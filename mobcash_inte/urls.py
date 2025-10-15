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
    path("plateform", views.CreateAppName.as_view())
]
