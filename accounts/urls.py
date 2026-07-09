from django.urls import path

from . import views
app_name="auth"
urlpatterns = [
    path("registration", views.registration, name="registration"),
    path("activation", views.account_activation),
    path("logout", views.logout),
    path("login", views.login, name="login"),
    path("change_password", views.change_password),
    path("send_otp", views.send_otp),
    path("send_otp_whatsapp", views.send_otp_whatsapp),
    path("reset_password", views.reset_password),
    path("whatsapp-phone", views.update_whatsapp_phone),
    path("sms-phone", views.update_sms_phone),
    path("telegram-link", views.telegram_link),
    path("telegram-status", views.telegram_status),
    path("telegram-username", views.update_telegram_username),
    path("telegram-webhook", views.telegram_webhook),
    path("edit", views.edit_user_infos),
    path("delete_account", views.delete_account),
    path("me", views.user_detail),
    path("refresh", views.refresh_token),
    path("validate_otp", views.validate_otp),
    path("admin/user/delete", views.delete_account_by_admin),
    path("users", views.ListUser.as_view()),
    path("users/block/block", views.BlockUserViews.as_view()),
    path("users/block/deblock", views.BlockUserViews.as_view()),
    path("verify-user", views.verify_user),
    path("check-user-account-status", views.check_user_account_status),
    path(
        "telegram-user", views.RegisterOrGetTelegramUser.as_view(), name="telegram-user"
    ),
    path("telegram-users-list", views.ListBotUser.as_view()),
    path("verify-bot-user", views.VerifyTelegramUser.as_view(), name="verify-bot-user"),
    path("user-to-partner", views.UserToPartner.as_view(), name="user-to-partner"),
    path("google", views.google_auth, name="google-auth"),
]
