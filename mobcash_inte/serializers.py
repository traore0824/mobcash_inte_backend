from rest_framework import serializers
from django.db.models import Sum
from accounts.models import AppName, Advertisement
from accounts.serializers import SmallBotUserSerializer, SmallUserSerializer

# from mobcash_inte.mobcash_service import BetApp
from mobcash_inte.models import (
    TRANS_STATUS,
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
)
from dateutil.relativedelta import relativedelta
from django.utils import timezone


class UploadFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadFile
        fields = "__all__"

        extra_kwargs = {"file": {"required": True}}


class IDLinkSerializer(serializers.ModelSerializer):
    app_details = serializers.SerializerMethodField()

    class Meta:
        model = IDLink
        fields = "__all__"

    def get_app_details(self, obj):
        return ReadAppNameSerializer(obj.app_name).data


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"


class NetworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Network
        fields = "__all__"


class SendNotificationSerializer(serializers.Serializer):
    content = serializers.CharField()
    title = serializers.CharField()


class ReadAppNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppName
        exclude = [
            "hash",
            "cashdeskid",
            "cashierpass",
        ]


class CreateAppNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppName
        fields = "__all__"


class UpdateSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Setting
        fields = "__all__"


class ReadSettingSerializer(serializers.ModelSerializer):

    class Meta:
        model = Setting
        exclude = [
            "connect_pro_password",
            "connect_pro_email",
            "connect_pro_token",
            "connect_pro_refresh",
            "expired_connect_pro_token",
            "mobcash_api_key",
            "mobcash_api_secret",
        ]


class CreateSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Setting
        fields = "__all__"


class BonusSerializer(serializers.ModelSerializer):
    user = SmallUserSerializer(read_only=True)

    class Meta:
        model = Bonus
        # fields = "__all__"
        exclude = [
            "bonus_with",
            "bonus_delete",
        ]


class TransactionDetailsSerializer(serializers.ModelSerializer):
    user = SmallUserSerializer()
    app_details = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = "__all__"

    def get_app_details(self, obj):
        return ReadAppNameSerializer(obj.app).data


class DepositTransactionSerializer(serializers.ModelSerializer):
    user = SmallUserSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "amount",
            "phone_number",
            "app",
            "user_app_id",
            "network",
            "user",
            "source",
        ]
        extra_kwargs = {
            "amount": {"required": True},
            "phone_number": {"required": True},
            "app": {"required": True},
            "user_app_id": {"required": True},
            "network": {"required": True},
            "source": {"required": True},
        }

    def validate(self, data):
        setting = Setting.objects.first()

        # Vérifie s'il y a une transaction acceptée dans les 5 dernières minutes
        transaction = Transaction.objects.filter(
            user_app_id=data.get("user_app_id"),
            status="accept",
            validated_at__gte=timezone.now() - relativedelta(minutes=5),
            amount=data.get("amount"),
        ).first()

        if transaction:
            time_left = (
                transaction.validated_at + relativedelta(minutes=5)
            ) - timezone.now()
            total_seconds = max(int(time_left.total_seconds()), 0)
            minutes_left = total_seconds // 60
            seconds_left = total_seconds % 60

            raise serializers.ValidationError(
                {"error_time_message": f"{minutes_left} M:{seconds_left} S"}
            )

        # Vérifie le montant minimum
        MINIMUM_DEPOSIT = setting.minimum_deposit
        if MINIMUM_DEPOSIT > data.get("amount"):
            raise serializers.ValidationError(
                {
                    "amount": f"{MINIMUM_DEPOSIT} est le montant minimum de depot accepter"
                }
            )

        return data


class WithdrawalTransactionSerializer(serializers.ModelSerializer):
    user = SmallUserSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "amount",
            "phone_number",
            "app",
            "user_app_id",
            "network",
            "withdriwal_code",
            "user",
            "source",
        ]
        extra_kwargs = {
            "withdriwal_code": {"required": True},
            "phone_number": {"required": True},
            "app": {"required": True},
            "user_app_id": {"required": True},
            "network": {"required": True},
            "source": {"required": True},
        }


class RewardTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ["user_app_id", "app", "amount", "source"]
        extra_kwargs = {
            "user_app_id": {"required": True},
            "app": {"required": True},
            "amount": {"required": True},
        }


class DisbursmentTransactionSerializer(serializers.Serializer):
    reference = serializers.CharField()


class UserPhoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPhone
        fields = "__all__"
        read_only_fields = ["user", "telegram_user"]

    def validate(self, data):
        user = self.context.get("user")
        telegram_user = self.context.get("telegram_user")

        phone = data.get("phone")
        network = data.get("network")

        # Vérification d’unicité selon le type d’utilisateur
        if user:
            exists = UserPhone.objects.filter(
                user=user, phone=phone, network=network
            ).exists()
            if exists:
                raise serializers.ValidationError(
                    {
                        "phone": "Ce numéro existe déjà pour ce réseau et cet utilisateur."
                    }
                )

        elif telegram_user:
            exists = UserPhone.objects.filter(
                telegram_user=telegram_user, phone=phone, network=network
            ).exists()
            if exists:
                raise serializers.ValidationError(
                    {
                        "phone": "Ce numéro existe déjà pour ce réseau et cet utilisateur Telegram."
                    }
                )

        return data


class ChangeTransactionStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=TRANS_STATUS, required=False)
    reference = serializers.CharField()


