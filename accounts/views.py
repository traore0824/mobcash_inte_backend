import secrets
from django.shortcuts import render
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db.models import Q
from django.core.validators import validate_email
from django.contrib.auth.hashers import check_password
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import api_view, permission_classes, APIView
from dateutil.relativedelta import relativedelta
import constant
from django.conf.urls import handler404
from .models import TelegramUser, User
import os
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from .serializers import (
    RefreshObtainSerializer,
    TelegramUserSerializer,
    UpdateUserSerializer,
    UserDetailSerializer,
    UserRegistrationSerializer,
    AccountActivationSerializer,
    LoginSerializer,
    ChangePasswordSerializer,
    ResetPasswordSerializer,
    DeleteUserSerializer,
    ValidateOtpSerializer,
)
from .helpers import CustomPagination, create_otp, send_mails
from mobcash_inte.whatsapp_service import (
    is_whatsapp_enabled,
    normalize_whatsapp_phone,
    send_whatsapp_message,
    send_whatsapp_to_user,
    validate_whatsapp_phone,
)
from mobcash_inte.telegram_service import (
    get_telegram_link,
    is_telegram_enabled,
    link_telegram_to_user,
    send_telegram_message,
    validate_telegram_username,
)
from mobcash_inte.sms_service import is_sms_enabled, send_sms_message, _get_user_sms_phone
from mobcash_inte.models import Setting

from django.contrib.gis.geoip2 import GeoIP2
from rest_framework_simplejwt.token_blacklist.models import (
    OutstandingToken,
    BlacklistedToken,
)


def blacklist_user_tokens(user):
    tokens = OutstandingToken.objects.filter(user=user)
    for token in tokens:
        try:
            BlacklistedToken.objects.get_or_create(token=token)
        except:
            continue


# Create your views here.


def save_user_location(request):
    g = GeoIP2()
    remote_addr = request.META.get("HTTP_X_FORWARDED_FOR")
    if remote_addr:
        address = remote_addr.split(",")[-1].strip()
    else:
        address = request.META.get("REMOTE_ADDR")
        # Country  name
    return g.country_name(address)
    # City name


@api_view(["POST"])
def registration(request):
    serializer = UserRegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(
        UserRegistrationSerializer(user).data, status=status.HTTP_201_CREATED
    )



