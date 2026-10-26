"""
AutoPayer — payin (dépôt), payout (retrait), status, networks, webhook.

Sécurité :
- HMAC-SHA256 webhook (compare_digest)
- Idempotence via WebhookLog + select_for_update
- external_id = reference MobCash (traçabilité)
- Montants validés, timeouts HTTP, secrets hors logs
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.cache import cache
from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils import timezone

from integrations.autopayer.client import (
    AutoPayerAPIError,
    AutoPayerConfigError,
    request as ap_request,
)
from mobcash_inte.models import Setting, Transaction

logger = logging.getLogger("mobcash_inte_backend.transactions")

NETWORKS_CACHE_KEY = "autopayer:networks:v1"
NETWORKS_CACHE_TTL = 300  # 5 min


def webhook_secret() -> str:
    try:
        from django.conf import settings as dj_settings

        val = getattr(dj_settings, "AUTOPAYER_WEBHOOK_SECRET", None)
        if val:
            return str(val).strip()
    except Exception:
        pass
    return (os.getenv("AUTOPAYER_WEBHOOK_SECRET") or "").strip()


def autopayer_verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Vérifie X-Webhook-Signature = HMAC-SHA256(body, secret)."""
    secret = webhook_secret()
    if not secret:
        logger.error("[AUTOPAYER] AUTOPAYER_WEBHOOK_SECRET manquant — webhook refusé")
        return False
    if not signature_header:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.strip()
    # Accepter éventuellement le préfixe sha256=
    if provided.lower().startswith("sha256="):
        provided = provided.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def normalize_autopayer_phone(transaction: Transaction) -> str:
    """
    AutoPayer attend un numéro local à 10 chiffres (ex. BJ 01xxxxxxxx).
    On retire l'indicatif pays du Network si présent.
    """
    digits = re.sub(r"\D", "", str(transaction.phone_number or ""))
    network = getattr(transaction, "network", None)
    indication = re.sub(r"\D", "", str(getattr(network, "indication", "") or ""))

    local = digits
    if indication and digits.startswith(indication):
        local = digits[len(indication) :]

    # Garder les 10 derniers chiffres si trop long
    if len(local) > 10:
        local = local[-10:]

    if len(local) != 10:
        raise ValueError(
            f"Téléphone AutoPayer invalide (attendu 10 chiffres), obtenu={local!r}"
        )
    return local


def _safe_amount(transaction: Transaction) -> str:
    try:
        amount = Decimal(str(transaction.amount))
    except (InvalidOperation, TypeError):
        raise ValueError(f"Montant invalide: {transaction.amount}")
    if amount <= 0:
        raise ValueError(f"Montant doit être > 0: {amount}")
    # Entier FCFA
    return str(int(amount))


def autopayer_get_networks(*, force_refresh: bool = False) -> list[dict]:
    """GET /api/aggregator/networks/ — liste + cache Redis."""
    if not force_refresh:
        cached = cache.get(NETWORKS_CACHE_KEY)
        if cached is not None:
            return cached

    payload = ap_request("GET", "/api/aggregator/networks/")
    data = payload.get("data") if isinstance(payload, dict) else None
    if data is None and isinstance(payload, list):
        data = payload
    networks = data if isinstance(data, list) else []
    cache.set(NETWORKS_CACHE_KEY, networks, NETWORKS_CACHE_TTL)
    return networks


def autopayer_resolve_network_uid(transaction: Transaction) -> str:
    """
    Résout le UUID réseau AutoPayer :
    1) Network.autopayer_network_uid si renseigné
    2) Match network_code / network_name vs Network.name / public_name
    """
    network = transaction.network
    if not network:
        raise ValueError("Transaction sans network")

    override = (getattr(network, "autopayer_network_uid", None) or "").strip()
    if override:
        return override

    networks = autopayer_get_networks()
    if not networks:
        raise ValueError("Aucun réseau AutoPayer disponible")

    name = (network.name or "").strip().lower()
    public = (network.public_name or "").strip().lower()

    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    targets = {norm(name), norm(public)} - {""}

    for item in networks:
        code = norm(str(item.get("network_code") or ""))
        nname = norm(str(item.get("network_name") or ""))
        uid = item.get("network_uid")
        if not uid:
            continue
        if code in targets or nname in targets:
            # wave / mtn / moov etc.
            return str(uid)
        # fuzzy contains
        for t in targets:
            if t and (t in code or t in nname or code in t or nname in t):
                return str(uid)

    raise ValueError(
        f"Impossible de mapper le réseau MobCash '{network.name}' vers AutoPayer. "
        f"Renseignez Network.autopayer_network_uid ou alignez les codes."
    )


def _extract_uid(payload: dict) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("uid", "id", "transaction_uid", "reference"):
        val = data.get(key) if isinstance(data, dict) else None
        if val:
            return str(val)
    return None


