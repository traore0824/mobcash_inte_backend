"""
API My Solde — gains estimés, stats par réseau/app, solde approximatif à une date.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Optional, Tuple

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AppName
from mobcash_inte.models import Caisse, CaisseBalanceSnapshot, Setting, Transaction


def _parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _period_bounds(request) -> Tuple[datetime, datetime, str]:
    """
    Retourne (start, end, period_label). end inclus jusqu'à fin de journée, plafonné à maintenant.
    """
    now = timezone.now()
    today = timezone.localdate()
    period = (request.query_params.get("period") or "today").strip().lower()

    if period == "3d":
        start_date = today - timedelta(days=2)
        end_date = today
        label = "3d"
    elif period in ("7d", "week"):
        start_date = today - timedelta(days=6)
        end_date = today
        label = "7d"
    elif period == "custom":
        start_date = _parse_date(request.query_params.get("from")) or today
        end_date = _parse_date(request.query_params.get("to")) or today
        if end_date > today:
            end_date = today
        if start_date > end_date:
            start_date = end_date
        label = "custom"
    else:
        start_date = today
        end_date = today
        label = "today"

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end = timezone.make_aware(datetime.combine(end_date, time.max), tz)
    if end > now:
        end = now
    return start, end, label


def _commission_amounts(setting: Setting):
    dep = Decimal(str(getattr(setting, "deposit_commission_percent", 0) or 0))
    wit = Decimal(str(getattr(setting, "withdrawal_commission_percent", 0) or 0))
    return dep, wit


def _earnings_from_amounts(deposit_sum, withdrawal_sum, dep_pct, wit_pct) -> float:
    d = Decimal(str(deposit_sum or 0)) * dep_pct / Decimal("100")
    w = Decimal(str(withdrawal_sum or 0)) * wit_pct / Decimal("100")
    return float(d + w)


class MySoldeView(APIView):
    """
    GET  /mobcash/my-solde/?period=today|3d|7d|custom&from=YYYY-MM-DD&to=YYYY-MM-DD&balance_at=YYYY-MM-DD
    PATCH /mobcash/my-solde/  { deposit_commission_percent, withdrawal_commission_percent }
    """

    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        setting = Setting.objects.first()
        if not setting:
            return Response(
                {"error": "Settings introuvables"},
                status=status.HTTP_404_NOT_FOUND,
            )

        start, end, period = _period_bounds(request)
        dep_pct, wit_pct = _commission_amounts(setting)

        accepted = Transaction.objects.filter(
            status="accept",
            created_at__gte=start,
            created_at__lte=end,
            type_trans__in=["deposit", "withdrawal"],
        )

        totals = accepted.aggregate(
            deposit_count=Count("id", filter=Q(type_trans="deposit")),
            withdrawal_count=Count("id", filter=Q(type_trans="withdrawal")),
            deposit_amount=Sum("amount", filter=Q(type_trans="deposit")),
            withdrawal_amount=Sum("amount", filter=Q(type_trans="withdrawal")),
        )
        deposit_amount = int(totals["deposit_amount"] or 0)
        withdrawal_amount = int(totals["withdrawal_amount"] or 0)
        earnings = _earnings_from_amounts(
            deposit_amount, withdrawal_amount, dep_pct, wit_pct
        )

        # Par réseau
        by_network_raw = (
            accepted.values("network_id", "network__name", "network__public_name")
            .annotate(
                deposit_count=Count("id", filter=Q(type_trans="deposit")),
                withdrawal_count=Count("id", filter=Q(type_trans="withdrawal")),
                deposit_amount=Sum("amount", filter=Q(type_trans="deposit")),
                withdrawal_amount=Sum("amount", filter=Q(type_trans="withdrawal")),
                tx_count=Count("id"),
            )
            .order_by("-tx_count")
        )
        by_network = []
        for row in by_network_raw:
            d_amt = int(row["deposit_amount"] or 0)
            w_amt = int(row["withdrawal_amount"] or 0)
            name = (
                row["network__public_name"]
                or row["network__name"]
                or ("Sans réseau" if not row["network_id"] else f"#{row['network_id']}")
            )
            by_network.append(
                {
                    "network_id": row["network_id"],
                    "network_name": name,
                    "deposit_count": row["deposit_count"],
                    "withdrawal_count": row["withdrawal_count"],
                    "deposit_amount": d_amt,
                    "withdrawal_amount": w_amt,
                    "tx_count": row["tx_count"],
                    "earnings": _earnings_from_amounts(d_amt, w_amt, dep_pct, wit_pct),
                }
            )

        # Par app
        by_app_raw = (
            accepted.values("app_id", "app__name")
            .annotate(
                deposit_count=Count("id", filter=Q(type_trans="deposit")),
                withdrawal_count=Count("id", filter=Q(type_trans="withdrawal")),
                deposit_amount=Sum("amount", filter=Q(type_trans="deposit")),
                withdrawal_amount=Sum("amount", filter=Q(type_trans="withdrawal")),
                tx_count=Count("id"),
            )
            .order_by("-tx_count")
        )
        caisses = {
            c.bet_app_id: float(c.solde)
            for c in Caisse.objects.select_related("bet_app").all()
        }
        by_app = []
        for row in by_app_raw:
            d_amt = int(row["deposit_amount"] or 0)
            w_amt = int(row["withdrawal_amount"] or 0)
            name = row["app__name"] or (
                "Sans app" if not row["app_id"] else f"#{row['app_id']}"
            )
            by_app.append(
                {
                    "app_id": str(row["app_id"]) if row["app_id"] else None,
                    "app_name": name,
                    "current_solde": caisses.get(row["app_id"]),
                    "deposit_count": row["deposit_count"],
                    "withdrawal_count": row["withdrawal_count"],
                    "deposit_amount": d_amt,
                    "withdrawal_amount": w_amt,
                    "tx_count": row["tx_count"],
                    "earnings": _earnings_from_amounts(d_amt, w_amt, dep_pct, wit_pct),
                }
            )

        # Apps sans txn sur la période mais avec caisse
        seen_apps = {str(r["app_id"]) for r in by_app if r["app_id"]}
        for app in AppName.objects.all():
            app_key = str(app.id)
            if app_key in seen_apps:
                continue
            if app.id in caisses:
                by_app.append(
                    {
                        "app_id": app_key,
                        "app_name": app.name,
                        "current_solde": caisses.get(app.id),
                        "deposit_count": 0,
                        "withdrawal_count": 0,
                        "deposit_amount": 0,
                        "withdrawal_amount": 0,
                        "tx_count": 0,
                        "earnings": 0.0,
                    }
                )

        # Solde approximatif à une date
        balance_at_date = _parse_date(request.query_params.get("balance_at"))
        balance_at = None
        if balance_at_date:
            tz = timezone.get_current_timezone()
            target = timezone.make_aware(
                datetime.combine(balance_at_date, time.max), tz
            )
            if target > timezone.now():
                target = timezone.now()
            apps_snap = []
            for app in AppName.objects.all():
                snap = (
                    CaisseBalanceSnapshot.objects.filter(
                        bet_app=app, created_at__lte=target
                    )
                    .order_by("-created_at")
                    .first()
                )
                apps_snap.append(
                    {
                        "app_id": str(app.id),
                        "app_name": app.name,
                        "solde": float(snap.solde) if snap else None,
                        "snapshot_at": snap.created_at.isoformat() if snap else None,
                        "found": bool(snap),
                    }
                )
            balance_at = {
                "requested_date": balance_at_date.isoformat(),
                "approximate": True,
                "message": (
                    "Solde approximatif : dernière valeur enregistrée "
                    "à ou avant cette date (après une transaction réussie)."
                ),
                "apps": apps_snap,
            }

        return Response(
            {
                "period": period,
                "from": start.date().isoformat(),
                "to": end.date().isoformat(),
                "commissions": {
                    "deposit_commission_percent": float(dep_pct),
                    "withdrawal_commission_percent": float(wit_pct),
                },
                "summary": {
                    "deposit_count": totals["deposit_count"] or 0,
                    "withdrawal_count": totals["withdrawal_count"] or 0,
                    "tx_count": (totals["deposit_count"] or 0)
                    + (totals["withdrawal_count"] or 0),
                    "deposit_amount": deposit_amount,
                    "withdrawal_amount": withdrawal_amount,
                    "earnings": earnings,
                },
                "by_network": by_network,
                "by_app": by_app,
                "current_caisses": [
                    {
                        "app_id": str(c.bet_app_id),
                        "app_name": c.bet_app.name,
                        "solde": float(c.solde),
                        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                    }
                    for c in Caisse.objects.select_related("bet_app").all()
                ],
                "balance_at": balance_at,
            }
        )

    def patch(self, request, *args, **kwargs):
        setting = Setting.objects.first()
        if not setting:
            return Response(
                {"error": "Settings introuvables"},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = request.data or {}
        updated = []
        for field in ("deposit_commission_percent", "withdrawal_commission_percent"):
            if field in data and data[field] is not None:
                try:
                    value = Decimal(str(data[field]))
                except Exception:
                    return Response(
                        {"error": f"Valeur invalide pour {field}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if value < 0 or value > 100:
                    return Response(
                        {"error": f"{field} doit être entre 0 et 100"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                setattr(setting, field, value)
                updated.append(field)

        if not updated:
            return Response(
                {"error": "Aucun champ commission à mettre à jour"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        setting.save(update_fields=updated)
        return Response(
            {
                "deposit_commission_percent": float(setting.deposit_commission_percent),
                "withdrawal_commission_percent": float(
                    setting.withdrawal_commission_percent
                ),
            }
        )