@api_view(["POST"])
def account_activation(request):
    serializer = AccountActivationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    otp = serializer.validated_data.get("otp")
    user = User.objects.filter(otp=otp).first()
    if not user:
        return Response(
            {
                "success": False,
                "details": "Invalid otp",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    user.is_active = True
    user.otp = None
    user.save()
    return Response(UserRegistrationSerializer(user).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    serializer = RefreshObtainSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    refresh_token = serializer.validated_data.get("refresh")
    token = RefreshToken(refresh_token)
    token.blacklist()

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
def login(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email_or_phone = serializer.validated_data.get("email_or_phone")
    email = None
    phone = None
    try:
        validate_email(email_or_phone)
        email = email_or_phone
    except Exception as e:
        try:
            int(email_or_phone)
            phone = email_or_phone
        except Exception as e:
            pass
    password = serializer.validated_data.get("password")

    if email:
        user = User.objects.filter(email=email, is_delete=False).first()
    else:
        user = User.objects.filter(phone=phone, is_delete=False).first()
    if not user:
        return Response(
            {
                "success": False,
                "details": constant.INVALID_EMAIL_PASSWORD,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if user.is_delete:
        return Response(
            {"success": False, "details": f"{constant.INVALID_EMAIL_PASSWORD}"}
        )
    if user.is_block:
        return Response(
            {"details": "Votre compte est bloqué pour fraude "},
            status=status.HTTP_400_BAD_REQUEST,
        )
    auth_user = authenticate(username=user.username, password=password)

    if auth_user is None:
        return Response(
            {
                "success": False,
                "details": constant.INVALID_EMAIL_PASSWORD,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    # user.country = save_user_location(request)
    user.save()
    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "exp": timezone.datetime.fromtimestamp(refresh["exp"]).isoformat(),
            "data": UserDetailSerializer(user).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    new_password = serializer.validated_data.get("new_password")
    old_password = serializer.validated_data.get("old_password")
    user = request.user
    if not user.check_password(old_password):
        return Response(
            {"success": False, "details": "OLD_PASSWORD_IS_INCORRECT"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user.set_password(new_password)
    user.save()
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
def send_otp(request):
    email = request.data.get("email")
    user = User.objects.filter(email=email).first()
    if not user:
        return Response(status=status.HTTP_200_OK)
    otp = create_otp()
    user.otp = otp
    user.otp_created_at = timezone.now() + relativedelta(minutes=2)
    user.save()
    if user:
        response = send_mails(
            subject="Réinitialisation de mot de passe",
            to_email=user.email,
            template_name="reset_password.html",
            context={"otp": otp},
        )
        print(f"{response}")
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
def validate_otp(request):
    serializer = ValidateOtpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    otp = serializer.validated_data.get("otp")
    user = User.objects.filter(otp=otp, otp_created_at__gt=timezone.now()).first()

    if not user:
        return Response(
            {"success": False, "details": constant.INVALID_OTP},
            status=status.HTTP_404_NOT_FOUND,
        )
    user.otp_is_valid = True
    user.save()
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
def reset_password(request):
    serializer = ResetPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    otp = serializer.validated_data.get("otp")
    new_password = serializer.validated_data.get("new_password")
    user = User.objects.filter(otp=otp).first()
    if not user:
        return Response(
            {
                "success": False,
                "details": "User not found !",
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    user.set_password(new_password)
    user.otp = None
    user.save()
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
def send_otp_whatsapp(request):
    email = request.data.get("email")
    user = User.objects.filter(email=email).first()
    if not user:
        return Response(status=status.HTTP_200_OK)
    if not is_whatsapp_enabled():
        return Response(
            {"success": False, "details": "WhatsApp non activé"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not user.user_whatsapp_phone:
        return Response(
            {"success": False, "details": "Aucun numéro WhatsApp enregistré"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    otp = create_otp()
    user.otp = otp
    user.otp_created_at = timezone.now() + relativedelta(minutes=2)
    user.save()
    result = send_whatsapp_message(
        user.user_whatsapp_phone,
        f"*Réinitialisation de mot de passe*\n\nVotre code OTP : *{otp}*\n\nValide 2 minutes.",
    )
    if not result.get("success"):
        return Response(
            {"success": False, "details": "Échec envoi WhatsApp"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def check_whatsapp_phone(request):
    phone = request.data.get("user_whatsapp_phone") or request.data.get("phone")
    if not phone:
        return Response(
            {"success": False, "message": "INVALID_PHONE"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not is_whatsapp_enabled():
        return Response(
            {"success": False, "message": "WHATSAPP_DISABLED"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    validation = validate_whatsapp_phone(phone)
    if not validation.get("exists"):
        return Response(
            {"success": False, "message": "NUMBER_NOT_ON_WHATSAPP"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    normalized = normalize_whatsapp_phone(phone)
    return Response(
        {
            "success": True,
            "exists": True,
            "user_whatsapp_phone": normalized,
        }
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def update_whatsapp_phone(request):
    phone = request.data.get("user_whatsapp_phone") or request.data.get("whatsapp")
    user = request.user
    if phone in (None, ""):
        user.user_whatsapp_phone = None
        user.whatsapp_verified = False
        user.save()
        return Response({"success": True, "user_whatsapp_phone": None, "whatsapp_verified": False})
    if not is_whatsapp_enabled():
        return Response(
            {"success": False, "message": "WHATSAPP_DISABLED"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    validation = validate_whatsapp_phone(phone)
    if not validation.get("exists"):
        return Response(
            {"success": False, "message": "NUMBER_NOT_ON_WHATSAPP"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    normalized = normalize_whatsapp_phone(phone)
    user.user_whatsapp_phone = normalized
    user.whatsapp_verified = True
    user.save()
    return Response(
        {
            "success": True,
            "user_whatsapp_phone": normalized,
            "whatsapp_verified": True,
        }
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def update_sms_phone(request):
    user = request.user
    phone = request.data.get("phone")

    if phone in (None, ""):
        user.sms_verified = False
        user.save()
        return Response({"success": True, "sms_verified": False})

    if not is_sms_enabled():
        return Response(
            {"success": False, "details": "SMS non activé"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.phone = phone
    user.save()

    to_phone = _get_user_sms_phone(user)
    if not to_phone:
        return Response(
            {"success": False, "details": "Numéro invalide"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = send_sms_message(
        to_phone,
        "Votre numéro BLAFFA est confirmé. Vous recevrez vos alertes par SMS.",
    )
    if not result.get("success"):
        return Response(
            {"success": False, "details": "Échec envoi SMS"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    user.sms_verified = True
    user.save()
    return Response(
        {
            "success": True,
            "phone": user.phone,
            "sms_verified": True,
        }
    )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def telegram_link(request):
    if not is_telegram_enabled():
        return Response(
            {"success": False, "details": "Telegram non activé"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    link = get_telegram_link(request.user.id)
    return Response(
        {
            "success": True,
            "link": link or "",
            "telegram_verified": request.user.telegram_verified,
        }
    )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def telegram_status(request):
    return Response(
        {
            "success": True,
            "telegram_verified": request.user.telegram_verified,
            "user_telegram_username": request.user.user_telegram_username,
        }
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def update_telegram_username(request):
    username = request.data.get("user_telegram_username") or request.data.get("telegram")
    user = request.user
    if username in (None, ""):
        user.user_telegram_username = None
        user.user_telegram_chat_id = None
        user.telegram_verified = False
        user.save()
        return Response({"success": True, "telegram_verified": False})

    if not is_telegram_enabled():
        return Response(
            {"success": False, "details": "Telegram non activé"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    validation = validate_telegram_username(username)
    if not validation.get("exists"):
        return Response(
            {
                "success": False,
                "details": "Démarrez d'abord le bot Telegram",
                "link": get_telegram_link(user.id),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.user_telegram_username = validation.get("username")
    user.user_telegram_chat_id = validation.get("chat_id")
    user.telegram_verified = True
    user.save()
    send_telegram_message(
        user.user_telegram_chat_id,
        "✅ Votre compte est connecté à Telegram.\n\n"
        "Vous recevrez ici vos notifications de transactions et les annonces importantes.",
    )
    return Response(
        {
            "success": True,
            "user_telegram_username": user.user_telegram_username,
            "telegram_verified": True,
        }
    )


@api_view(["POST"])
def telegram_webhook(request):
    if not is_telegram_enabled():
        return Response({"ok": True})

    message = request.data.get("message") or {}
    text = message.get("text") or ""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    username = chat.get("username")

    if text.startswith("/start link_") and chat_id:
        link_token = text.replace("/start link_", "").strip()
        user = User.objects.filter(id=link_token).first()
        if user:
            link_telegram_to_user(user, chat_id, username)
            send_telegram_message(
                chat_id,
                "✅ Votre compte est connecté à Telegram.\n\n"
                "Vous recevrez ici vos notifications de transactions et les annonces importantes.",
            )

    return Response({"ok": True})


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def edit_user_infos(request):
    user_id = request.GET.get("user_id")
    if user_id and request.user.is_staff:
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
    else:
        user = request.user
    serializer = UpdateUserSerializer(instance=user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def delete_account(request):
    serializer = DeleteUserSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    phone = serializer.validated_data.get("phone")
    user = User.objects.filter(phone=phone).first()
    if not user:
        return Response(
            {"success": False, "details": "Invalid phone number !"},
            status=status.HTTP_404_NOT_FOUND,
        )
    if user.phone != phone:
        return Response(
            {"success": False, "details": "You can't delete this account"},
            status=status.HTTP_403_FORBIDDEN,
        )
    user.is_delete = True
    user.save()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def delete_account_by_admin(request):
    serializer = DeleteUserSerializer(data=request.data)
    serializer.is_valid()
    password = serializer.validated_data.get("password")
    if not password:
        return Response(
            {"success": False, "details": "password is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user_id = serializer.validated_data.get("user_id")
    if not user_id:
        return Response(
            {"success": False, "details": "user_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = User.objects.filter(id=user_id).first()
    if not user:
        return Response(
            {"success": False, "details": "user not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    if not request.user.check_password(password):
        return Response(
            {"success": False, "details": "Inccorrect password !"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user.is_delete = True
    user.save()
    return Response(status=status.HTTP_204_NO_CONTENT)


class ListUser(generics.ListAPIView):
    serializer_class = UserDetailSerializer
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["is_block"]
    search_fields = [
        "username",
        "email",
        "phone",
        "first_name",
        "last_name",
        "referral_code",
        "referrer_code",
    ]

    def get_queryset(self):
        return User.objects.all().order_by("-date_joined")


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def user_detail(request):
    user_id = request.GET.get("user_id")
    if user_id and request.user.is_staff:
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
    else:
        user = request.user
    user_infos = UserDetailSerializer(user).data
    return Response(user_infos, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def verify_user(request):
    reject_account_reason = request.data.get("reject_account_reason", None)
    user_status = request.data.get("status")
    user_id = request.data.get("user_id")
    user = User.objects.filter(id=user_id).first()
    if not user:
        return Response(status=status.HTTP_404_NOT_FOUND)
    if user_status == "reject" and reject_account_reason is None:
        return Response(
            {"reject_account_reason": "reject_account_reason is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user.status = user_status
    user.reject_account_reason = reject_account_reason
    user.save()
    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def check_user_account_status(request):
    user_id = request.data.get("user_id")
    user = User.objects.filter(id=user_id).first()
    if not user:
        return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(
        {"is_verify": True if user.status == "verify" else False},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def refresh_token(request):
    try:
        serializer = RefreshObtainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data.get("refresh", None)
        refresh = RefreshToken(refresh_token)
        user_id = refresh.get("user_id")
        user = User.objects.filter(id=user_id, is_block=False).first()
        if not user:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "exp": timezone.datetime.fromtimestamp(refresh["exp"]).isoformat(),
            }
        )
    except TokenError as e:
        return Response({"error": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class BlockUserViews(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        user_id = self.request.data.get("user_id")
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not user.is_block:
            user.is_block = True
            user.save()
            blacklist_user_tokens(user)
            return Response({"blocked": True}, status=status.HTTP_200_OK)
        else:
            user.is_block = False
            user.save()
            return Response({"blocked": False}, status=status.HTTP_200_OK)


def generate_api_keys() -> dict:
    public_key = "pk_live_" + secrets.token_urlsafe()
    secret_key = "sk_live_" + secrets.token_urlsafe()
    return {"public_key": public_key, "secret_key": secret_key}


# class NamedUserPartner(APIView):
#     permission_classes = [permissions.IsAdminUser]
#     def post(self, request, *args, **kwargs):
#         user_id = self.request.GET.get("user_id")
#         user = User.objects.filter(id=user_id).first()
#         if not user:
#             return Response({"details": "User not found"}, status=status.HTTP_400_BAD_REQUEST)
#         if not user.is_partner:
#             user.is_partner = True
#             key_data = generate_api_keys()
#             user.secret_key = key_data.get("secret_key")
#             user.public_key = key_data.get("public_key")
#             user.save()
#         data = UserInfosSerializer(user).data
#         data["secret_key"] = user.secret_key
#         data["public_key"] =  user.public_key
#         return Response(data)


class UserToPartner(APIView):
    """
    POST /auth/user-to-partner?user_id={uuid}
    Réservé aux admins. Active un utilisateur comme partenaire
    et génère (ou retourne) sa paire de clés API.
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        user_id = request.GET.get("user_id")
        if not user_id:
            return Response(
                {"details": "user_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response(
                {"details": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not user.is_partner:
            user.is_partner = True
            key_data = generate_api_keys()
            user.secret_key = key_data.get("secret_key")
            user.public_key = key_data.get("public_key")
            user.save(update_fields=["is_partner", "secret_key", "public_key"])

        return Response(
            {
                "id": str(user.id),
                "email": user.email,
                "is_partner": user.is_partner,
                "public_key": user.public_key,
                "secret_key": user.secret_key,
            },
            status=status.HTTP_200_OK,
        )


class RegisterOrGetTelegramUser(APIView):
    def post(self, request):
        telegram_user_id = request.data.get("telegram_user_id")
        if not telegram_user_id:
            return Response(
                {"error": "telegram_user_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, created = TelegramUser.objects.get_or_create(
            telegram_user_id=telegram_user_id,
            defaults={
                "first_name": request.data.get("first_name"),
                "last_name": request.data.get("last_name"),
                "email": request.data.get("email"),
            },
        )

        # 🔁 Si l'utilisateur existe, mettre à jour si les valeurs sont différentes
        if not created:
            updated = False
            for field in ["first_name", "last_name", "email"]:
                new_value = request.data.get(field)
                if new_value is not None and getattr(user, field) != new_value:
                    setattr(user, field, new_value)
                    updated = True
            if updated:
                user.save()

        serializer = TelegramUserSerializer(user)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED,
        )


class ListBotUser(generics.ListAPIView):
    serializer_class = TelegramUserSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["is_block"]
    search_fields = ["telegram_user_id", "first_name", "last_name", "email"]
    queryset = TelegramUser.objects.all()


class VerifyTelegramUser(APIView):
    def get(self, request, *args, **kwargs):
        telegram_user_id = self.request.GET.get("telegram_user_id")
        user = TelegramUser.objects.filter(telegram_user_id=telegram_user_id).first()
        if user:
            return Response({"user_exist": True})
        return Response({"user_exist": False})


def custom_404(request, exception):
    return render(request, "404.html", status=404)


handler404 = custom_404


@api_view(["POST"])
def google_auth(request):
    """
    Authentification via Google OAuth.

    Reçoit un id_token Google depuis le frontend (web ou mobile),
    le vérifie, puis connecte ou crée le compte utilisateur.

    Body: { "id_token": "<google_id_token>" }
    Retourne: { refresh, access, exp, data } — même format que /auth/login
    """
    token = request.data.get("id_token")
    access_token = request.data.get("access_token")

    if not token and not access_token:
        return Response(
            {"success": False, "details": "id_token or access_token is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Si on reçoit un access_token Google (flow implicit web),
    # on récupère les infos user directement depuis l'API Google
    if access_token and not token:
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(
                f"https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            with urllib.request.urlopen(req) as response_google:
                import json as json_module
                google_info = json_module.loads(response_google.read().decode())
        except Exception as e:
            return Response(
                {"success": False, "details": "Invalid or expired Google access_token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = google_info.get("email")
        if not email:
            return Response(
                {"success": False, "details": "Email not found in Google token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not google_info.get("email_verified", False):
            return Response(
                {"success": False, "details": "Google email not verified"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        first_name = google_info.get("given_name", "")
        last_name = google_info.get("family_name", "")

    else:
        # Flow id_token classique
        allowed_client_ids = [
            cid for cid in [
                os.getenv("GOOGLE_CLIENT_ID_WEB"),
                os.getenv("GOOGLE_CLIENT_ID_ANDROID"),
                os.getenv("GOOGLE_CLIENT_ID_IOS"),
                os.getenv("GOOGLE_CLIENT_ID_WEB_CASHIKA"),
                os.getenv("GOOGLE_CLIENT_ID_ANDROID_CASHIKA"),
                os.getenv("GOOGLE_CLIENT_ID_WEB_SLATER"),
                os.getenv("GOOGLE_CLIENT_ID_ANDROID_SLATER"),
            ] if cid and not cid.startswith("REMPLACER")
        ]

        if not allowed_client_ids:
            return Response(
                {"success": False, "details": "Google OAuth not configured on server"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        google_info = None
        last_error = None
        for client_id in allowed_client_ids:
            try:
                google_info = id_token.verify_oauth2_token(
                    token,
                    google_requests.Request(),
                    client_id,
                )
                break
            except Exception as e:
                last_error = e
                continue

        if google_info is None:
            return Response(
                {"success": False, "details": "Invalid or expired Google token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = google_info.get("email")
        if not email:
            return Response(
                {"success": False, "details": "Email not found in Google token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not google_info.get("email_verified", False):
            return Response(
                {"success": False, "details": "Google email not verified"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        first_name = google_info.get("given_name", "")
        last_name = google_info.get("family_name", "")

    # Chercher ou créer l'utilisateur
    user = User.objects.filter(email=email, is_delete=False).first()

    if user:
        # Utilisateur existant — vérifier qu'il n'est pas bloqué
        if user.is_block:
            return Response(
                {"success": False, "details": "Votre compte est bloqué pour fraude"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        # Nouveau compte via Google — création automatique
        from .serializers import generate_referral_code

        # On construit l'objet sans sauvegarder pour pouvoir set_unusable_password avant
        user = User(
            email=email,
            username=email,
            first_name=first_name,
            last_name=last_name,
            phone="",
            referral_code=generate_referral_code(),
            is_active=True,
        )
        # Aucun mot de passe — connexion uniquement via Google
        user.set_unusable_password()
        user.save()

    # Génération des tokens JWT (même format que /auth/login)
    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "exp": timezone.datetime.fromtimestamp(refresh["exp"]).isoformat(),
            "data": UserDetailSerializer(user).data,
        },
        status=status.HTTP_200_OK,
    )
