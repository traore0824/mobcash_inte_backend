from django.contrib import admin

from predictions.models import (
    Competition,
    Fixture,
    ModelVersion,
    Prediction,
    PredictionSettings,
    Team,
)


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "provider_id", "is_active", "priority", "season")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "provider_id", "country")
    search_fields = ("name",)


@admin.register(Fixture)
class FixtureAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition",
        "home",
        "away",
        "kickoff_at",
        "status",
        "score_home",
        "score_away",
    )
    list_filter = ("status", "competition")
    search_fields = ("home__name", "away__name", "provider_id")
    date_hierarchy = "kickoff_at"


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "fixture",
        "best_market_label",
        "best_market_prob",
        "outcome",
        "prediction_date",
        "is_published",
    )
    list_filter = ("outcome", "confidence_level", "prediction_date", "is_published")
    search_fields = ("fixture__home__name", "fixture__away__name", "best_market_label")
    readonly_fields = ("published_at", "locked_at", "settled_at")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_deleted=False)


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "trained_at", "is_active", "artifact_path")
    list_filter = ("is_active", "name")


@admin.register(PredictionSettings)
class PredictionSettingsAdmin(admin.ModelAdmin):
    list_display = ("kill_switch", "auto_publish", "disclaimer_version", "updated_at")
