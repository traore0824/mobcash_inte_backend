import logging
from django.shortcuts import render
from datetime import timedelta
from django.conf.urls import handler404
from rest_framework.permissions import BasePermission
from rest_framework import generics, permissions, status, decorators, viewsets
from accounts.helpers import CustomPagination
from accounts.models import Advertisement, AppName, TelegramUser, User
from rest_framework.filters import SearchFilter
import constant
from mobcash_inte.helpers import (
    generate_reference,
    init_mobcash,
    send_admin_notification,
    send_notification,
)
from mobcash_inte.models import (
    Bonus,
    Caisse,
    Coupon,
    Deposit,
    IDLink,
    Network,
    Notification,
    Reward,
    Setting,
    Transaction,
    UploadFile,
    UserPhone,
    WebhookLog,
)
from django_filters.rest_framework import DjangoFilterBackend
from mobcash_inte.permissions import IsAuthenticated
from mobcash_inte.serializers import (
    AdvertisementSerializer,
    BonusSerializer,
    BonusTransactionSerializer,
    BotDepositTransactionSerializer,
    BotWithdrawalTransactionSerializer,
    CaisseSerializer,
    ChangeTransactionStatusSerializer,
    CouponSerializer,
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
    SearchUserBetSerializer,
    SendNotificationSerializer,
    TransactionDetailsSerializer,
    UploadFileSerializer,
    UserPhoneSerializer,
    WithdrawalTransactionSerializer,
)
from django.db import transaction
from rest_framework.response import Response
from django.utils import timezone
from payment import connect_pro_webhook, disbursment_process, payment_fonction, webhook_transaction_success
from django.db.models import Sum, Count, Q, Avg
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth, TruncYear

connect_pro_logger = logging.getLogger("mobcash_inte_backend.transactions")


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
        filter_type = self.request.GET.get("type", "deposit")
        queryset = Network.objects.all()
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
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["user"]

    def get_queryset(self):
        queryset = Notification.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user, is_read=False)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = SendNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = self.request.GET.get("user_id")
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
                title=serializer.validated_data.get("title"),
                content=serializer.validated_data.get("content"),
            )
        return Response(status=status.HTTP_200_OK)


class ListDeposit(generics.ListAPIView):
    serializer_class = DepositSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Deposit.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["bet_app"]
    pagination_class = CustomPagination


class ListCaisse(generics.ListAPIView):
    serializer_class = CaisseSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Caisse.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["bet_app"]
    # pagination_class = CustomPagination


class ListDeposit(generics.ListAPIView):
    serializer_class = DepositSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Deposit.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["bet_app"]
    pagination_class = CustomPagination


class CreateDeposit(generics.CreateAPIView):

    serializer_class = DepositSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Deposit.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["bet_app"]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = DepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        caisse, created = Caisse.objects.select_for_update().get_or_create(
            bet_app=obj.bet_app
        )

        caisse.solde += obj.amount
        caisse.save()

        return Response(DepositSerializer(obj).data, status=status.HTTP_201_CREATED)


class CreateAppName(generics.ListCreateAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["name"]

    def get_queryset(self):
        if self.request.user.is_staff:
            queryset = AppName.objects.all().order_by("order")
        else:
            queryset = AppName.objects.filter(enable=True).order_by("order")
        type = self.request.GET.get("type")
        if type == "deposit":
            queryset = queryset.filter(active_for_deposit=True)
        elif type == "withdrawal":
            queryset = queryset.filter(active_for_with=True)
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
            self.permission_classes = [permissions.AllowAny]
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
    pagination_class = CustomPagination
    serializer_class = BonusSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["user"]

    def get_queryset(self):
        queryset = Bonus.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(
                user=self.request.user, bonus_with=False, bonus_delete=False
            )
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
            reference=generate_reference(prefix="depot-"),
            user=self.request.user,
            type_trans="deposit",
        )
        transaction.api = transaction.network.deposit_api
        transaction.save()
        payment_fonction(reference=transaction.reference)
        transaction.refresh_from_db()
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )


class CreateBonusDepositTransactionViews(generics.CreateAPIView):
    serializer_class = BonusTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(
            reference=generate_reference(prefix="depot-"),
            user=self.request.user,
            type_trans="reward",
        )
        # transaction.api = transaction.network.deposit_api
        # transaction.save()
        webhook_transaction_success(transaction=transaction, setting=Setting.objects.first())
        transaction.refresh_from_db()
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )

    # def get_serializer_context(self):
    #     context = super().get_serializer_context()
    #     # Ajoute les infos utiles au serializer
    #     context["request"] = self.request
    #     # context["telegram_user"] = getattr(self.request, "telegram_user", None)
    #     return context


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
        try:
            # Log de la réception du webhook
            connect_pro_logger.info(
                f"Connect pro webhook reçu le {timezone.now()} avec le body: {request.data}"
            )

            data = request.data

            # Vérification des données
            if not data:
                connect_pro_logger.warning("Webhook reçu mais avec aucune donnée")
                return Response(
                    {"error": "Aucune donnée fournie"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Vérification de l'UID
            uid = data.get("uid")
            if not uid:
                connect_pro_logger.warning("Webhook reçu sans UID")
                return Response(
                    {"error": "UID manquant dans les données"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Vérification de duplication
            try:
                webhook_log = WebhookLog.objects.filter(reference=uid).first()
                if webhook_log:
                    connect_pro_logger.info(
                        f"Webhook avec UID {uid} déjà traité - Duplication évitée"
                    )
                    return Response(
                        {"message": "Webhook déjà traité"}, status=status.HTTP_200_OK
                    )
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur lors de la vérification du webhook log: {str(e)}",
                    exc_info=True,
                )
                # On continue le traitement même si la vérification échoue

            # Lancement de la tâche asynchrone
            try:
                connect_pro_webhook.delay(data=data)
                connect_pro_logger.info(f"Tâche asynchrone lancée pour UID {uid}")
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur lors du lancement de la tâche asynchrone: {str(e)}",
                    exc_info=True,
                )
                return Response(
                    {"error": "Erreur lors du traitement asynchrone"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Création du log
            try:
                WebhookLog.objects.create(
                    reference=uid,
                    api="CONNECT PRO",
                    webhook_data=data,
                    header=str(request.headers),
                )
                connect_pro_logger.info(f"WebhookLog créé avec succès pour UID {uid}")
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur lors de la création du WebhookLog pour UID {uid}: {str(e)}",
                    exc_info=True,
                )
                # On ne retourne pas d'erreur car la tâche a déjà été lancée

            return Response(
                {"message": "Webhook traité avec succès"}, status=status.HTTP_200_OK
            )

        except Exception as e:
            # Catch-all pour toute erreur non prévue
            connect_pro_logger.error(
                f"Erreur inattendue dans ConnectProWebhook: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Erreur interne du serveur"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DisbursmentTransactionView(decorators.APIView):
    def post(self, request, *args, **kwargs):
        serializer = DisbursmentTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reference = serializer.validated_data.get("reference")
        transaction = Transaction.objects.filter(reference=reference).first()
        if not transaction:
            return Response(status=status.HTTP_404_NOT_FOUND)
        transaction.old_status = transaction.status
        transaction.old_public_id = transaction.public_id
        transaction.save()
        disbursment_process(transaction=transaction)
        transaction.refresh_from_db()
        return Response(
            TransactionDetailsSerializer(transaction).data, status=status.HTTP_200_OK
        )


class UserPhoneViewSet(viewsets.ModelViewSet):
    serializer_class = UserPhoneSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["user", "telegram_user", "network"]
    search_fields = ["phone"]

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return UserPhone.objects.all()
        if self.request.user.is_authenticated:
            return UserPhone.objects.filter(user=self.request.user)
        return UserPhone.objects.filter(telegram_user=self.request.telegram_user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Ajoute les infos utiles au serializer
        context["user"] = (
            self.request.user if self.request.user.is_authenticated else None
        )
        context["telegram_user"] = getattr(self.request, "telegram_user", None)
        return context

    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            serializer.save(user=self.request.user)
        else:
            serializer.save(telegram_user=self.request.telegram_user)


class ChangeTransactionStatus(decorators.APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        serializer = ChangeTransactionStatusSerializer(data=request.data)
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


class BotWithdrawalTransactionViews(generics.CreateAPIView):

    serializer_class = BotWithdrawalTransactionSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(
            reference=generate_reference(prefix="retrait-"),
            type_trans="withdrawal",
            telegram_user=request.telegram_user,
        )
        transaction.api = transaction.network.withdrawal_api
        transaction.save()
        payment_fonction(reference=transaction.reference)
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )


class BotDepositTransactionViews(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BotDepositTransactionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(
            reference=generate_reference(prefix="depot-"),
            type_trans="deposit",
            telegram_user=request.telegram_user,
            source="bot",
        )
        transaction.api = transaction.network.deposit_api
        transaction.save()
        payment_fonction(reference=transaction.reference)
        transaction.refresh_from_db()
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )


class WithdrawalTransactionViews(generics.CreateAPIView):
    serializer_class = WithdrawalTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(
            reference=generate_reference(prefix="retrait-"),
            type_trans="withdrawal",
            user=request.user,
        )
        transaction.api = transaction.network.withdrawal_api
        transaction.save()
        payment_fonction(reference=transaction.reference)
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )


class DepositTransactionViews(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DepositTransactionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(
            reference=generate_reference(prefix="depot-"),
            type_trans="deposit",
            telegram_user=request.telegram_user,
            source="bot",
        )
        payment_fonction(reference=transaction.reference)
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )


class IDLinkViews(viewsets.ModelViewSet):
    serializer_class = IDLinkSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = [
        "email",
        "phone",
        
    ]
    search_fields = ["user_app_id"]

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return IDLink.objects.all()
        if self.request.user.is_authenticated:
            return IDLink.objects.filter(user=self.request.user)
        return IDLink.objects.filter(telegram_user=self.request.telegram_user)

    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            serializer.save(user=self.request.user)
        else:
            serializer.save(telegram_user=self.request.telegram_user)


class ReadAllNotificaation(decorators.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        result = None
        notifications = Notification.objects.filter(is_read=False)
        if notifications.exists():
            result = notifications.update(is_read=True)
        return Response({"result": result})


class HistoryTransactionViews(generics.ListAPIView):
    serializer_class = TransactionDetailsSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = [
        "user",
        "telegram_user",
        "type_trans",
        "status",
        "app",
        "source",
        "network",
    ]
    search_fields = [
        "reference",
        "phone_number",
        "user_app_id",
        "public_id",
    ]

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return Transaction.objects.all()
        if self.request.user.is_authenticated:
            return Transaction.objects.filter(user=self.request.user)
        return Transaction.objects.filter(telegram_user=self.request.telegram_user)


def custom_404(request, exception):
    return render(request, "404.html", status=404)


handler404 = custom_404


class SearchUserBet(decorators.APIView):
    def post(self, request, *args, **kwargs):
        serializer = SearchUserBetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app = serializer.validated_data["app"]
        app_name = app.name
        userid = serializer.validated_data["userid"]

        init_app = init_mobcash(app_name=app)
        response = init_app.search_user(userid=userid)

        if response.get("code") != constant.CODE_EXEPTION:
            response = response.get("data")
        else:
            response = {}

        return Response(response)


class CreateCoupon(generics.ListCreateAPIView):
    serializer_class = CouponSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = CustomPagination

    def get_permissions(self):
        if self.request.method == "GET":
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()

    def get_queryset(self):
        """Afficher uniquement les coupons de moins de 24 heures"""
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        return Coupon.objects.filter(created_at__gte=last_24h)


class CouponDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API pour récupérer, modifier ou supprimer un coupon spécifique.
    """

    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [
        permissions.IsAdminUser
    ]  # seuls les admins peuvent modifier/supprimer

    def get_permissions(self):
        # Permet aux utilisateurs connectés de consulter un coupon (GET)
        if self.request.method == "GET":
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()

class CreateAdvertisementViews(generics.ListCreateAPIView):
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdvertisementSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()

    def get_queryset(self):
        if self.request.user.is_staff:
            objs = Advertisement.objects.all()
        else:
            objs = Advertisement.objects.filter(enable=True)
        return objs


class DetailsAdvertisementViews(generics.RetrieveUpdateDestroyAPIView):
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdvertisementSerializer


    def get_queryset(self):
        if self.request.user.is_staff:
            objs = Advertisement.objects.all()
        else:
            objs = Advertisement.objects.filter(enable=True)
        return objs


class StatisticsView(decorators.APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        """
        Retourne les statistiques importantes :
        - Volume des transactions
        - Croissance utilisateurs
        - Système de parrainage
        """
        # Paramètres de période (optionnels)
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")
        
        # Filtre de base pour les dates
        date_filter = Q()
        if start_date:
            date_filter &= Q(created_at__gte=start_date)
        if end_date:
            date_filter &= Q(created_at__lte=end_date)

        # ========== VOLUME DES TRANSACTIONS ==========
        transactions = Transaction.objects.filter(date_filter)
        
        # Total des dépôts
        deposits = transactions.filter(type_trans="deposit", status="accept")
        total_deposits_amount = deposits.aggregate(
            total=Sum("amount")
        )["total"] or 0
        total_deposits_count = deposits.count()
        
        # Total des retraits
        withdrawals = transactions.filter(type_trans="withdrawal", status="accept")
        total_withdrawals_amount = withdrawals.aggregate(
            total=Sum("amount")
        )["total"] or 0
        total_withdrawals_count = withdrawals.count()
        
        # Volume net
        net_volume = total_deposits_amount - total_withdrawals_amount
        
        # Évolution par période
        evolution_daily = (
            transactions.filter(type_trans__in=["deposit", "withdrawal"], status="accept")
            .annotate(date=TruncDate("created_at"))
            .values("date", "type_trans")
            .annotate(
                total_amount=Sum("amount"),
                count=Count("id")
            )
            .order_by("date")
        )
        
        evolution_weekly = (
            transactions.filter(type_trans__in=["deposit", "withdrawal"], status="accept")
            .annotate(week=TruncWeek("created_at"))
            .values("week", "type_trans")
            .annotate(
                total_amount=Sum("amount"),
                count=Count("id")
            )
            .order_by("week")
        )
        
        evolution_monthly = (
            transactions.filter(type_trans__in=["deposit", "withdrawal"], status="accept")
            .annotate(month=TruncMonth("created_at"))
            .values("month", "type_trans")
            .annotate(
                total_amount=Sum("amount"),
                count=Count("id")
            )
            .order_by("month")
        )
        
        evolution_yearly = (
            transactions.filter(type_trans__in=["deposit", "withdrawal"], status="accept")
            .annotate(year=TruncYear("created_at"))
            .values("year", "type_trans")
            .annotate(
                total_amount=Sum("amount"),
                count=Count("id")
            )
            .order_by("year")
        )

        # ========== CROISSANCE UTILISATEURS ==========
        users_date_filter = Q()
        if start_date:
            users_date_filter &= Q(date_joined__gte=start_date)
        if end_date:
            users_date_filter &= Q(date_joined__lte=end_date)
        
        all_users = User.objects.filter(users_date_filter, is_delete=False)
        
        # Nouveaux utilisateurs par période
        new_users_daily = (
            all_users.annotate(date=TruncDate("date_joined"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )
        
        new_users_weekly = (
            all_users.annotate(week=TruncWeek("date_joined"))
            .values("week")
            .annotate(count=Count("id"))
            .order_by("week")
        )
        
        new_users_monthly = (
            all_users.annotate(month=TruncMonth("date_joined"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        
        # Utilisateurs actifs (qui ont fait au moins une transaction)
        # Compte les User normaux avec transactions
        user_transactions_filter = Q(transaction__isnull=False)
        if start_date:
            user_transactions_filter &= Q(transaction__created_at__gte=start_date)
        if end_date:
            user_transactions_filter &= Q(transaction__created_at__lte=end_date)
        
        active_users = User.objects.filter(user_transactions_filter).distinct().count()
        
        # Compte les TelegramUser avec transactions
        telegram_transactions_filter = Q(transaction__isnull=False)
        if start_date:
            telegram_transactions_filter &= Q(transaction__created_at__gte=start_date)
        if end_date:
            telegram_transactions_filter &= Q(transaction__created_at__lte=end_date)
        
        active_telegram_users = TelegramUser.objects.filter(telegram_transactions_filter).distinct().count()
        
        active_users_count = active_users + active_telegram_users
        
        # Utilisateurs par source
        users_by_source = []
        for source in ["mobile", "web", "bot"]:
            source_transactions = transactions.filter(source=source)
            unique_users = source_transactions.exclude(user__isnull=True).values("user").distinct().count()
            unique_telegram_users = source_transactions.exclude(telegram_user__isnull=True).values("telegram_user").distinct().count()
            users_by_source.append({
                "source": source,
                "count": unique_users + unique_telegram_users
            })
        
        # Utilisateurs bloqués vs actifs
        blocked_users = User.objects.filter(is_block=True, is_delete=False).count()
        active_status_users = User.objects.filter(is_active=True, is_block=False, is_delete=False).count()
        inactive_status_users = User.objects.filter(is_active=False, is_delete=False).count()

        # ========== SYSTÈME DE PARRAINAGE ==========
        # Nombre de parrainages effectués (utilisateurs avec referrer_code)
        parrainages_count = User.objects.filter(
            referrer_code__isnull=False,
            referrer_code__gt="",
            is_delete=False
        ).count()
        
        if start_date or end_date:
            parrainages_count = User.objects.filter(
                referrer_code__isnull=False,
                referrer_code__gt="",
                is_delete=False,
                date_joined__gte=start_date if start_date else timezone.datetime.min,
                date_joined__lte=end_date if end_date else timezone.now()
            ).count()
        
        # Montant total des bonus de parrainage distribués
        referral_bonuses = Bonus.objects.filter(
            reason_bonus__icontains="parrainage"
        )
        if start_date:
            referral_bonuses = referral_bonuses.filter(created_at__gte=start_date)
        if end_date:
            referral_bonuses = referral_bonuses.filter(created_at__lte=end_date)
        
        total_referral_bonus = referral_bonuses.aggregate(
            total=Sum("amount")
        )["total"] or 0
        
        # Top utilisateurs par nombre de filleuls
        top_referrers_list = []
        for user in User.objects.filter(referral_code__isnull=False, referral_code__gt=""):
            filleuls = User.objects.filter(referrer_code=user.referral_code, is_delete=False).count()
            if filleuls > 0:
                top_referrers_list.append({
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "referral_code": user.referral_code,
                    "filleuls_count": filleuls
                })
        
        top_referrers_list = sorted(top_referrers_list, key=lambda x: x["filleuls_count"], reverse=True)[:10]
        
        # Taux d'activation des codes de parrainage
        total_referral_codes = User.objects.filter(
            referral_code__isnull=False,
            referral_code__gt="",
            is_delete=False
        ).count()
        
        activated_referral_codes = User.objects.filter(
            referrer_code__isnull=False,
            referrer_code__gt="",
            is_delete=False
        ).values("referrer_code").distinct().count()
        
        activation_rate = (
            (activated_referral_codes / total_referral_codes * 100)
            if total_referral_codes > 0
            else 0
        )

        # ========== STATISTIQUES DASHBOARD ==========
        # Total Utilisateurs
        total_users = User.objects.filter(is_delete=False).count()
        
        # Utilisateurs Actifs/Inactifs
        active_users_total = User.objects.filter(is_active=True, is_block=False, is_delete=False).count()
        inactive_users_total = User.objects.filter(is_active=False, is_delete=False).count()
        
        # Total Bonus
        total_bonus = Bonus.objects.filter(bonus_delete=False).aggregate(
            total=Sum("amount")
        )["total"] or 0
        
        # Statistiques Bot
        bot_transactions = transactions.filter(source="bot")
        total_transactions_bot = bot_transactions.count()
        total_deposit_bot = bot_transactions.filter(type_trans="deposit", status="accept").count()
        total_withdrawal_bot = bot_transactions.filter(type_trans="withdrawal", status="accept").count()
        
        # Utilisateurs Bot (TelegramUser)
        telegram_users_count = TelegramUser.objects.count()
        if start_date or end_date:
            telegram_users_filter = Q()
            if start_date:
                telegram_users_filter &= Q(created_at__gte=start_date)
            if end_date:
                telegram_users_filter &= Q(created_at__lte=end_date)
            telegram_users_count = TelegramUser.objects.filter(telegram_users_filter).count()
        
        # Total Transactions
        total_transactions = transactions.count()
        
        # Transactions par application
        transactions_by_app = {}
        apps = AppName.objects.all()
        for app in apps:
            app_transactions = transactions.filter(app=app, status="accept")
            transactions_by_app[app.name] = {
                "count": app_transactions.count(),
                "total_amount": float(app_transactions.aggregate(total=Sum("amount"))["total"] or 0)
            }
        
        # Balance Bizao (Solde de caisse total)
        total_balance_bizao = Caisse.objects.aggregate(
            total=Sum("solde")
        )["total"] or 0
        
        # Dépôts et Retraits Bizao (depuis le modèle Deposit)
        deposits_bizao = Deposit.objects.all()
        if start_date:
            deposits_bizao = deposits_bizao.filter(created_at__gte=start_date)
        if end_date:
            deposits_bizao = deposits_bizao.filter(created_at__lte=end_date)
        
        total_deposits_bizao_count = deposits_bizao.count()
        total_deposits_bizao_amount = deposits_bizao.aggregate(
            total=Sum("amount")
        )["total"] or 0
        
        # Retraits Bizao (depuis Caisse - calculé différemment)
        # On utilise les retraits acceptés des transactions
        withdrawals_bizao = withdrawals
        total_withdrawals_bizao_count = withdrawals_bizao.count()
        total_withdrawals_bizao_amount = float(total_withdrawals_amount)
        
        # Récompenses (Rewards)
        total_rewards = Reward.objects.aggregate(
            total=Sum("amount")
        )["total"] or 0
        
        # Remboursements (Disbursements)
        disbursements = transactions.filter(type_trans="disbursements")
        total_disbursements = disbursements.count()
        total_disbursements_amount = disbursements.aggregate(
            total=Sum("amount")
        )["total"] or 0
        
        # Publicités (Advertisements)
        total_advertisements = Advertisement.objects.count()
        active_advertisements = Advertisement.objects.filter(enable=True).count()
        
        # Coupons
        total_coupons = Coupon.objects.count()
        # Coupons en cours (moins de 24h)
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        active_coupons = Coupon.objects.filter(created_at__gte=last_24h).count()

        return Response({
            "dashboard_stats": {
                "total_users": total_users,
                "active_users": active_users_total,
                "inactive_users": inactive_users_total,
                "total_bonus": float(total_bonus),
                "bot_stats": {
                    "total_transactions": total_transactions_bot,
                    "total_deposits": total_deposit_bot,
                    "total_withdrawals": total_withdrawal_bot,
                    "total_users": telegram_users_count
                },
                "total_transactions": total_transactions,
                "transactions_by_app": transactions_by_app,
                "balance_bizao": float(total_balance_bizao),
                "deposits_bizao": {
                    "count": total_deposits_bizao_count,
                    "amount": float(total_deposits_bizao_amount)
                },
                "withdrawals_bizao": {
                    "count": total_withdrawals_bizao_count,
                    "amount": total_withdrawals_bizao_amount
                },
                "rewards": {
                    "total": float(total_rewards)
                },
                "disbursements": {
                    "count": total_disbursements,
                    "amount": float(total_disbursements_amount)
                },
                "advertisements": {
                    "total": total_advertisements,
                    "active": active_advertisements
                },
                "coupons": {
                    "total": total_coupons,
                    "active": active_coupons
                }
            },
            "volume_transactions": {
                "deposits": {
                    "total_amount": float(total_deposits_amount),
                    "total_count": total_deposits_count
                },
                "withdrawals": {
                    "total_amount": float(total_withdrawals_amount),
                    "total_count": total_withdrawals_count
                },
                "net_volume": float(net_volume),
                "evolution": {
                    "daily": list(evolution_daily),
                    "weekly": list(evolution_weekly),
                    "monthly": list(evolution_monthly),
                    "yearly": list(evolution_yearly)
                }
            },
            "user_growth": {
                "new_users": {
                    "daily": list(new_users_daily),
                    "weekly": list(new_users_weekly),
                    "monthly": list(new_users_monthly)
                },
                "active_users_count": active_users_count,
                "users_by_source": list(users_by_source),
                "status": {
                    "blocked": blocked_users,
                    "active": active_status_users,
                    "inactive": inactive_status_users
                }
            },
            "referral_system": {
                "parrainages_count": parrainages_count,
                "total_referral_bonus": float(total_referral_bonus),
                "top_referrers": top_referrers_list,
                "activation_rate": round(activation_rate, 2)
            }
        })


# Create your views here.
