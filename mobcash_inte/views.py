import logging
import os
from django.forms import ValidationError
from django.shortcuts import render
from datetime import timedelta
from django.conf.urls import handler404
import requests
from rest_framework.permissions import BasePermission
from rest_framework import generics, permissions, status, decorators, viewsets
from accounts.helpers import CustomPagination
from accounts.models import Advertisement, AppName, TelegramUser, User
from rest_framework.filters import SearchFilter
import constant
from django.db import transaction as db_transaction
from dateutil.relativedelta import relativedelta
from mobcash_balance import get_balance
from mobcash_external_service import MobCashExternalService
from mobcash_inte.helpers import (
    generate_reference,
    init_mobcash,
    send_admin_notification,
    send_notification,
)
from mobcash_inte.mobcash_service import CashAPIService
from mobcash_inte.models import (
    TYPE_TRANS,
    Bonus,
    Caisse,
    Coupon,
    Deposit,
    IDLink,
    Network,
    Notification,
    RechargeMobcashBalance,
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
    CreateBonusSerializer,
    BotDepositTransactionSerializer,
    BotWithdrawalTransactionSerializer,
    CaisseSerializer,
    ChangeTransactionStatusSerializer,
    ProcessTransactionSerializer,
    UpdateTransactionStatusSerializer,
    ValidateVersionSerializer,
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
    RechargeMobcashBalanceSerializer,
    RewardTransactionSerializer,
    SearchUserBetSerializer,
    SendNotificationSerializer,
    TransactionDetailsSerializer,
    UploadFileSerializer,
    UserPhoneSerializer,
    WithdrawalTransactionSerializer,
)
from django.db import transaction
from django.db.models import F
from rest_framework.response import Response
from django.utils import timezone
from payment import connect_balance, connect_pro_status, connect_pro_webhook, disbursment_process, feexpay_check_status, payment_fonction, webhook_transaction_failled, webhook_transaction_success, feexpay_webhook, track_status_change, connect_pro_withd_process, feexpay_withdrawall_process, check_solde, process_transaction_notifications_and_bonus
from django.db.models import Sum, Count, Q, Avg
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth, TruncYear


connect_pro_logger = logging.getLogger("mobcash_inte_backend.transactions")
payment_logger = logging.getLogger("Payment transaction process")


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
        if self.request.user.is_staff:
            return queryset
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
            try:
                user = User.objects.filter(id=user_id).first()
            except:
                user = TelegramUser.objects.filter(id=user_id).first()
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


