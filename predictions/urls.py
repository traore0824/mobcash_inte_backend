from django.urls import path

from predictions.views import PredictionSettingsPublicView, TodayPredictionsView

urlpatterns = [
    path("today/", TodayPredictionsView.as_view(), name="predictions-today"),
    path("settings/", PredictionSettingsPublicView.as_view(), name="predictions-settings"),
]
