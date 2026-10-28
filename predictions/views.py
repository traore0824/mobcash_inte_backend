from collections import OrderedDict

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from mobcash_inte.helpers import user_has_recent_accepted_transaction
from predictions.models import Fixture, Prediction, PredictionSettings
from predictions.serializers import PredictionCardSerializer, PublicSettingsSerializer

ACTIVITY_REQUIRED_MSG = (
    "Pour voir les pronos, effectuez un dépôt ou un retrait au cours des 7 derniers jours."
)


class TodayPredictionsView(APIView):
    """Liste des pronos du jour, groupés par championnat (UI type EventIA)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        settings = PredictionSettings.get_solo()
        if settings.kill_switch:
            return Response(
                {"detail": "Module analyses temporairement désactivé.", "groups": []},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not user_has_recent_accepted_transaction(request.user, days=7):
            return Response(
                {
                    "date": timezone.localdate().isoformat(),
                    "count": 0,
                    "groups": [],
                    "locked": True,
                    "code": "activity_required",
                    "detail": ACTIVITY_REQUIRED_MSG,
                }
            )

        today = timezone.localdate()
        qs = (
            Prediction.objects.filter(
                prediction_date=today,
                is_published=True,
                is_deleted=False,
                fixture__competition__is_active=True,
                fixture__status__in=[
                    Fixture.Status.SCHEDULED,
                    Fixture.Status.LIVE,
                    Fixture.Status.FINISHED,
                    Fixture.Status.POSTPONED,
                    Fixture.Status.CANCELLED,
                ],
            )
            .select_related(
                "fixture",
                "fixture__home",
                "fixture__away",
                "fixture__competition",
            )
            .order_by(
                "fixture__competition__priority",
                "fixture__kickoff_at",
            )
        )

        groups: OrderedDict[str, dict] = OrderedDict()
        for pred in qs:
            comp = pred.fixture.competition
            key = comp.slug
            if key not in groups:
                groups[key] = {
                    "competition": {
                        "id": comp.id,
                        "slug": comp.slug,
                        "name": comp.name,
                        "logo": comp.logo,
                    },
                    "predictions": [],
                }
            groups[key]["predictions"].append(PredictionCardSerializer(pred).data)

        return Response(
            {
                "date": today.isoformat(),
                "count": qs.count(),
                "unlocked": user_has_recent_accepted_transaction(request.user, days=7),
                "groups": list(groups.values()),
            }
        )


class PredictionSettingsPublicView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(PublicSettingsSerializer(PredictionSettings.get_solo()).data)