class ValidateVersionView(decorators.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = ValidateVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user_version = serializer.validated_data.get("version")
        setting = Setting.objects.first()
        
        if not setting:
            return Response(
                {"error": "Configuration non disponible"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        min_version = setting.min_version
        last_version = setting.last_version
        download_link = setting.dowload_apk_link
        
        # Si les versions ne sont pas configurées, on considère que tout est OK
        if min_version is None and last_version is None:
            return Response({
                "valid": True,
                "update_required": False,
                "update_available": False,
                "current_version": user_version,
                "min_version": None,
                "last_version": None,
                "download_link": download_link
            })
        
        # Déterminer si la mise à jour est obligatoire
        update_required = False
        if min_version is not None and user_version < min_version:
            update_required = True
        
        # Déterminer si une mise à jour est disponible (optionnelle)
        update_available = False
        if last_version is not None and user_version < last_version:
            update_available = True
        
        # La version est valide si elle est >= min_version
        valid = True
        if min_version is not None and user_version < min_version:
            valid = False
        
        return Response({
            "valid": valid,
            "update_required": update_required,
            "update_available": update_available,
            "current_version": user_version,
            "min_version": min_version,
            "last_version": last_version,
            "download_link": download_link
        }, status=status.HTTP_200_OK)


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


class CreateBonusView(generics.CreateAPIView):
    serializer_class = CreateBonusSerializer
    permission_classes = [permissions.IsAdminUser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bonus = serializer.save()
        
        # Mettre à jour le Reward de l'utilisateur
        try:
            reward, _ = Reward.objects.get_or_create(user=bonus.user)
            from decimal import Decimal
            reward.amount = Decimal(str(reward.amount)) + Decimal(str(bonus.amount))
            reward.save()
            connect_pro_logger.info(
                f"Reward mis à jour pour utilisateur {bonus.user.id}: +{bonus.amount} FCFA (nouveau solde: {reward.amount})"
            )
        except Exception as e:
            connect_pro_logger.error(
                f"Erreur mise à jour Reward pour bonus {bonus.id}: {str(e)}",
                exc_info=True,
            )
        
        return Response(
            BonusSerializer(bonus).data,
            status=status.HTTP_201_CREATED,
        )


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
        track_status_change(transaction, transaction.status, source="system")
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
        track_status_change(transaction, transaction.status, source="system")
        transaction.save()
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
        
        # ✅ SÉCURITÉ : Transaction atomique avec verrouillage
        with db_transaction.atomic():
            # 1. Verrouiller et récupérer tous les bonus disponibles
            bonus_queryset = Bonus.objects.select_for_update().filter(
                user=request.user, 
                bonus_with=False, 
                bonus_delete=False
            )
            bonus_amount = bonus_queryset.aggregate(total=Sum("amount"))["total"] or 0
            
            # 2. Vérifier qu'il y a au moins un bonus disponible
            if bonus_amount <= 0:
                return Response(
                    {
                        "details": "Vous n'avez aucun bonus disponible à utiliser."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            # 3. Créer la transaction avec le montant total des bonus
            transaction = serializer.save(
                reference=generate_reference(prefix="depot-"),
                user=request.user,
                type_trans="reward",
                amount=int(bonus_amount),  # Utiliser tout le solde disponible
            )
            track_status_change(transaction, transaction.status, source="system")
            
            # 4. Verrouiller la transaction pour éviter traitement simultané
            transaction = Transaction.objects.select_for_update(nowait=True).get(id=transaction.id)
            
            # 5. Vérifier que la transaction n'est pas déjà traitée
            if transaction.status != "pending":
                return Response(
                    {"error": "Transaction déjà traitée"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            # 6. Appeler directement l'API (comme dans webhook_transaction_success)
            setting = Setting.objects.first()
            if not setting:
                return Response(
                    {"error": "Configuration système non trouvée"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            
            try:
                transaction.status = "init_payment"
                track_status_change(transaction, "init_payment", source="system")
                transaction.save()
                
                app = transaction.app
                servculAPI = init_mobcash(app_name=app)
                amount = transaction.amount
                
                # Appeler l'API selon le type d'app
                if transaction.app.hash:
                    response = servculAPI.recharge_account(
                        amount=float(amount), userid=transaction.user_app_id
                    )
                    connect_pro_logger.info(
                        f"Reponse de l'api de {transaction.app.name}: {response}"
                    )
                    xbet_response_data = response.get("data")
                else:
                    response = MobCashExternalService().create_deposit(transaction=transaction)
                    connect_pro_logger.info( 
                        f"Reponse de l'api de {transaction.app.name}: {response}"
                    )
                    xbet_response_data = response
                
                # 7. Si succès : marquer tous les bonus comme utilisés et mettre status="accept"
                if xbet_response_data.get("Success") == True:
                    payment_logger.info(
                        f"Transaction reward de {transaction.app.name} success"
                    )
                    transaction.validated_at = timezone.now()
                    transaction.status = "accept"
                    track_status_change(transaction, "accept", source="system")
                    transaction.save()
                    
                    # Marquer TOUS les bonus comme utilisés
                    bonus_queryset.update(bonus_with=True)
                    
                    # Appel de la tâche Celery pour les notifications
                    try:
                        process_transaction_notifications_and_bonus.delay(transaction_id=transaction.id)
                    except Exception as e:
                        connect_pro_logger.error(
                            f"Erreur process_transaction_notifications_and_bonus.delay pour transaction {transaction.id}: {str(e)}",
                            exc_info=True,
                        )
                    
                    # Appeler check_solde pour les reward
                    try:
                        check_solde.delay(transaction_id=transaction.id)
                    except Exception as e:
                        connect_pro_logger.error(
                            f"Erreur check_solde.delay pour transaction {transaction.id}: {str(e)}",
                            exc_info=True,
                        )
                else:
                    # 8. Si échec : mettre status="error" (bonus restent disponibles)
                    transaction.status = "error"
                    track_status_change(transaction, "error", source="system")
                    transaction.error_message = f"Échec de l'API : {xbet_response_data}"
                    transaction.save()
                    
                    # Envoyer une notification d'erreur à l'utilisateur
                    try:
                            app_name = transaction.app.name.upper() if transaction.app else "l'application"
                            error_message = (
                                f"Une erreur est survenue lors de l'utilisation de vos rewards de {transaction.amount} FCFA sur "
                                f"{app_name}. "
                                f"Référence de la transaction : {transaction.reference}"
                            )
                        process_transaction_notifications_and_bonus.delay(
                            transaction_id=transaction.id,
                            is_error=True,
                            error_message=error_message
                        )
                    except Exception as e:
                        connect_pro_logger.error(
                            f"Erreur envoi notification échec reward transaction {transaction.id}: {str(e)}",
                            exc_info=True,
                        )
                    
                    return Response(
                        {
                            "error": "Échec du traitement de la transaction",
                            "details": xbet_response_data
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                    
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur lors du traitement de la transaction reward {transaction.id}: {str(e)}",
                    exc_info=True,
                )
                transaction.status = "error"
                track_status_change(transaction, "error", source="system")
                transaction.error_message = str(e)
                transaction.save()
                
                return Response(
                    {
                        "error": "Erreur lors du traitement",
                        "details": str(e)
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        
        transaction.refresh_from_db()
        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )


class GetRewardView(decorators.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Récupère le solde Reward de l'utilisateur authentifié.
        Retourne le solde Reward total et la somme des bonus disponibles.
        """
        user = request.user
        
        # Récupérer le Reward de l'utilisateur
        reward, _ = Reward.objects.get_or_create(user=user)
        reward_amount = float(reward.amount) if reward.amount else 0.0
        
        # Calculer la somme des bonus disponibles
        bonus_queryset = Bonus.objects.filter(
            user=user,
            bonus_with=False,
            bonus_delete=False
        )
        bonus_total = bonus_queryset.aggregate(total=Sum("amount"))["total"] or 0
        bonus_total = float(bonus_total) if bonus_total else 0.0
        
        return Response(
            {
                "reward_amount": reward_amount,
                "available_bonus_total": bonus_total,
                "total_available": reward_amount + bonus_total
            },
            status=status.HTTP_200_OK,
        )


class ConnectProWebhook(decorators.APIView):
    def post(self, request, *args, **kwargs):
        try:
            connect_pro_logger.info(
                f"[RECEPTION] Connect pro webhook reçu le {timezone.now()} avec le body: {request.data}"
            )

            data = request.data
            uid = data.get("uid")

            if not uid:
                connect_pro_logger.warning("Webhook reçu sans UID")
                return Response(
                    {"error": "UID manquant dans les données"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ✅ TOUT DANS UNE SEULE TRANSACTION ATOMIQUE
            with transaction.atomic():
                connect_pro_logger.info(f"[STEP 1] Entrée transaction pour {uid}")
                
                # Vérifier si déjà traité (avec lock pour éviter race condition)
                existing_log = (
                    WebhookLog.objects.select_for_update()
                    .filter(reference=uid, processed=True)
                    .first()
                )

                if existing_log:
                    connect_pro_logger.info(
                        f"[DUPLICATION] Webhook {uid} déjà traité le {existing_log.processed_at}"
                    )
                    return Response(
                        {"message": "Webhook déjà traité"}, status=status.HTTP_200_OK
                    )

                connect_pro_logger.info(f"[STEP 2] Création WebhookLog pour {uid}")
                
                # Créer ou récupérer le WebhookLog (avec lock)
                webhook_log, created = WebhookLog.objects.select_for_update().get_or_create(
                    reference=uid,
                    defaults={
                        "api": "CONNECT PRO",
                        "webhook_data": data,
                        "header": str(request.headers),
                        "processed": False,
                    },
                )

                connect_pro_logger.info(
                    f"[STEP 3] WebhookLog created={created}, processed={webhook_log.processed}"
                )

                # Si déjà en cours de traitement par une autre requête
                if not created and webhook_log.processed:
                    connect_pro_logger.info(
                        f"[RACE-CONDITION] Webhook {uid} déjà traité"
                    )
                    return Response(
                        {"message": "Webhook déjà traité"}, status=status.HTTP_200_OK
                    )

                # Si déjà créé mais pas encore traité (retry)
                if not created and not webhook_log.processed:
                    connect_pro_logger.warning(
                        f"[RETRY] Webhook {uid} en retry (erreur: {webhook_log.error_message})"
                    )

                # ✅ TRAITEMENT DANS LA TRANSACTION
                connect_pro_logger.info(f"[STEP 4] AVANT appel connect_pro_webhook pour {uid}")
                
                try:
                    connect_pro_webhook(data=data)
                    
                    connect_pro_logger.info(f"[STEP 5] APRÈS appel connect_pro_webhook pour {uid}")

                    # ✅ MARQUER COMME TRAITÉ (dans la même transaction)
                    webhook_log.processed = True
                    webhook_log.processed_at = timezone.now()
                    webhook_log.error_message = None  # Clear previous errors
                    webhook_log.save(
                        update_fields=["processed", "processed_at", "error_message"]
                    )

                    connect_pro_logger.info(f"[SUCCESS] Webhook {uid} traité avec succès")

                    return Response(
                        {"message": "Webhook traité avec succès"}, 
                        status=status.HTTP_200_OK
                    )

                except Exception as e:
                    # ✅ ENREGISTRER L'ERREUR mais NE PAS marquer comme processed
                    webhook_log.error_message = str(e)
                    webhook_log.save(update_fields=["error_message"])

                    connect_pro_logger.error(
                        f"[ERROR] Erreur traitement {uid}: {str(e)}",
                        exc_info=True,
                    )

                    # La transaction sera automatiquement rollback
                    return Response(
                        {"error": "Erreur lors du traitement"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

        except Exception as e:
            connect_pro_logger.error(
                f"[CRITICAL] Erreur inattendue: {str(e)}",
                exc_info=True,
            )
            return Response(
                {"error": "Erreur interne du serveur"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class FeexpayWebhook(decorators.APIView):
    def post(self, request, *args, **kwargs):
        try:
            connect_pro_logger.info(
                f"Feexpay webhook reçu le {timezone.now()} avec le body: {request.data}"
            )

            data = request.data
            reference = data.get("externalId") or data.get("reference") or data.get("uid")

            if not reference:
                connect_pro_logger.warning("Webhook reçu sans référence")
                return Response(
                    {"error": "Référence manquante dans les données"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ✅ TRANSACTION ATOMIQUE avec LOCK
            with transaction.atomic():
                # Vérifier si déjà traité (avec lock pour éviter race condition)
                existing_log = (
                    WebhookLog.objects.select_for_update()
                    .filter(reference=reference, processed=True)
                    .first()
                )

                if existing_log:
                    connect_pro_logger.info(
                        f"[DUPLICATION] Webhook {reference} déjà traité le {existing_log.processed_at}"
                    )
                    return Response(
                        {"message": "Webhook déjà traité"}, status=status.HTTP_200_OK
                    )

                # Créer ou récupérer le WebhookLog (avec lock)
                (
                    webhook_log,
                    created,
                ) = WebhookLog.objects.select_for_update().get_or_create(
                    reference=reference,
                    defaults={
                        "api": "FEEXPAY",
                        "webhook_data": data,
                        "header": str(request.headers),
                        "processed": False,
                    },
                )

                # Si déjà en cours de traitement par une autre requête
                if not created and webhook_log.processed:
                    connect_pro_logger.info(
                        f"[RACE-CONDITION] Webhook {reference} déjà traité"
                    )
                    return Response(
                        {"message": "Webhook déjà traité"}, status=status.HTTP_200_OK
                    )

                # Si déjà créé mais pas encore traité (rare, mais possible)
                if not created and not webhook_log.processed:
                    connect_pro_logger.warning(
                        f"[RETRY] Webhook {reference} en retry (erreur précédente: {webhook_log.error_message})"
                    )

            # ⚠️ SORTIE DE LA TRANSACTION - Le traitement peut être long
            connect_pro_logger.info(
                f"[NEW] WebhookLog créé pour référence {reference}, début du traitement..."
            )

            # ✅ TRAITEMENT (hors transaction pour ne pas bloquer la DB trop longtemps)
            try:
                feexpay_webhook(data=data)

                # ✅ MARQUER COMME TRAITÉ (dans une nouvelle transaction)
                with transaction.atomic():
                    webhook_log.processed = True
                    webhook_log.processed_at = timezone.now()
                    webhook_log.error_message = None  # Clear previous errors
                    webhook_log.save(
                        update_fields=["processed", "processed_at", "error_message"]
                    )

                connect_pro_logger.info(f"[SUCCESS] Webhook {reference} traité avec succès")

                return Response(
                    {"message": "Webhook traité avec succès"}, status=status.HTTP_200_OK
                )

            except Exception as e:
                # ✅ ENREGISTRER L'ERREUR mais NE PAS marquer comme processed
                with transaction.atomic():
                    webhook_log.error_message = str(e)
                    webhook_log.save(update_fields=["error_message"])

                connect_pro_logger.error(
                    f"[ERROR] Erreur lors du traitement de {reference}: {str(e)}",
                    exc_info=True,
                )

                return Response(
                    {"error": "Erreur lors du traitement"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except Exception as e:
            connect_pro_logger.error(
                f"[CRITICAL] Erreur inattendue dans FeexpayWebhook: {str(e)}",
                exc_info=True,
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
    # permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        serializer = ChangeTransactionStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reference = serializer.validated_data.get("reference")
        transaction = Transaction.objects.filter(reference=reference).first()
        setting = Setting.objects.first()
        destination_status = serializer.validated_data.get("status")
        if not transaction:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not destination_status:
            if transaction.status == "pending" :
                with db_transaction.atomic():
                    if transaction.network.name == "wave":
                        data = connect_pro_status(reference=transaction.public_id, is_wave=True)
                    else:
                        data = connect_pro_status(
                            reference=transaction.public_id,
                            is_momo_pay=(
                                False
                                if (
                                    not transaction.network.payment_by_link
                                    or transaction.type_trans == "withdrawal"
                                )
                                else True
                            ),
                        )
                    if (
                        data.get("status") == "failed" or data.get("status") == "cancelled"
                    ) or data.get("status") == "timeout":
                        connect_pro_logger.info("Transaction is fail")
                        webhook_transaction_failled(transaction=transaction)
                    elif data.get("status") == "success" or data.get("status") == "confirmed":
                        connect_pro_logger.info("Transaction is success")
                        webhook_transaction_success(transaction=transaction, setting=setting)
            elif transaction.status == "init_payment":
                if transaction.type_trans == "withdrawal":
                    transaction.status = "accept"
                    track_status_change(transaction, "accept", source="admin", admin_id=request.user.id)
                    transaction.save()
                else:
                    webhook_transaction_success(transaction=transaction, setting=setting)

            transaction = Transaction.objects.filter(reference=reference).first()
            return Response(
                {"status": transaction.status}, status=status.HTTP_200_OK
            )
        else: 
            new_status = serializer.validated_data.get("status")
            transaction.status = new_status
            track_status_change(transaction, new_status, source="admin", admin_id=request.user.id)
            transaction.fixed_by_admin = True
            transaction.save(update_fields=['status', 'fixed_by_admin'])
            return Response(
                {"status": transaction.status}, status=status.HTTP_200_OK
            )

class TransactionStatus(decorators.APIView):
    def get(self, request, *args, **kwargs):
        reference=self.request.GET.get("reference")
        transaction = Transaction.objects.filter(reference=reference).first()
        if not transaction:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if transaction.api=="connect":
            if transaction.network.name == "wave":
                data = connect_pro_status(reference=transaction.public_id, is_wave=True)
            else:
                data = connect_pro_status(
                    reference=transaction.public_id,
                    is_momo_pay=(
                        False
                        if (
                            not transaction.network.payment_by_link
                            or transaction.type_trans == "withdrawal"
                        )
                        else True
                    ),
                )
            return Response(data, status=status.HTTP_200_OK)
        elif transaction.api=="feexpay":
            data = feexpay_check_status(public_id=transaction.public_id)
            return Response(data, status=status.HTTP_200_OK)
        return Response(status=status.HTTP_200_OK)

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
        track_status_change(transaction, transaction.status, source="system")
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
        track_status_change(transaction, transaction.status, source="system")
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
        track_status_change(transaction, transaction.status, source="system")
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
        "app_name",
        
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


class ReadNotificationView(decorators.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Marque toutes les notifications de l'utilisateur connecté comme lues.
        """
        if not request.user.is_authenticated:
            return Response(
                {"error": "User not authenticated"}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        notifications = Notification.objects.filter(
            user=request.user, 
            is_read=False
        )
        
        if notifications.exists():
            updated_count = notifications.update(is_read=True)
            return Response(
                {
                    "message": f"{updated_count} notification(s) marquée(s) comme lue(s)",
                    "updated_count": updated_count
                },
                status=status.HTTP_200_OK
            )
        
        return Response(
            {"message": "Aucune notification non lue trouvée", "updated_count": 0},
            status=status.HTTP_200_OK
        )


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


class TransactionDetailView(decorators.APIView):
    """
    Récupère les détails complets d'une transaction par ID ou référence.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        transaction_id = request.GET.get("id")
        reference = request.GET.get("reference")

        if not transaction_id and not reference:
            return Response(
                {"error": "Le paramètre 'id' ou 'reference' est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Construire la requête
        query = {}
        if transaction_id:
            query["id"] = transaction_id
        if reference:
            query["reference"] = reference

        # Récupérer la transaction
        transaction = Transaction.objects.filter(**query).first()

        if not transaction:
            return Response(
                {"error": "Transaction non trouvée"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Vérifier les permissions (utilisateur non-admin ne peut voir que ses transactions)
        if not request.user.is_staff:
            if request.user.is_authenticated:
                if transaction.user != request.user:
                    return Response(
                        {"error": "Vous n'avez pas accès à cette transaction"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                # Pour les utilisateurs Telegram
                if hasattr(request, "telegram_user") and transaction.telegram_user != request.telegram_user:
                    return Response(
                        {"error": "Vous n'avez pas accès à cette transaction"},
                        status=status.HTTP_403_FORBIDDEN
                    )

        return Response(
            TransactionDetailsSerializer(transaction).data,
            status=status.HTTP_200_OK
        )


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
        if app.hash:
            init_app = init_mobcash(app_name=app)
            response = init_app.search_user(userid=userid)
            if response.get("code") != constant.CODE_EXEPTION:
                response = response.get("data")
            else:
                response = {}
        else:
            response = MobCashExternalService().verify_player(
                player_user_id=userid, code=app.name
            )

        

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
        if self.request.user.is_staff:
            return Coupon.objects.all()
        else:
            last_24h = timezone.now() - relativedelta(hours=24)
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
    serializer_class = AdvertisementSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Advertisement.objects.all().order_by("-created_at")
        return Advertisement.objects.filter(enable=True).order_by("-created_at")
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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
        # Récupérer toutes les caisses avec leurs apps
        caisses = Caisse.objects.select_related('bet_app').all()

        # Vérifier si au moins une app a un hash
        has_app_with_hash = any(caisse.bet_app.hash for caisse in caisses if caisse.bet_app)

        if has_app_with_hash:
            # Si au moins une app a un hash, retourner la somme des soldes
            net_volume = sum(float(caisse.solde) for caisse in caisses)
        else:
            # Sinon, retourner le premier solde (ou 0 si aucune caisse)
            if caisses.exists():
                net_volume = MobCashExternalService().get_wallet_balance()
            else:
                net_volume = 0.0 

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
            transactions_by_app[app.name] = {}

            for type_key, _ in TYPE_TRANS:
                app_transactions = transactions.filter(
                    app=app,
                    status="accept",
                    type_trans=type_key
                )

                transactions_by_app[app.name][type_key] = {
                    "count": app_transactions.count(),
                    "total_amount": float(
                        app_transactions.aggregate(total=Sum("amount"))["total"] or 0
                    ),
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


class APIBalanceView(decorators.APIView):
    def get(self, request, *args, **kwargs):
        # balance, created = BpaySold.objects.get_or_create()
        data = {
            # "barkapay": barkapay_balance(),
            # "pal": balance_pal(),
            "connect": float(connect_balance().get("data").get("balance")),
            # "dgs_pay": dgs_pay_balance(),
            # "bpay": balance.balance,
        }
        return Response(data, status=status.HTTP_200_OK)


import asyncio

class MobCashBalance(decorators.APIView):

    def get(self, request, *args, **kwargs):
        # Exécuter la logique async dans un contexte sync
        result = asyncio.run(self.get_balances())
        return Response(result, status=status.HTTP_200_OK)

    async def get_balances(self):
        from asgiref.sync import sync_to_async

        soldes = await sync_to_async(list)(
            Caisse.objects.select_related("bet_app").all()
        )

        result = []
        for solde in soldes:
            api_response = await get_balance(
                solde.bet_app.cashdeskid,
                solde.bet_app.hash,
                solde.bet_app.cashierpass,
            )

            result.append(
                {
                    "app_name": solde.bet_app.name,
                    "solde": float(solde.solde),
                    "app_image": solde.bet_app.image,
                    "balance_limit": (
                        api_response.get("Limit") if api_response else None
                    ),
                }
            )

        return result
from dotenv import load_dotenv
load_dotenv()

from celery import shared_task

@shared_task
def feexpay_payout_task( amount: int, phone_number: str, network_name: str):
    """
    Task Celery pour créer un retrait Feexpay
    """

    connect_pro_logger.info("=== FEEXPAY PAYOUT TASK START ===")

    # Variables d'environnement
    shop = os.getenv("FEEXPAY_CUSTOMER_ID")
    api_key = os.getenv("FEEXPAY_API_KEY")

    if not shop:
        connect_pro_logger.error("FEEXPAY_CUSTOMER_ID non configuré")
        raise ValidationError("FEEXPAY_CUSTOMER_ID non configuré")

    if not api_key:
        connect_pro_logger.error("FEEXPAY_API_KEY non configuré")
        raise ValidationError("FEEXPAY_API_KEY non configuré")

    url = "https://api.feexpay.me/api/payouts/public/transfer/global"

    connect_pro_logger.info(
        f"Initialisation retrait | amount={amount} | phone={phone_number} | network={network_name}"
    )

    data = {
        "phoneNumber": phone_number,
        "amount": str(amount),
        "shop": shop,
        "network": network_name,
        "motif": "Retrait de caisse",
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        connect_pro_logger.info("Envoi requête Feexpay payout")

        response = requests.post(url=url, json=data, headers=headers, timeout=90)

        connect_pro_logger.info(
            f"Réponse Feexpay | status={response.status_code} | body={response.text}"
        )

        response.raise_for_status()

        response_data = response.json()

        connect_pro_logger.info("=== FEEXPAY PAYOUT TASK SUCCESS ===")
        return response_data

    except requests.exceptions.RequestException as e:
        connect_pro_logger.error(
            f"Erreur HTTP Feexpay payout | {str(e)}", exc_info=True
        )
        raise

    except Exception as e:
        connect_pro_logger.critical(
            f"Erreur inconnue Feexpay payout | {str(e)}", exc_info=True
        )
        raise


class TestAPIViews(decorators.APIView):

    def post(self, request, *args, **kwargs):
        connect_pro_logger.info("API payout appelée")

        amount = 100
        phone_number = "2290155187395"
        network_name = "MOOV"

        try:
            task = feexpay_payout_task.delay(
                amount=amount,
                phone_number=phone_number,
                network_name=network_name,
            )

            connect_pro_logger.info(
                f"Task Celery feexpay_payout lancée | task_id={task.id}"
            )

            return Response(
                {
                    "message": "Retrait en cours de traitement",
                    "task_id": task.id,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as e:
            connect_pro_logger.error(
                f"Erreur lancement task Celery | {str(e)}", exc_info=True
            )

            return Response(
                {"error": "Impossible de lancer le retrait"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RechargeMobcashBalanceView(generics.ListCreateAPIView):
    """
    API pour créer et lister les recharges de balance Mobcash avec preuve de paiement.
    Permission: Admin uniquement
    """
    serializer_class = RechargeMobcashBalanceSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = CustomPagination
    queryset = RechargeMobcashBalance.objects.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def create(self, request, *args, **kwargs):
        """
        Créer une recharge et envoyer la requête à l'API MobCash
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Créer l'instance
        instance = serializer.save()

        # Appeler l'API MobCash en passant directement request.data et request.FILES
        try:
            mobcash_service = MobCashExternalService()
            result = mobcash_service.create_recharge_request_from_request(
                request_data=request.data
            )

            connect_pro_logger.info(
                f"Réponse de l'API MobCash pour la recharge {instance.payment_reference}: {result}"
            )

            # Si l'API retourne une erreur, on peut logger mais on garde l'instance créée
            if not result.get('success'):
                connect_pro_logger.error(
                    f"Erreur lors de l'envoi à l'API MobCash pour {instance.payment_reference}: {result.get('error')}"
                )

        except Exception as e:
            connect_pro_logger.error(
                f"Exception lors de l'appel à l'API MobCash pour {instance.payment_reference}: {str(e)}",
                exc_info=True
            )
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
                )


class UpdateCaisseBalanceView(decorators.APIView):
    """
    API simple pour récupérer le solde via MobCashExternalService
    et mettre à jour la Caisse.
    Pas de permissions requises.
    """
    
    def get(self, request, *args, **kwargs):
        try:
            connect_pro_logger.info("[UPDATE_CAISSE_BALANCE] Début de la mise à jour du solde")
            
            # Récupérer le solde via MobCashExternalService
            mobcash_service = MobCashExternalService()
            balance = mobcash_service.get_wallet_balance()
            
            if balance is None or balance < 0:
                connect_pro_logger.error(
                    f"[UPDATE_CAISSE_BALANCE] Échec récupération solde: {balance}"
                )
                return Response(
                    {
                        "success": False,
                        "error": "Impossible de récupérer le solde",
                        "balance": balance
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Mettre à jour toutes les caisses avec le nouveau solde
            caisses = Caisse.objects.all()
            updated_count = 0
            
            if caisses.exists():
                for caisse in caisses:
                    caisse.solde = float(balance)
                    caisse.updated_at = timezone.now()
                    caisse.save()
                    updated_count += 1
                connect_pro_logger.info(
                    f"[UPDATE_CAISSE_BALANCE] {updated_count} caisse(s) mise(s) à jour avec le solde {balance}"
                )
            else:
                # Créer une caisse par défaut si aucune n'existe
                # On a besoin d'un bet_app, donc on prend le premier disponible
                first_app = AppName.objects.first()
                if first_app:
                    Caisse.objects.create(
                        solde=float(balance),
                        bet_app=first_app,
                        updated_at=timezone.now()
                    )
                    updated_count = 1
                    connect_pro_logger.info(
                        f"[UPDATE_CAISSE_BALANCE] Caisse créée avec le solde {balance} pour l'app {first_app.name}"
                    )
                else:
                    connect_pro_logger.error(
                        "[UPDATE_CAISSE_BALANCE] Aucune app disponible pour créer une caisse"
                    )
                    return Response(
                        {
                            "success": False,
                            "error": "Aucune app disponible pour créer une caisse"
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            return Response(
                {
                    "success": True,
                    "balance": float(balance),
                    "updated_caisses": updated_count,
                    "message": f"Solde mis à jour avec succès: {balance}"
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            connect_pro_logger.error(
                f"[UPDATE_CAISSE_BALANCE] Erreur lors de la mise à jour: {str(e)}",
                exc_info=True
            )
            return Response(
                {
                    "success": False,
                    "error": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProcessTransactionView(decorators.APIView):
    """
    API 1: Traiter une transaction (dépôt ou retrait)
    Permission: Admin uniquement
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        serializer = ProcessTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reference = serializer.validated_data.get("reference")

        transaction = Transaction.objects.filter(reference=reference).first()
        if not transaction:
            return Response(
                {"error": "Transaction non trouvée"},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            # Tracker le statut initial si pas encore tracké
            if not transaction.all_status:
                track_status_change(transaction, transaction.status, source="system")

            # Traiter selon le type de transaction
            if transaction.type_trans == "deposit" or transaction.type_trans == "reward":
                # Pour les dépôts, utiliser webhook_transaction_success qui gère automatiquement betpay/mobcash
                setting = Setting.objects.first()
                webhook_transaction_success(transaction=transaction, setting=setting)
            elif transaction.type_trans == "withdrawal":
                # Pour les retraits, utiliser l'API appropriée selon transaction.api
                if transaction.api == "connect":
                    connect_pro_withd_process(transaction=transaction)
                elif transaction.api == "feexpay":
                    feexpay_withdrawall_process(transaction=transaction)
                else:
                    return Response(
                        {"error": f"API de retrait non supportée: {transaction.api}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                return Response(
                    {"error": f"Type de transaction non supporté: {transaction.type_trans}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            transaction.refresh_from_db()
            return Response(
                TransactionDetailsSerializer(transaction).data,
                status=status.HTTP_200_OK
            )

        except Exception as e:
            connect_pro_logger.error(
                f"Erreur lors du traitement de la transaction {reference}: {str(e)}",
                exc_info=True
            )
            return Response(
                {"error": f"Erreur lors du traitement: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UpdateTransactionStatusView(decorators.APIView):
    """
    API 2: Changer le statut d'une transaction
    Permission: Admin uniquement
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        serializer = UpdateTransactionStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reference = serializer.validated_data.get("reference")
        new_status = serializer.validated_data.get("new_status")

        transaction = Transaction.objects.filter(reference=reference).first()
        if not transaction:
            return Response(
                {"error": "Transaction non trouvée"},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            old_status = transaction.status
            
            # Tracker le changement de statut avec source admin
            track_status_change(
                transaction=transaction,
                new_status=new_status,
                source="admin",
                admin_id=request.user.id
            )

            # Mettre à jour le statut et marquer comme fixé par admin
            transaction.status = new_status
            transaction.fixed_by_admin = True
            transaction.save(update_fields=['status', 'fixed_by_admin'])

            transaction.refresh_from_db()
            return Response(
                {
                    "message": f"Statut changé de '{old_status}' à '{new_status}'",
                    "transaction": TransactionDetailsSerializer(transaction).data
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            connect_pro_logger.error(
                f"Erreur lors du changement de statut pour {reference}: {str(e)}",
                exc_info=True
            )
            return Response(
                {"error": f"Erreur lors du changement de statut: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TransactionStatusHistoryView(decorators.APIView):
    """
    API 3: Consulter la traçabilité des statuts d'une transaction
    Permission: Admin uniquement
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        search = request.GET.get("search")

        # Vérifier qu'un critère de recherche est fourni
        if not search:
            return Response(
                {"error": "Le paramètre 'search' est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        search_term = search.strip()

        # Construire la requête pour rechercher dans tous les champs pertinents
        query = Q()

        # Recherche par référence (exacte ou partielle)
        query |= Q(reference__icontains=search_term)

        # Recherche par email dans User ou TelegramUser
        query |= Q(user__email__icontains=search_term) | Q(telegram_user__email__icontains=search_term)

        # Recherche par fullname (first_name + last_name) dans User ou TelegramUser
        # Split le search_term en parties pour rechercher dans first_name et last_name
        search_parts = search_term.split()
        if len(search_parts) >= 2:
            # Si plusieurs mots, chercher le premier dans first_name et le reste dans last_name
            first_name_part = search_parts[0]
            last_name_part = " ".join(search_parts[1:])
            query |= (
                Q(user__first_name__icontains=first_name_part, user__last_name__icontains=last_name_part) |
                Q(telegram_user__first_name__icontains=first_name_part, telegram_user__last_name__icontains=last_name_part)
            )
        else:
            # Si un seul mot, chercher dans first_name ou last_name
            name_part = search_parts[0]
            query |= (
                Q(user__first_name__icontains=name_part) |
                Q(user__last_name__icontains=name_part) |
                Q(telegram_user__first_name__icontains=name_part) |
                Q(telegram_user__last_name__icontains=name_part)
            )

        # Si plusieurs critères sont fournis, utiliser AND (tous doivent correspondre)
        transactions = Transaction.objects.filter(query).select_related('user', 'telegram_user').distinct()

        transaction_count = transactions.count()

        if transaction_count == 0:
            return Response(
                {"error": "Aucune transaction trouvée avec les critères de recherche fournis"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Si plusieurs transactions correspondent, retourner un avertissement avec la première
        if transaction_count > 1:
            transaction = transactions.first()
            warning_message = f"Attention: {transaction_count} transactions trouvées. Affichage de la première (référence: {transaction.reference})"
        else:
            transaction = transactions.first()
            warning_message = None

        # Retourner l'historique des statuts
        all_status = transaction.all_status if transaction.all_status else []

        # Si pas d'historique mais que la transaction existe, ajouter le statut actuel
        if not all_status:
            all_status = [{
                "status": transaction.status,
                "timestamp": transaction.created_at.isoformat() if transaction.created_at else timezone.now().isoformat(),
                "source": "system"
            }]

        # Récupérer les infos utilisateur pour la réponse
        user_email = None
        user_fullname = None
        if transaction.user:
            user_email = transaction.user.email
            user_fullname = transaction.user.full_name()
        elif transaction.telegram_user:
            user_email = transaction.telegram_user.email
            user_fullname = transaction.telegram_user.full_name()

        response_data = {
            "reference": transaction.reference,
            "current_status": transaction.status,
            "fixed_by_admin": transaction.fixed_by_admin,
            "status_history": all_status,
            "total_status_changes": len(all_status),
            "user_email": user_email,
            "user_fullname": user_fullname,
            "total_matching_transactions": transaction_count
        }

        if warning_message:
            response_data["warning"] = warning_message

        return Response(
            response_data,
            status=status.HTTP_200_OK
            )


class ChangeTransactionStatusManuelViews(decorators.APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        serializer = ChangeTransactionStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reference = serializer.validated_data.get("reference")
        new_status = serializer.validated_data.get("status")

        transaction = Transaction.objects.filter(reference=reference).first()
        if not transaction:
            return Response(
                {"error": "Transaction non trouvée"},
                status=status.HTTP_404_NOT_FOUND
            )

        if not new_status:
            return Response(
                {"error": "Le statut est obligatoire"},
                status=status.HTTP_400_BAD_REQUEST
            )

        track_status_change(
            transaction=transaction,
            new_status=new_status,
            source="admin",
            admin_id=str(request.user.id)
        )

        transaction.status = new_status
        transaction.fixed_by_admin = True
        transaction.save(update_fields=['status', 'fixed_by_admin'])

        return Response(
            TransactionDetailsSerializer(transaction).data, 
            status=status.HTTP_200_OK
        )


class FinalizeDepositTransaction(decorators.APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        reference = self.request.data.get("reference")
        transaction = Transaction.objects.filter(reference=reference).exclude(status="accept").first()
        if not transaction:
            return Response(status=status.HTTP_404_NOT_FOUND)

        response = MobCashExternalService().create_deposit(transaction=transaction)
        xbet_response_data = response
        connect_pro_logger.info(
            f"MobCash deposit response | response={response} | xbet_response_data={xbet_response_data}",
        )

        if xbet_response_data.get("Success") == True:
            transaction.status = "accept"
            transaction.mobcash_response = str(response)
            transaction.save()

            check_solde.delay(transaction_id=transaction.id)
            send_notification(
                user=transaction.user,
                title="Opération réussie avec succès",
                content=f"Vous avez effectué un dépôt de {transaction.amount} FCFA sur votre compte {transaction.app.name if transaction.app else 'plateforme'}",
            )
        return Response(TransactionDetailsSerializer(transaction).data)


# Create your views here.
