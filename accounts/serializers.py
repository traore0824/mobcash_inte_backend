import re

from django.core.validators import validate_email

from rest_framework import serializers

from accounts.helpers import validate_password
import constant
from django.utils.translation import gettext_lazy as _
from .models import AppName, TelegramUser, User
import string, secrets


def generate_referral_code(min_length=6):
    characters = string.ascii_uppercase + string.digits
    length = min_length

    while True:
        code = "".join(secrets.choice(characters) for _ in range(length))
        if not User.objects.filter(referral_code=code).exists():
            return code
        length += 1


class UserRegistrationSerializer(serializers.ModelSerializer):
    re_password = serializers.CharField(min_length=6, write_only=True)
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "re_password",
            "password",
        ]

    def validate(self, attrs):
        password = attrs.get("password", None)
        re_password = attrs.get("re_password", None)

        if (password and re_password) and (password != re_password):
            raise serializers.ValidationError({"password": constant.PASSWORD_NOT_MATCH})
        return attrs

    def create(self, validated_data):
        user = User.objects.create(
            first_name=validated_data.get("first_name"),
            last_name=validated_data.get("last_name"),
            email=validated_data.get("email"),
            phone=validated_data.get("phone"),
            referral_code=generate_referral_code(),
            username=validated_data.get("email"),
        )
        user.set_password(validated_data.get("password"))
        user.save()
        return user


class AccountActivationSerializer(serializers.Serializer):
    otp = serializers.CharField()


class LoginSerializer(serializers.ModelSerializer):
    email_or_phone = serializers.CharField()
    password = serializers.CharField()

    class Meta:
        model = User
        fields = ["id", "email_or_phone", "password"]


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=6, write_only=True)
    confirm_new_password = serializers.CharField(min_length=6, write_only=True)

    def validate(self, attrs):
        old_password = attrs.get("old_password")
        new_password = attrs.get("new_password")
        confirm_new_password = attrs.get("confirm_new_password")

        if (new_password and confirm_new_password) and (
            new_password != confirm_new_password
        ):
            raise serializers.ValidationError({"password": constant.PASSWORD_NOT_MATCH})
        return attrs


class ResetPasswordSerializer(serializers.Serializer):
    otp = serializers.CharField(min_length=4, write_only=True, required=True)
    new_password = serializers.CharField(min_length=6, write_only=True, required=True)
    confirm_new_password = serializers.CharField(
        min_length=6, write_only=True, required=True
    )

    def validate(self, attrs):
        new_password = attrs.get("new_password")
        confirm_new_password = attrs.get("confirm_new_password")
        if (new_password and confirm_new_password) and (
            new_password != confirm_new_password
        ):
            raise serializers.ValidationError({"password": constant.PASSWORD_NOT_MATCH})
        return attrs


class UserDetailSerializer(serializers.ModelSerializer):
    bonus_available = serializers.SerializerMethodField()

    class Meta:
        model = User
        exclude = ["password", "groups", "user_permissions"]

    def get_bonus_available(self, obj):
        return obj.bonus_available


class DeleteUserSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False)
    password = serializers.CharField(required=False)
    user_id = serializers.CharField(required=False)

    def validate(self, data):
        user = User.objects.filter(
            id=data.get("user_id"), phone=data.get("phone")
        ).first()
        if not user:
            raise serializers.ValidationError({"details": "Aucun utilisateur trouver"})
        if not user.check_password(data.get("password")):
            raise serializers.ValidationError({"password": "Mot de passe incorrect"})
        return data


class UpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
        ]


class RefreshObtainSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ValidateOtpSerializer(serializers.Serializer):
    otp = serializers.CharField()


class SmallUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email"]


class SmallBotUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramUser
        fields = ["id", "first_name", "last_name", "email"]


class TelegramUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramUser
        # fields = "__all__"
        exclude = ["is_block"]
