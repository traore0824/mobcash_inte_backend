"""
API de consultation des pronostics pour l'admin (staff uniquement).

Contrairement à ``/api/v1/predictions/today/``, ces vues ne sont pas soumises
au verrou « dépôt/retrait des 7 derniers jours » : elles servent uniquement à
visualiser les pronostics générés par le pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.db.models import Count, Q
from rest_framework import permissions
from rest_framework.generics import ListAPIView
from rest_framework.response import Response

from accounts.helpers import CustomPagination
from predictions.models import Prediction
from predictions.serializers import PredictionAdminSerializer


def _parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _as_bool(value: Optional[str]):
    if value is None or value == "":
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


class PredictionAdminListView(ListAPIView):
    """
    GET /mobcash/predictions/?date=YYYY-MM-DD&from=...&to=...&outcome=won
        &competition=<id>&search=<équipe>&published=true&page=1&page_size=20

    Retourne la liste paginée + un résumé (total / gagnés / perdus / en attente).
    """

    permission_classes = [permissions.IsAdminUser]
    serializer_class = PredictionAdminSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        qs = (
            Prediction.objects.select_related(
                "fixture",
                "fixture__home",
                "fixture__away",
                "fixture__competition",
                "model_version",
            )
            .order_by("-prediction_date", "fixture__kickoff_at")
        )

        params = self.request.query_params
        exact_date = _parse_date(params.get("date"))
        from_date = _parse_date(params.get("from"))
        to_date = _parse_date(params.get("to"))

        if exact_date:
            qs = qs.filter(prediction_date=exact_date)
        else:
            if from_date:
                qs = qs.filter(prediction_date__gte=from_date)
            if to_date:
                qs = qs.filter(prediction_date__lte=to_date)

        outcome = (params.get("outcome") or "").strip().lower()
        if outcome in Prediction.Outcome.values:
            qs = qs.filter(outcome=outcome)

        competition = (params.get("competition") or "").strip()
        if competition:
            if competition.isdigit():
                qs = qs.filter(fixture__competition_id=int(competition))
            else:
                qs = qs.filter(fixture__competition__slug=competition)

        published = _as_bool(params.get("published"))
        if published is not None:
            qs = qs.filter(is_published=published)

        search = (params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(fixture__home__name__icontains=search)
                | Q(fixture__away__name__icontains=search)
                | Q(best_market_label__icontains=search)
                | Q(fixture__competition__name__icontains=search)
            )

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        summary = queryset.aggregate(
            total=Count("id"),
            won=Count("id", filter=Q(outcome=Prediction.Outcome.WON)),
            lost=Count("id", filter=Q(outcome=Prediction.Outcome.LOST)),
            pending=Count("id", filter=Q(outcome=Prediction.Outcome.PENDING)),
            void=Count("id", filter=Q(outcome=Prediction.Outcome.VOID)),
            published=Count("id", filter=Q(is_published=True)),
        )
        settled = summary["won"] + summary["lost"]
        summary["win_rate"] = (
            round(summary["won"] * 100 / settled, 1) if settled else None
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data["summary"] = summary
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({"results": serializer.data, "summary": summary})
