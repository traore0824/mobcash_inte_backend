from django.urls import path
from . import views

urlpatterns = [
    path("connect-pro-webhook", views.ConnectProWebhook.as_view()),
    path("user-phone", views.RegisterOrGetUserPhone.as_view(), name="user-phone"),
]
