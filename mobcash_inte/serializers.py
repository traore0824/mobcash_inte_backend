from rest_framework import serializers

from accounts.models import AppName
from accounts.serializers import SmallBotUserSerializer, SmallUserSerializer
from mobcash_inte.models import (
    TRANS_STATUS,
    Advertisement,
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
from dateutil.relativedelta import relativedelta
from django.utils import timezone

class AdvertisementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Advertisement
        fields = "__all__"


class UploadFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadFile
        fields = "__all__"

        extra_kwargs = {
            "file": {"required": True}
        }


class IDLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = IDLink
        fields = "__all__"


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
        exclude = [
            "hash",
            "cashdeskid",
            "cashierpass",
        ]


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
        ]


class CreateSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Setting
        fields = "__all__"


class BonusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bonus
        # fields = "__all__"
        exclude = ["bonus_with",
"bonus_delete",]


class TransactionDetailsSerializer(serializers.ModelSerializer):
    user = SmallUserSerializer()
    class Meta:
        model = Transaction
        fields ="__all__"


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


class ChangeTransactionStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=TRANS_STATUS)
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
        transaction = Transaction.objects.filter(
            user_app_id=data.get("user_app_id"),
            status="accept",
            validated_at__lt=timezone.now() + relativedelta(minutes=5),
        ).first()
        if transaction:
            time_left = (
                transaction.validated_at + relativedelta(minutes=5)
            ) - timezone.now()
            minutes_left = time_left.seconds // 60
            seconds_left = time_left.seconds % 60
            raise serializers.ValidationError(
                {"error_time_message": f"{minutes_left} M:{seconds_left} S"}
            )

        MINIMUM_DEPOSIT = setting.minimum_deposit
        if MINIMUM_DEPOSIT > data.get("amount"):
            raise serializers.ValidationError(
                {
                    "amount": f"{MINIMUM_DEPOSIT} est le montant minimum de depot accepter"
                }
            )
        return data


class CaisseSerializer(serializers.ModelSerializer):
    bet_app = ReadAppNameSerializer(read_only=True)
    class Meta:
        model = Caisse 
        fields = "__all__"


class DepositSerializer(serializers.ModelSerializer):
    bet_app = ReadAppNameSerializer(read_only=True)

    class Meta:
        model = Deposit
        fields = "__all__"
