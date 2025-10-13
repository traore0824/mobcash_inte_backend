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
    path("reset_password", views.reset_password),
    path("edit", views.edit_user_infos),
    path("delete_account", views.delete_account),
    path("me", views.user_detail),
    path("refresh", views.refresh_token),
    path("validate_otp", views.validate_otp),
    path("admin/user/delete", views.delete_account_by_admin),
    path("users", views.ListUser.as_view()),
    path("admin/name-user", views.NamedAdminUser.as_view()),
    path("users/block/block", views.BlockUserViews.as_view()),
    path("users/block/deblock", views.BlockUserViews.as_view()),
    path("verify-user", views.verify_user),
    path("check-user-account-status", views.check_user_account_status),
    path("user-to-partner", views.NamedUserPartner.as_view()),
]
