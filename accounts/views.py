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
from rest_framework.decorators import api_view, permission_classes, APIView
from dateutil.relativedelta import relativedelta
import constant

from .models import User
from .serializers import (
    RefreshObtainSerializer,
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
    user = User.objects.filter(email=request.data.get("email"), is_delete=True).first()
    if user:
        user.is_delete = False
        user.save()
    else:
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save(user_app_id=serializer.validated_data.get("user_app_id"))
        otp = create_otp()
        user.otp = otp
        user.save()
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
    auth_user = authenticate(email=user.email, password=password)

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
        return Response(
            {
                "success": False,
                "details": "USER_NOT_FOUND",
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    otp = create_otp()
    user.otp = otp
    user.otp_created_at = timezone.now() + relativedelta(minutes=2)
    user.save()
    if user:
        response = send_mails(
            subject="Réinitialisation de mot de passe",
            to_email=user.email,
            otp=otp,
            template_name="reset_password.html",
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

    def get_queryset(self):
        search_fields = self.request.GET.get("search_fields")
        status = self.request.GET.get("status")

        if search_fields:
            objs = User.objects.filter(
                Q(email__icontains=search_fields)
                | Q(first_name__icontains=search_fields)
                | Q(last_name__icontains=search_fields)
                | Q(referral_code__icontains=search_fields)
            )
        else:
            objs = User.objects.all()
        return objs


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
        else:
            user.is_block = False
            user.save()
        return Response(status=status.HTTP_200_OK)


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
