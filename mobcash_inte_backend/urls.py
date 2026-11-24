from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from mobcash_inte.betting_cancel_views import (
    ConnectBettingCancelView,
    DeviceCancelJobNextView,
    DeviceCancelJobResultView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("mobcash/", include("mobcash_inte.urls")),
    path("blaffa/", include("mobcash_inte.urls")),
    path("auth/", include("accounts.urls")),
    path("api/v1/predictions/", include("predictions.urls")),
    # Connect → Mobcash Cancel (HMAC) + app device (Bearer)
    path("api/v1/connect/betting-cancel/", ConnectBettingCancelView.as_view()),
    path("api/v1/device/cancel-jobs/next/", DeviceCancelJobNextView.as_view()),
    path(
        "api/v1/device/cancel-jobs/<uuid:uid>/result/",
        DeviceCancelJobResultView.as_view(),
    ),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
