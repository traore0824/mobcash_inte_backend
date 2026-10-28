from django.db import models
from django.utils import timezone


class Competition(models.Model):
    provider_id = models.PositiveIntegerField(unique=True)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    country = models.CharField(max_length=80, blank=True)
    logo = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=100)
    season = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["priority", "name"]

    def __str__(self):
        return self.name


class Team(models.Model):
    provider_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=120)
    short_name = models.CharField(max_length=40, blank=True)
    logo = models.URLField(blank=True)
    country = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Fixture(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "À venir"
        LIVE = "live", "En direct"
        FINISHED = "finished", "Terminé"
        POSTPONED = "postponed", "Reporté"
        CANCELLED = "cancelled", "Annulé"

    provider_id = models.PositiveIntegerField(unique=True)
    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="fixtures"
    )
    home = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="home_fixtures")
    away = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="away_fixtures")
    kickoff_at = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True
    )
    minute = models.PositiveSmallIntegerField(null=True, blank=True)
    score_home = models.PositiveSmallIntegerField(null=True, blank=True)
    score_away = models.PositiveSmallIntegerField(null=True, blank=True)
    round_name = models.CharField(max_length=80, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kickoff_at"]
        indexes = [
            models.Index(fields=["kickoff_at", "status"]),
            models.Index(fields=["competition", "kickoff_at"]),
        ]

    def __str__(self):
        return f"{self.home} vs {self.away}"

    @property
    def is_today(self):
        local = timezone.localtime(self.kickoff_at)
        return local.date() == timezone.localdate()


class ModelVersion(models.Model):
    name = models.CharField(max_length=80)
    trained_at = models.DateTimeField(auto_now_add=True)
    params = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    artifact_path = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-trained_at"]

    def __str__(self):
        return f"{self.name} ({self.trained_at:%Y-%m-%d})"


class Prediction(models.Model):
    class Confidence(models.TextChoices):
        LOW = "low", "Faible"
        MEDIUM = "medium", "Moyen"
        HIGH = "high", "Élevé"

    class Outcome(models.TextChoices):
        PENDING = "pending", "En attente"
        WON = "won", "Gagné"
        LOST = "lost", "Perdu"
        VOID = "void", "Annulé"

    fixture = models.OneToOneField(
        Fixture, on_delete=models.CASCADE, related_name="prediction"
    )
    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="predictions",
    )
    p_home = models.FloatField()
    p_draw = models.FloatField()
    p_away = models.FloatField()
    best_market = models.CharField(max_length=40)
    best_market_label = models.CharField(max_length=80)
    best_market_prob = models.FloatField()
    confidence_level = models.CharField(
        max_length=10, choices=Confidence.choices, default=Confidence.MEDIUM
    )
    markets = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    prediction_date = models.DateField(db_index=True)
    outcome = models.CharField(
        max_length=10, choices=Outcome.choices, default=Outcome.PENDING, db_index=True
    )
    settled_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=True)
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Masqué côté users et ignoré par le pipeline (suppression admin)",
    )

    class Meta:
        ordering = ["fixture__competition__priority", "fixture__kickoff_at"]
        indexes = [
            models.Index(fields=["prediction_date", "is_published"]),
        ]

    def __str__(self):
        return f"{self.fixture} — {self.best_market_label}"

    @property
    def is_locked(self):
        return self.locked_at is not None


class PredictionSettings(models.Model):
    """Singleton de configuration du module."""

    kill_switch = models.BooleanField(
        default=False, help_text="Désactive le module analyses pour les clients"
    )
    auto_publish = models.BooleanField(default=True)
    disclaimer_version = models.CharField(max_length=20, default="1.0")
    disclaimer_text = models.TextField(blank=True, default="")
    sync_interval_hours = models.PositiveSmallIntegerField(default=3)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Prediction settings"
        verbose_name_plural = "Prediction settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Prediction settings"