def _payload_data(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else (payload if isinstance(payload, dict) else {})


def _apply_autopayer_payin_instructions(transaction: Transaction, payload: dict) -> list[str]:
    """
    Mappe la réponse AutoPayer vers les champs MobCash exposés au front :
    - payment_ussd  → transaction.ussd_code
    - payment_url   → transaction.transaction_link (lien HTTP ou numéro Wave)
    - uid           → transaction.public_id
    """
    data = _payload_data(payload)
    updated: list[str] = []

    uid = _extract_uid(payload)
    if uid:
        transaction.public_id = uid
        updated.append("public_id")

    ussd = (data.get("payment_ussd") or "").strip()
    if ussd:
        # CharField max_length=200
        transaction.ussd_code = ussd[:200]
        updated.append("ussd_code")

    pay_url = (data.get("payment_url") or "").strip()
    if pay_url:
        transaction.transaction_link = pay_url
        updated.append("transaction_link")

    comment = (data.get("payment_comment") or "").strip()
    # Audit complet (sans secrets)
    try:
        transaction.connect_pro_response = json.dumps(
            {
                "provider": "autopayer",
                "uid": uid,
                "payment_ussd": ussd or None,
                "payment_url": pay_url or None,
                "payment_comment": comment or None,
                "status": data.get("status"),
            },
            ensure_ascii=False,
            default=str,
        )[:5000]
        updated.append("connect_pro_response")
    except Exception:
        pass

    if updated:
        transaction.save(update_fields=list(dict.fromkeys(updated)))

    logger.info(
        "[AUTOPAYER][PAYIN] instructions ref=%s uid=%s ussd=%s link=%s",
        transaction.reference,
        uid,
        bool(ussd),
        bool(pay_url),
    )
    return updated


def depot_auto_payer(transaction: Transaction) -> dict:
    """POST /api/aggregator/payin/ — encaissement Mobile Money."""
    try:
        phone = normalize_autopayer_phone(transaction)
        amount = _safe_amount(transaction)
        network_uid = autopayer_resolve_network_uid(transaction)
    except (ValueError, AutoPayerConfigError) as exc:
        logger.error("[AUTOPAYER][PAYIN] validation: %s ref=%s", exc, transaction.reference)
        transaction.change_status(
            new_status="error",
            source="API_ERROR",
            data={"error": str(exc)},
            message=str(exc),
        )
        return {"ok": False, "error": str(exc)}

    body = {
        "amount": amount,
        "recipient_phone": phone,
        "network": network_uid,
        "external_id": transaction.reference,
        "objet": f"Depot MobCash {transaction.reference}",
        "commentaire": "",
    }

    try:
        payload = ap_request("POST", "/api/aggregator/payin/", json_body=body)
    except (AutoPayerAPIError, AutoPayerConfigError) as exc:
        logger.error(
            "[AUTOPAYER][PAYIN] échec ref=%s err=%s payload=%s",
            transaction.reference,
            exc,
            getattr(exc, "payload", None),
        )
        transaction.change_status(
            new_status="error",
            source="API_ERROR",
            data=getattr(exc, "payload", {"error": str(exc)}),
            message=str(exc),
        )
        return {"ok": False, "error": str(exc)}

    applied = _apply_autopayer_payin_instructions(transaction, payload)
    data = _payload_data(payload)
    comment = (data.get("payment_comment") or "").strip()
    msg = "Payin AutoPayer initié"
    if comment:
        msg = f"{msg} — {comment[:180]}"

    transaction.change_status(
        new_status="pending",
        source="API_RESPONSE",
        data=payload,
        message=msg,
        extra_fields=applied or None,
    )

    # Push WS pour que le front reçoive ussd_code / transaction_link
    try:
        if transaction.user_id:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            from mobcash_inte.serializers import TransactionDetailsSerializer

            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"private_channel_{transaction.user_id}",
                    {
                        "type": "transaction",
                        "data": TransactionDetailsSerializer(transaction).data,
                    },
                )
    except Exception as exc:
        logger.warning(
            "[AUTOPAYER][PAYIN] WS skip ref=%s err=%s",
            transaction.reference,
            exc,
        )

    uid = transaction.public_id
    logger.info(
        "[AUTOPAYER][PAYIN] OK ref=%s uid=%s ussd=%s link=%s",
        transaction.reference,
        uid,
        bool(transaction.ussd_code),
        bool(transaction.transaction_link),
    )
    return {
        "ok": True,
        "uid": uid,
        "payment_ussd": transaction.ussd_code,
        "payment_url": transaction.transaction_link,
        "data": payload,
    }


