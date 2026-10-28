from rest_framework import serializers

from predictions.models import Competition, Fixture, Prediction, PredictionSettings


class CompetitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Competition
        fields = ("id", "slug", "name", "country", "logo", "priority")


class TeamMiniSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    logo = serializers.CharField(allow_blank=True)


class PredictionCardSerializer(serializers.ModelSerializer):
    competition = CompetitionSerializer(source="fixture.competition", read_only=True)
    home = serializers.SerializerMethodField()
    away = serializers.SerializerMethodField()
    status = serializers.CharField(source="fixture.status")
    status_label = serializers.SerializerMethodField()
    kickoff_at = serializers.DateTimeField(source="fixture.kickoff_at")
    score_home = serializers.IntegerField(source="fixture.score_home", allow_null=True)
    score_away = serializers.IntegerField(source="fixture.score_away", allow_null=True)
    minute = serializers.IntegerField(source="fixture.minute", allow_null=True)
    outcome_label = serializers.SerializerMethodField()
    best_pari = serializers.SerializerMethodField()

    class Meta:
        model = Prediction
        fields = (
            "id",
            "competition",
            "home",
            "away",
            "status",
            "status_label",
            "kickoff_at",
            "score_home",
            "score_away",
            "minute",
            "p_home",
            "p_draw",
            "p_away",
            "best_market",
            "best_market_label",
            "best_market_prob",
            "best_pari",
            "confidence_level",
            "outcome",
            "outcome_label",
            "prediction_date",
        )

    def get_home(self, obj):
        t = obj.fixture.home
        return {"id": t.id, "name": t.name, "logo": t.logo}

    def get_away(self, obj):
        t = obj.fixture.away
        return {"id": t.id, "name": t.name, "logo": t.logo}

    def get_status_label(self, obj):
        fx = obj.fixture
        if fx.status == Fixture.Status.FINISHED:
            return "FT"
        if fx.status == Fixture.Status.LIVE:
            return f"{fx.minute}'" if fx.minute else "LIVE"
        if fx.status == Fixture.Status.POSTPONED:
            return "Reporté"
        if fx.status == Fixture.Status.CANCELLED:
            return "Annulé"
        return "NS"

    def get_outcome_label(self, obj):
        return {
            Prediction.Outcome.WON: "Gagné",
            Prediction.Outcome.LOST: "Perdu",
            Prediction.Outcome.VOID: "Annulé",
            Prediction.Outcome.PENDING: None,
        }.get(obj.outcome)

    def get_best_pari(self, obj):
        return {
            "label": obj.best_market_label,
            "market": obj.best_market,
            "probability": obj.best_market_prob,
        }


class PredictionAdminSerializer(PredictionCardSerializer):
    """Carte prono enrichie pour la consultation depuis l'admin."""

    fixture_id = serializers.IntegerField(source="fixture.id", read_only=True)
    round_name = serializers.CharField(source="fixture.round_name", read_only=True)
    published_at = serializers.DateTimeField(read_only=True)
    settled_at = serializers.DateTimeField(read_only=True)
    locked_at = serializers.DateTimeField(read_only=True)
    model_version = serializers.SerializerMethodField()

    class Meta(PredictionCardSerializer.Meta):
        fields = PredictionCardSerializer.Meta.fields + (
            "fixture_id",
            "round_name",
            "is_published",
            "published_at",
            "locked_at",
            "settled_at",
            "model_version",
        )

    def get_model_version(self, obj):
        return obj.model_version.name if obj.model_version_id else None


class PublicSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PredictionSettings
        fields = ("kill_switch", "disclaimer_version", "disclaimer_text")
