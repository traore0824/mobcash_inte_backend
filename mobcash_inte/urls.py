from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter
from fcm_django.api.rest_framework import FCMDeviceAuthorizedViewSet

router = DefaultRouter()
router.register("devices", FCMDeviceAuthorizedViewSet)
router.register(r"user-phone", views.UserPhoneViewSet, basename="user-phone")
router.register(r"user-app-id", views.IDLinkViews, basename="user-app-id")

app_name = "mobcash_inte"
urlpatterns = [
    path("connect-pro-webhook", views.ConnectProWebhook.as_view()),
    path("feexpay-webhook", views.FeexpayWebhook.as_view()),
    path("", include(router.urls)),
    path("network", views.CreateNetworkView.as_view(), name="network"),
    path("network/<int:pk>", views.DetailsNetworkView.as_view()),
    path("plateform", views.CreateAppName.as_view()),
    path("plateform/<str:pk>", views.DetailAppName.as_view()),
    path("notification", views.NotificationView.as_view()),
    path("delete-notification", views.ReadAllNotificaation.as_view()),
    path("read-notification", views.ReadNotificationView.as_view()),
    path("bot-transaction-deposit", views.BotDepositTransactionViews.as_view()),
    path("bot-transaction-withdrawal", views.BotWithdrawalTransactionViews.as_view()),
    path("transaction-deposit", views.CreateDepositTransactionViews.as_view()),
    path("transaction-withdrawal", views.WithdrawalTransactionViews.as_view()),
    path("transaction-bonus", views.CreateBonusDepositTransactionViews.as_view()),
    path("transaction-reward", views.RewardTransactionViews.as_view()),
    path("reward", views.GetRewardView.as_view()),
    path("bonus", views.GetBonus.as_view()),
    path("create-bonus", views.CreateBonusView.as_view()),
    path("transaction-history", views.HistoryTransactionViews.as_view()),
    path("transaction-detail", views.TransactionDetailView.as_view()),
    path("change-transaction", views.ChangeTransactionStatus.as_view()),
    path("setting", views.SettingViews.as_view()),
    path("validate-version", views.ValidateVersionView.as_view()),
    path("deposit", views.CreateDeposit.as_view()),
    path("list-deposit", views.ListDeposit.as_view()),
    path("caisses", views.ListCaisse.as_view()),
    path("upload", views.UploadFileView.as_view()),
    path("search-user", views.SearchUserBet.as_view()),
    path("coupon", views.CreateCoupon.as_view()),
    path("coupon/<int:pk>", views.CouponDetailAPIView.as_view()),
    path("ann", views.CreateAdvertisementViews.as_view()),
    path("ann/<str:pk>", views.DetailsAdvertisementViews.as_view()),
    path("statistics", views.StatisticsView.as_view()),
    path("balance", views.APIBalanceView.as_view()),
    path("mobcash-balance", views.MobCashBalance.as_view()),
    path("show-transaction-status", views.TransactionStatus.as_view()),
    path("test-views", views.TestAPIViews.as_view()),
    path("recharge-mobcash-balance", views.RechargeMobcashBalanceView.as_view()),
    path("update-caisse-balance", views.UpdateCaisseBalanceView.as_view()),
    path("process-transaction", views.ProcessTransactionView.as_view()),
    path("update-transaction-status", views.UpdateTransactionStatusView.as_view()),
    path("transaction-status-history", views.TransactionStatusHistoryView.as_view()),
    path("change-transaction-status-manuel", views.ChangeTransactionStatusManuelViews.as_view()),
]
