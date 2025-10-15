import logging
from django.shortcuts import render
from rest_framework.permissions import BasePermission
from rest_framework import generics, permissions, status, decorators, viewsets
from accounts.helpers import CustomPagination
from accounts.models import AppName, TelegramUser, User
from mobcash_inte.helpers import (
    generate_reference,
    send_admin_notification,
    send_notification,
)
from mobcash_inte.models import (
    Bonus,
    Caisse,
    Deposit,
    IDLink,
    Network,
    Notification,
    Setting,
    Transaction,
    UploadFile,
    UserPhone,
)
from django_filters.rest_framework import DjangoFilterBackend
from mobcash_inte.permissions import IsAuthenticated
from mobcash_inte.serializers import (
    BonusSerializer,
    BotDepositTransactionSerializer,
    ChangeTransactionStatusSerializer,
    CreateAppNameSerializer,
    CreateSettingSerializer,
    DepositSerializer,
    DepositTransactionSerializer,
    DisbursmentTransactionSerializer,
    IDLinkSerializer,
    NetworkSerializer,
    NotificationSerializer,
    ReadAppNameSerializer,
    ReadSettingSerializer,
    RewardTransactionSerializer,
    SendNotificationSerializer,
    TransactionDetailsSerializer,
    UploadFileSerializer,
    UserPhoneSerializer,
)
from django.db import transaction
from rest_framework.response import Response
from django.utils import timezone
from payment import connect_pro_webhook, disbursment_process, payment_fonction
from django.db.models import Sum

connect_pro_logger = logging.getLogger("Connect pro Logger")


class UploadFileView(generics.ListCreateAPIView):
    serializer_class = UploadFileSerializer
    pagination_class = CustomPagination
    queryset = UploadFile.objects.all()


class CreateNetworkView(generics.ListCreateAPIView):
    serializer_class = NetworkSerializer

    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            self.permission_classes = [permissions.IsAdminUser]
        return super().get_permissions()

    def get_queryset(self):
        filter_type = self.request.GET.get("type")
        queryset = Network.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(enable=True)

        if filter_type == "deposit":
            queryset = queryset.filter(active_for_deposit=True)
        elif filter_type == "withdrawal":
            queryset = queryset.filter(active_for_with=True)

        return queryset


class DetailsNetworkView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = NetworkSerializer
    queryset = Network.objects.all()
    permission_classes = [permissions.IsAdminUser]

    def get_permissions(self):
        if self.request.method == "GET":
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()


