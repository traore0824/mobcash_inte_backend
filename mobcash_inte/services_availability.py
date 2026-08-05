"""API publique — disponibilité réseaux Mobile Money + applications (chatbot)."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AppName
from mobcash_inte.models import Network, Setting


TYPE_ALIASES = {
    "deposit": "deposit",
    "depot": "deposit",
    "dépôt": "deposit",
    "depots": "deposit",
    "deposits": "deposit",
    "withdrawal": "withdrawal",
    "retrait": "withdrawal",
    "retraits": "withdrawal",
    "withdraw": "withdrawal",
    "withdrawals": "withdrawal",
    "all": "all",
    "tous": "all",
    "tout": "all",
    "toutes": "all",
    "both": "all",
    "les_deux": "all",
    "les deux": "all",
}


def _normalize_type(raw: str) -> str:
    key = (raw or "").strip().lower().replace("-", "_")
    if key in {"les deux", "les_deux"}:
        return "all"
    return TYPE_ALIASES.get(key, "all")


def _norm_label(value: str | None) -> str:
    return (value or "").strip()


def _display_network(net: Network) -> str:
    return _norm_label(net.public_name) or _norm_label(net.name) or "Réseau"


def _display_app(app: AppName) -> str:
    return _norm_label(app.name) or "Application"


def _matches_focus(label: str, name: str, focus: str) -> bool:
    if not focus or focus in {"all", "tous", "tout", "toutes", "*"}:
        return True
    f = focus.lower().strip()
    blob = f"{label} {name}".lower()
    return f in blob or blob in f


def _setting_flags() -> tuple[bool, bool]:
    s = Setting.objects.first()
    if not s:
        return True, True
    return bool(s.deposit_enable), bool(s.withdraw_enable)


def _network_qs():
    return Network.objects.all().order_by("public_name", "name")


def _app_qs(*, include_disabled: bool = False):
    qs = AppName.objects.all()
    if not include_disabled:
        qs = qs.filter(enable=True)
    return qs.order_by("order", "name")


def build_services_availability_response(
    *,
    type_raw: str = "",
    focus_raw: str = "",
) -> tuple[dict[str, Any], int]:
    op = _normalize_type(type_raw)
    focus = (focus_raw or "").strip().lower()
    if focus in {"", "all", "tous", "tout", "toutes", "both", "les deux", "les_deux", "*"}:
        focus = "all"

    include_disabled = focus != "all"

    deposit_on, withdraw_on = _setting_flags()

    networks_avail: list[dict[str, Any]] = []
    networks_unavail: list[dict[str, Any]] = []
    for net in _network_qs():
        label = _display_network(net)
        if not _matches_focus(label, str(net.name or ""), focus):
            continue
        dep_ok = bool(net.active_for_deposit) and deposit_on
        wd_ok = bool(net.active_for_with) and withdraw_on
        item = {
            "name": net.name,
            "public_name": label,
            "enabled": True,
            "active_for_deposit": dep_ok,
            "active_for_withdrawal": wd_ok,
        }
        if op == "deposit":
            (networks_avail if dep_ok else networks_unavail).append(item)
        elif op == "withdrawal":
            (networks_avail if wd_ok else networks_unavail).append(item)
        else:
            if dep_ok or wd_ok:
                networks_avail.append(item)
            else:
                networks_unavail.append(item)

    apps_avail: list[dict[str, Any]] = []
    apps_unavail: list[dict[str, Any]] = []
    for app in _app_qs(include_disabled=include_disabled):
        label = _display_app(app)
        if not _matches_focus(label, str(app.name or ""), focus):
            continue
        enabled = bool(app.enable)
        dep_ok = enabled and bool(app.active_for_deposit) and deposit_on
        wd_ok = enabled and bool(app.active_for_with) and withdraw_on
        item = {
            "name": app.name,
            "public_name": label,
            "enabled": enabled,
            "active_for_deposit": dep_ok,
            "active_for_withdrawal": wd_ok,
        }
        if op == "deposit":
            (apps_avail if dep_ok else apps_unavail).append(item)
        elif op == "withdrawal":
            (apps_avail if wd_ok else apps_unavail).append(item)
        else:
            if dep_ok or wd_ok:
                apps_avail.append(item)
            else:
                apps_unavail.append(item)

    message = _format_message(
        op=op,
        focus=focus,
        deposit_on=deposit_on,
        withdraw_on=withdraw_on,
        networks_avail=networks_avail,
        networks_unavail=networks_unavail,
        apps_avail=apps_avail,
        apps_unavail=apps_unavail,
    )

    return {
        "ok": True,
        "type": op,
        "focus": focus,
        "global": {
            "deposit_enable": deposit_on,
            "withdraw_enable": withdraw_on,
        },
        "networks": {
            "available": networks_avail,
            "unavailable": networks_unavail,
        },
        "apps": {
            "available": apps_avail,
            "unavailable": apps_unavail,
        },
        "message": message,
    }, status.HTTP_200_OK


def _names(items: list[dict[str, Any]]) -> str:
    labels = [str(i.get("public_name") or i.get("name") or "").strip() for i in items]
    labels = [x for x in labels if x]
    if not labels:
        return "aucun"
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} et {labels[1]}"
    return ", ".join(labels[:-1]) + f" et {labels[-1]}"


def _op_label(op: str) -> str:
    if op == "deposit":
        return "dépôt"
    if op == "withdrawal":
        return "retrait"
    return "dépôt et retrait"


def _format_message(
    *,
    op: str,
    focus: str,
    deposit_on: bool,
    withdraw_on: bool,
    networks_avail: list[dict[str, Any]],
    networks_unavail: list[dict[str, Any]],
    apps_avail: list[dict[str, Any]],
    apps_unavail: list[dict[str, Any]],
) -> str:
    if focus != "all":
        if networks_avail or networks_unavail:
            hit = (networks_avail or networks_unavail)[0]
            label = hit.get("public_name") or hit.get("name")
            ok = (
                bool(hit.get("active_for_deposit"))
                if op == "deposit"
                else bool(hit.get("active_for_withdrawal"))
                if op == "withdrawal"
                else bool(hit.get("active_for_deposit") or hit.get("active_for_withdrawal"))
            )
            if not ok or hit.get("enabled") is False:
                return f"Le réseau {label} est momentanément indisponible."
            if op == "deposit":
                return f"Oui, le réseau {label} est disponible pour les dépôts."
            if op == "withdrawal":
                return f"Oui, le réseau {label} est disponible pour les retraits."
            return f"Oui, le réseau {label} est disponible."
        if apps_avail or apps_unavail:
            hit = (apps_avail or apps_unavail)[0]
            label = hit.get("public_name") or hit.get("name")
            ok = (
                bool(hit.get("active_for_deposit"))
                if op == "deposit"
                else bool(hit.get("active_for_withdrawal"))
                if op == "withdrawal"
                else bool(hit.get("active_for_deposit") or hit.get("active_for_withdrawal"))
            )
            if not ok or hit.get("enabled") is False:
                return f"L'application {label} est momentanément indisponible."
            if op == "deposit":
                return f"Oui, {label} est disponible pour les dépôts."
            if op == "withdrawal":
                return f"Oui, {label} est disponible pour les retraits."
            return f"Oui, {label} est disponible."
        return (
            f"Je ne reconnais pas « {focus} » parmi nos réseaux ou applications."
        )

    parts: list[str] = []
    if not deposit_on and op in {"deposit", "all"}:
        parts.append("Les dépôts sont momentanément indisponibles.")
    if not withdraw_on and op in {"withdrawal", "all"}:
        parts.append("Les retraits sont momentanément indisponibles.")
    if networks_avail:
        parts.append(f"Pour les réseaux Mobile Money, on a {_names(networks_avail)}.")
    elif op != "all" or not parts:
        parts.append("Aucun réseau Mobile Money n'est disponible pour le moment.")
    if apps_avail:
        parts.append(f"Côté applications, {_names(apps_avail)}.")
    return " ".join(parts)


class PublicServicesAvailabilityView(APIView):
    """
    GET /public/services-availability?type=deposit|withdrawal|all&q=wave|tous
    Sans authentification — message prêt pour le chatbot MyCustomer.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        body, code = build_services_availability_response(
            type_raw=(
                request.query_params.get("type")
                or request.query_params.get("operation_type")
                or ""
            ).strip(),
            focus_raw=(
                request.query_params.get("q")
                or request.query_params.get("focus")
                or request.query_params.get("name")
                or ""
            ).strip(),
        )
        return Response(body, status=code)
