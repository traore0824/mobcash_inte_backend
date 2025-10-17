from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter


router = DefaultRouter()
router.register(r"user-phone", views.UserPhoneViewSet, basename="user-phone")
router.register(r"user-app-id", views.IDLinkViews, basename="user-app-id")

urlpatterns = [
    path("connect-pro-webhook", views.ConnectProWebhook.as_view()),
    path("", include(router.urls)),
    path("network", views.CreateNetworkView.as_view()),
    path("network/<int:pk>", views.CreateNetworkView.as_view()),
    path("plateform", views.CreateAppName.as_view()),
    path("notification", views.NotificationView.as_view()),
    path("delete-notification", views.ReadAllNotificaation.as_view()),
    path("bot-transaction-deposit", views.BotDepositTransactionViews.as_view()),
    path("bot-transaction-withdrawal", views.BotWithdrawalTransactionViews.as_view()),
    path("transaction-deposit", views.CreateDepositTransactionViews.as_view()),
    path("transaction-withdrawal", views.WithdrawalTransactionViews.as_view()),
    path("bonus", views.GetBonus.as_view()),
    path("transaction-history", views.HistoryTransactionViews.as_view()),
    path("change-transaction", views.ChangeTransactionStatus.as_view()),
    path("setting", views.SettingViews.as_view()),
    path("deposit", views.CreateDeposit.as_view()),
    path("list-deposit", views.ListDeposit.as_view()),
    path("caisses",views.ListCaisse.as_view()),
]