class NotificationView(generics.ListCreateAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(is_read=False)
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = SendNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = self.request.GET.get("id")
        if user_id:
            user = User.objects.filter(id=user_id).first()
            if not user:
                return Response(status=status.HTTP_404_NOT_FOUND)
            send_notification(
                user=user,
                title=serializer.validated_data.get("title"),
                content=serializer.validated_data.get("content"),
            )

        else:
            send_admin_notification.delay(
                user=user,
                title=serializer.validated_data.get("title"),
                content=serializer.validated_data.get("content"),
            )
        return Response(status=status.HTTP_200_OK)


class CreateDeposit(generics.ListCreateAPIView):
    serializer_class = DepositSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Deposit.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = DepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        with transaction.atomic():
            solde = Caisse.objects.get_or_create(bet_app=obj.bet_app)
        return Response(DepositSerializer(obj).data, status=status.HTTP_201_CREATED)


class CreateAppName(generics.ListCreateAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["name"]

    def get_queryset(self):
        if self.request.user.is_staff:
            queryset = AppName.objects.all().order_by("order")
        else:
            queryset = AppName.objects.filter(enable=True).order_by("order")
        return queryset

    serializer_class = ReadAppNameSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_permissions(self):
        if self.request.method == "GET":
            self.permission_classes = [IsAuthenticated]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method in ["POST", "PUT", "DELETE"]:
            return CreateAppNameSerializer
        return ReadAppNameSerializer


class DetailAppName(generics.RetrieveUpdateDestroyAPIView):
    queryset = AppName.objects.all().order_by("order")
    serializer_class = ReadAppNameSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_serializer_class(self):
        if self.request.method in ["PUT", "DELETE", "PATCH"]:
            return CreateAppNameSerializer
        return ReadAppNameSerializer


class SettingViews(decorators.APIView):

    def get_permissions(self):
        if self.request.method == "GET":
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()

    def put(self, request, *args, **kwargs):
        setting = Setting.objects.first()
        serializer = CreateSettingSerializer(
            data=request.data, instance=setting, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        setting.refresh_from_db()
        return Response(ReadSettingSerializer(setting).data)

    def get(self, request, *args, **kwargs):
        setting = Setting.objects.first()
        return Response(ReadSettingSerializer(setting).data)


class GetBonus(generics.ListAPIView):
    serializer_class = BonusSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Bonus.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset


class CreateDepositTransactionViews(generics.CreateAPIView):
    serializer_class = DepositTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(
            generate_reference(prefix="depot-"),
            user=self.request.user,
            type_trans="deposit",
        )
        payment_fonction(reference=transaction.reference)
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )


class RewardTransactionViews(generics.CreateAPIView):
    serializer_class = RewardTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        bonus = Bonus.objects.filter(bonus_with=False, bonus_delete=False)
        bonus_amount = bonus.aggregate(total=Sum("amount"))["total"] or 0
        if bonus_amount < serializer.validated_data.get("amount"):
            return Response(
                {
                    "details": "Votre compte bonus ne dispose pas de suffisamment de fonds pour effectuer cette opération. "
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        transaction = serializer.save(
            reference=generate_reference(prefix="depot-"),
            user=self.request.user,
            type_trans="reward",
        )
        bonus = bonus.update(bonus_with=True)
        payment_fonction(reference=transaction.reference)
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )


class ConnectProWebhook(decorators.APIView):
    def post(self, request, *args, **kwargs):
        connect_pro_logger.info(
            f"Connect pro webhookrecue le {timezone.now()} avec le body{request.data}"
        )
        data = request.data
        connect_pro_webhook(data=data)
        return Response(status=status.HTTP_200_OK)


class DisbursmentTransactionView(decorators.APIView):
    def post(self, request, *args, **kwargs):
        serializer = DisbursmentTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reference = serializer.validated_data.get("reference")
        transaction = Transaction.objects.filter(reference=reference).first()
        if not transaction:
            return Response(status=status.HTTP_404_NOT_FOUND)
        transaction.old_status = transaction.status
        transaction.old_public_id=transaction.public_id
        transaction.save()
        disbursment_process(transaction=transaction)
        transaction.refresh_from_db()
        return Response(
            TransactionDetailsSerializer(transaction).data, status=status.HTTP_200_OK
        )


class UserPhoneViewSet(viewsets.ModelViewSet):
    serializer_class = UserPhoneSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return UserPhone.objects.filter(user=self.request.user)
        return UserPhone.objects.filter(telegram_user=self.request.telegram_user)

    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            serializer.save(user=self.request.user)
        else:
            serializer.save(telegram_user=self.request.telegram_user)


class ChangeTransactionStatus(decorators.APIView):
    def post(self, request, *args, **kwargs):
        serializer = ChangeTransactionStatusSerializer(request.data)
        serializer.is_valid(raise_exception=True)
        reference = serializer.validated_data.get("reference")
        transaction = Transaction.objects.filter(reference=reference).first()
        if not transaction:
            return Response(status=status.HTTP_404_NOT_FOUND)
        transaction.status = serializer.validated_data.get("status")
        transaction.save()
        return Response(
            TransactionDetailsSerializer(transaction).data, status=status.HTTP_200_OK
        )


class BotWithdrawalTransactionViews(decorators.APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

class BotDepositTransactionViews(generics.CreateAPIView):
    serializer_class = BotDepositTransactionSerializer
    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(
            generate_reference(prefix="depot-"),
            user=self.request.user,
            type_trans="deposit",
        )
        payment_fonction(reference=transaction.reference)
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )

class WithdrawalTransactionViews(generics.CreateAPIView):
    serializer_class = BotDepositTransactionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(
            generate_reference(prefix="retrait-"),
            user=self.request.user,
            type_trans="retrait",
        )
        payment_fonction(reference=transaction.reference)
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )

class IDLinkViews(viewsets.ModelViewSet):
    serializer_class = IDLinkSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["app_name"]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return IDLink.objects.filter(user=self.request.user)
        return IDLink.objects.filter(telegram_user=self.request.telegram_user)

    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            serializer.save(user=self.request.user)
        else:
            serializer.save(telegram_user=self.request.telegram_user)


# Create your views here.