class BotWithdrawalTransactionSerializer(serializers.ModelSerializer):
    telegram_user = SmallBotUserSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "amount",
            "phone_number",
            "app",
            "user_app_id",
            "network",
            "withdriwal_code",
            "telegram_user",
        ]
        extra_kwargs = {
            "withdriwal_code": {"required": True},
            "phone_number": {"required": True},
            "app": {"required": True},
            "user_app_id": {"required": True},
            "network": {"required": True},
            "source": {"required": True},
        }


class BotDepositTransactionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Transaction
        fields = [
            "id",
            "amount",
            "phone_number",
            "app",
            "user_app_id",
            "network",
        ]
        extra_kwargs = {
            "amount": {"required": True},
            "phone_number": {"required": True},
            "app": {"required": True},
            "user_app_id": {"required": True},
            "network": {"required": True},
            "source": {"required": True},
        }

    def validate(self, data):
        setting = Setting.objects.first()

        # Vérifie s'il y a une transaction acceptée dans les 5 dernières minutes
        transaction = Transaction.objects.filter(
            user_app_id=data.get("user_app_id"),
            status="accept",
            validated_at__gte=timezone.now() - relativedelta(minutes=5),
            amount=data.get("amount"),
        ).first()

        if transaction:
            time_left = (
                transaction.validated_at + relativedelta(minutes=5)
            ) - timezone.now()
            total_seconds = max(int(time_left.total_seconds()), 0)
            minutes_left = total_seconds // 60
            seconds_left = total_seconds % 60

            raise serializers.ValidationError(
                {"error_time_message": f"{minutes_left} M:{seconds_left} S"}
            )

        # Vérifie le montant minimum
        MINIMUM_DEPOSIT = setting.minimum_deposit
        if MINIMUM_DEPOSIT > data.get("amount"):
            raise serializers.ValidationError(
                {
                    "amount": f"{MINIMUM_DEPOSIT} est le montant minimum de depot accepter"
                }
            )

        return data


class CouponSerializer(serializers.ModelSerializer):
    bet_app_details = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = "__all__"

    def get_bet_app_details(self, obj):
        return ReadAppNameSerializer(obj.bet_app).data


class CaisseSerializer(serializers.ModelSerializer):
    bet_app_details = serializers.SerializerMethodField()

    class Meta:
        model = Caisse
        fields = "__all__"

    def get_bet_app_details(self, obj):
        return ReadAppNameSerializer(obj.bet_app).data


class DepositSerializer(serializers.ModelSerializer):

    bet_app = serializers.PrimaryKeyRelatedField(
        queryset=AppName.objects.all(), write_only=True
    )

    bet_app_detail = ReadAppNameSerializer(source="bet_app", read_only=True)

    class Meta:
        model = Deposit
        fields = "__all__"


class SearchUserBetSerializer(serializers.Serializer):
    app_id = serializers.CharField(required=False)
    app_name = serializers.CharField(required=False)
    userid = serializers.CharField(required=True)

    def validate(self, data):
        app_id = data.get("app_id")
        app_name = data.get("app_name")

        if not app_id and not app_name:
            raise serializers.ValidationError(
                {"details": "Veuillez fournir soit app_id soit app_name."}
            )
        app = None
        if app_id:
            app = AppName.objects.filter(id=app_id).first()
        elif app_name:
            app = AppName.objects.filter(name=app_name).first()

        if not app:
            raise serializers.ValidationError({"details": "App not found."})

        data["app"] = app
        return data


class AdvertisementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Advertisement
        fields = ["id", "image", "created_at", "enable"]
        extra_kwargs = {"image": {"required": True}}


class BonusTransactionSerializer(serializers.ModelSerializer):
    user = SmallUserSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = ["id", "app", "user_app_id", "user", "source", "amount"]
        extra_kwargs = {
            "amount": {"required": True},
            "app": {"required": True},
            "user_app_id": {"required": True},
        }

    def validate(self, data):
        setting = Setting.objects.first()
        user = self.context.get("request").user

        # Vérifie s'il y a une transaction acceptée dans les 5 dernières minutes
        transaction = Transaction.objects.filter(
            user_app_id=data.get("user_app_id"),
            status="accept",
            validated_at__gte=timezone.now() - relativedelta(minutes=5),
            amount=data.get("amount"),
        ).first()

        if transaction:
            time_left = (
                transaction.validated_at + relativedelta(minutes=5)
            ) - timezone.now()
            total_seconds = max(int(time_left.total_seconds()), 0)
            minutes_left = total_seconds // 60
            seconds_left = total_seconds % 60

            raise serializers.ValidationError(
                {"error_time_message": f"{minutes_left} M:{seconds_left} S"}
            )

        bonus = Bonus.objects.filter(user=user, bonus_with=False, bonus_delete=False)
        amount = 0
        if bonus.exists():
            amount = bonus.aggregate(total=Sum("amount"))["total"] or 0

        # Vérifie le montant minimum
        MINIMUM_DEPOSIT = setting.reward_mini_withdrawal
        if MINIMUM_DEPOSIT > amount:
            raise serializers.ValidationError(
                {
                    "amount": f"{MINIMUM_DEPOSIT} est le montant minimum de bonus pour une operation accepter"
                }
            )
        reward = Reward.objects.filter(user=user).first()
        if reward.amount < amount:
            raise serializers.ValidationError(
                {
                    "amount": f"{MINIMUM_DEPOSIT} est le montant minimum de bonus pour une operation accepter"
                }
            )

        data["amount"] = amount
        bonus = Bonus.objects.update(user=user, bonus_with=True)
        reward.amount = 0
        reward.save()

        return data