def retrait_auto_payer(transaction: Transaction) -> dict:
    """POST /api/aggregator/payout/ — envoi Mobile Money."""
    try:
        phone = normalize_autopayer_phone(transaction)
        amount = _safe_amount(transaction)
        network_uid = autopayer_resolve_network_uid(transaction)
    except (ValueError, AutoPayerConfigError) as exc:
        logger.error("[AUTOPAYER][PAYOUT] validation: %s ref=%s", exc, transaction.reference)
        transaction.change_status(
            new_status="error",
            source="API_ERROR",
            data={"error": str(exc)},
            message=str(exc),
        )
        return {"ok": False, "error": str(exc)}

    body = {
        "amount": amount,
        "recipient_phone": phone,
        "network": network_uid,
        "external_id": transaction.reference,
        "objet": f"Retrait MobCash {transaction.reference}",
        "commentaire": "",
    }

    try:
        payload = ap_request("POST", "/api/aggregator/payout/", json_body=body)
    except (AutoPayerAPIError, AutoPayerConfigError) as exc:
        logger.error(
            "[AUTOPAYER][PAYOUT] échec ref=%s err=%s payload=%s",
            transaction.reference,
            exc,
            getattr(exc, "payload", None),
        )
        transaction.change_status(
            new_status="error",
            source="API_ERROR",
            data=getattr(exc, "payload", {"error": str(exc)}),
            message=str(exc),
        )
        return {"ok": False, "error": str(exc)}

    uid = _extract_uid(payload)
    if uid:
        transaction.public_id = uid
        transaction.save(update_fields=["public_id"])

    transaction.change_status(
        new_status="pending",
        source="API_RESPONSE",
        data=payload,
        message="Payout AutoPayer initié",
        extra_fields=["public_id"] if uid else None,
    )
    logger.info(
        "[AUTOPAYER][PAYOUT] OK ref=%s uid=%s",
        transaction.reference,
        uid,
    )
    return {"ok": True, "uid": uid, "data": payload}


def autopayer_check_status(public_id: str | None = None, external_id: str | None = None) -> dict:
    """GET transaction par uid ou external_id."""
    import constant

    try:
        if public_id:
            payload = ap_request("GET", f"/api/aggregator/transactions/{public_id}/")
        elif external_id:
            payload = ap_request(
                "GET", f"/api/aggregator/transactions/external/{external_id}/"
            )
        else:
            return {"code": constant.CODE_EXEPTION, "erreur": "public_id ou external_id requis"}
        return {"code": constant.CODE_SUCCESS, "data": payload}
    except (AutoPayerAPIError, AutoPayerConfigError) as exc:
        return {
            "code": constant.CODE_EXEPTION,
            "erreur": str(exc),
            "data": getattr(exc, "payload", None),
        }


def process_autopayer_webhook(data: dict) -> None:
    """
    Traite le payload webhook AutoPayer (déjà authentifié HMAC côté vue).
    Statuts: pending|processing|success|failed|cancelled
    """
    from payment import webhook_transaction_failled, webhook_transaction_success

    # Payload peut être {data: {...}} ou plat
    body = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(body, dict):
        logger.warning("[AUTOPAYER][WEBHOOK] payload invalide")
        return

    external_id = body.get("external_id") or body.get("externalId")
    uid = body.get("uid") or body.get("id")
    status_raw = (body.get("status") or "").strip().lower()

    logger.info(
        "[AUTOPAYER][WEBHOOK] external_id=%s uid=%s status=%s",
        external_id,
        uid,
        status_raw,
    )

    if status_raw in {"pending", "processing"}:
        # Pas d'action métier — laisser en attente
        return

    with db_transaction.atomic():
        qs = Transaction.objects.filter(api="autopayer").exclude(
            Q(status="error") | Q(status="accept")
        )
        transaction = None
        if external_id:
            transaction = qs.filter(reference=external_id).select_for_update().first()
        if not transaction and uid:
            transaction = qs.filter(public_id=str(uid)).select_for_update().first()
        if not transaction and external_id:
            transaction = (
                Transaction.objects.filter(
                    Q(reference=external_id) | Q(public_id=external_id)
                )
                .exclude(Q(status="error") | Q(status="accept"))
                .select_for_update()
                .first()
            )

        if not transaction:
            logger.info(
                "[AUTOPAYER][WEBHOOK] transaction introuvable ou déjà finalisée "
                "external_id=%s uid=%s",
                external_id,
                uid,
            )
            return

        transaction.wehook_receive_at = timezone.now()
        transaction.webhook_data = json.dumps(data) if isinstance(data, dict) else str(data)
        if uid and not transaction.public_id:
            transaction.public_id = str(uid)
            transaction.save(update_fields=["wehook_receive_at", "webhook_data", "public_id"])
        else:
            transaction.save(update_fields=["wehook_receive_at", "webhook_data"])

        setting = Setting.objects.first()

        if status_raw in {"failed", "cancelled", "error"}:
            webhook_transaction_failled(transaction=transaction)
        elif status_raw in {"success", "successful", "confirmed"}:
            webhook_transaction_success(transaction=transaction, setting=setting)
        else:
            logger.warning(
                "[AUTOPAYER][WEBHOOK] statut ignoré=%s ref=%s",
                status_raw,
                transaction.reference,
            )
