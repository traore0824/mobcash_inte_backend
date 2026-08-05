"""Lookup public support (My Customer) — vérification en lecture seule."""

from __future__ import annotations

import ast
import json
import logging
import re
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from mobcash_inte.models import Transaction, TransactionStatusHistory
from payment import (
    connect_pro_status,
    connect_pro_verify_transaction_by_user_sms,
    connect_pro_confirm_withdrawal,
    connect_pro_retry_deposit,
    format_phone,
    get_connect_network_code,
    get_network_id,
)

logger = logging.getLogger(__name__)

# Aligné sur _connect_pro_webhook_inner (payment.py)
CONNECT_OK = frozenset({"success", "confirmed"})
CONNECT_FAIL = frozenset({"failed", "cancelled", "timeout", "error", "rejected"})
CONNECT_PENDING = frozenset({"pending", "processing", "initiated", "created", "waiting"})

# Dépôt support : statut Connect Pro en lecture seule (pas d'envoi d'argent).
# Sert à distinguer « paiement MM OK / crédit Betpay en attente » vs capture à demander.
HUMAN_HANDOFF_HINT = (
    "\n\nSi cela ne fonctionne toujours pas, écrivez « je veux parler à une personne » "
    "pour être mis en relation avec un conseiller."
)


def _with_human_handoff_hint(message: str) -> str:
    text = (message or "").rstrip()
    if "je veux parler" in text.lower():
        return text
    return f"{text}{HUMAN_HANDOFF_HINT}"



SUPPORT_LOOKUP_CALL_CONNECT_FOR_DEPOSIT = True

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
}

YES_VALUES = frozenset({
    "oui", "yes", "y", "true", "1", "ok", "daccord", "d'accord", "exact",
    "cest bon", "c'est bon", "bien envoye", "bien envoyé", "deja envoye",
    "déjà envoyé", "argent parti", "j'ai paye", "j'ai payé", "paye", "payé",
})
NO_VALUES = frozenset({
    "non", "no", "n", "false", "0", "pas encore", "toujours pas", "rien",
})


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _normalize_type(raw: str | None) -> str | None:
    if not raw:
        return None
    key = str(raw).strip().lower()
    return TYPE_ALIASES.get(key)


# Préfixes générés par generate_reference() — lookup accepte avec ou sans.
_REFERENCE_PREFIXES = (
    "depot-",
    "retrait-",
    "deposit-",
    "withdrawal-",
    "partner-",
)


def _reference_candidates(reference: str) -> list[str]:
    """Variantes de référence pour match exact en base (avec/sans préfixe)."""
    raw = (reference or "").strip()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        v = (value or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)

    add(raw)
    low = raw.lower()
    bare = raw
    for prefix in _REFERENCE_PREFIXES:
        if low.startswith(prefix):
            bare = raw[len(prefix) :]
            add(bare)
            break
    for prefix in _REFERENCE_PREFIXES:
        add(f"{prefix}{bare}")
    return out


def _find_transaction_by_reference(reference: str):
    """Retrouve une TX en essayant référence brute puis variantes préfixe."""
    qs = Transaction.objects.select_related("app", "network")
    for ref in _reference_candidates(reference):
        tx = qs.filter(reference=ref).first()
        if tx:
            return tx
    return None


def _normalize_boolish(raw: str | None) -> bool | None:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    folded = text.replace("é", "e").replace("è", "e").replace("ê", "e").replace("'", "")
    if folded in YES_VALUES or any(v in folded for v in ("oui", "paye", "envoye", "parti", "debite")):
        return True
    if folded in NO_VALUES or folded.startswith("non"):
        return False
    return None


def _parse_jsonish(raw: Any) -> dict:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {}
    for loader in (json.loads, ast.literal_eval):
        try:
            data = loader(text)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


def _mobcash_message(transaction: Transaction) -> str | None:
    data = _parse_jsonish(transaction.mobcash_response)
    for key in ("Message", "message", "detail", "error"):
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    nested = data.get("raw_response")
    if isinstance(nested, dict):
        for key in ("Message", "message"):
            val = nested.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    if transaction.message and transaction.message != "Transaction en cours":
        return str(transaction.message).strip()
    return None


def _phone_matches(transaction: Transaction, phone: str) -> bool:
    provided = _digits(phone)
    stored = _digits(transaction.phone_number)
    if not provided or not stored:
        return False
    length = 10
    phone_length = getattr(transaction.network, "phone_length", None) if transaction.network else None
    if phone_length:
        length = int(phone_length)
    try:
        stored_fmt = _digits(
            format_phone(numero=transaction.phone_number, longueur_locale=length)
        )
    except Exception:
        stored_fmt = stored[-length:] if len(stored) >= length else stored
    provided_fmt = provided[-length:] if len(provided) >= length else provided
    if stored_fmt and provided_fmt and stored_fmt == provided_fmt:
        return True
    for n in (10, 9, 8):
        if len(stored) >= n and len(provided) >= n and stored[-n:] == provided[-n:]:
            return True
    return False


def _connect_status_payload(transaction: Transaction) -> dict | None:
    """
    Statut Connect Pro — lecture seule (aucun envoi / relance d'argent).

    Pour les dépôts, contrôlé par SUPPORT_LOOKUP_CALL_CONNECT_FOR_DEPOSIT.
    """
    if (
        transaction.type_trans == "deposit"
        and not SUPPORT_LOOKUP_CALL_CONNECT_FOR_DEPOSIT
    ):
        return None
    if not transaction.public_id:
        return None
    network = transaction.network
    is_wave = bool(network and network.name == "wave")
    is_momo_pay = bool(
        network
        and getattr(network, "payment_by_link", False)
        and transaction.type_trans == "deposit"
    )
    try:
        data = connect_pro_status(
            reference=transaction.public_id,
            is_wave=is_wave,
            is_momo_pay=is_momo_pay,
        )
    except Exception as exc:
        logger.warning("connect_pro_status failed: %s", exc)
        return {"error": str(exc), "status": "error"}
    if data is None:
        return None
    if isinstance(data, dict):
        return data
    return {"raw": data, "status": "error"}


def _extract_connect_sms_items(payload: dict | None) -> list[dict]:
    """Extrais les SMS Connect (texte + méta) pour le rapport conseiller."""
    if not isinstance(payload, dict):
        return []
    raw_list = payload.get("sms")
    if not isinstance(raw_list, list):
        return []
    items: list[dict] = []
    for entry in raw_list[:3]:
        if not isinstance(entry, dict):
            continue
        data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        body = (
            data.get("original_body")
            or data.get("body")
            or data.get("text")
            or entry.get("original_body")
            or entry.get("body")
            or entry.get("text")
            or ""
        )
        body = str(body).strip()
        if not body:
            continue
        items.append(
            {
                "body": body[:500],
                "amount": data.get("amount", entry.get("amount")),
                "phone": data.get("phone", entry.get("phone")),
                "timestamp": entry.get("timestamp") or data.get("timestamp"),
            }
        )
    return items


def _connect_sms_items_as_nearby(sms_items: list[dict]) -> list[dict]:
    """Convertit les SMS statut Connect au format nearby (rapport agent)."""
    nearby: list[dict] = []
    for item in sms_items or []:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        nearby.append(
            {
                "body": body,
                "amount": item.get("amount"),
                "phone": item.get("phone"),
                "timestamp": item.get("timestamp"),
                "is_match": False,
            }
        )
    return nearby[:3]


def _phone_variants_for_sms(phone: Any) -> list[str]:
    """Variantes locales / indicatif pour maximiser le match Connect nearby."""
    digits = _digits(phone)
    if not digits:
        return []
    variants: list[str] = []
    for candidate in (
        digits,
        digits[-10:] if len(digits) >= 10 else digits,
        digits[-9:] if len(digits) >= 9 else "",
        f"225{digits[-10:]}" if len(digits) >= 10 else "",
        f"225{digits}" if not digits.startswith("225") else "",
    ):
        c = _digits(candidate)
        if c and c not in variants:
            variants.append(c)
    return variants


def _sms_entries_from_verify(verify: dict | None) -> list[dict]:
    """
    Extrais SMS utiles du verify Connect : nearby_messages (prioritaire)
    puis candidates (quand result=confirmed/possible → nearby souvent vide).
    """
    if not isinstance(verify, dict):
        return []
    nearby = _normalize_nearby_messages(verify.get("nearby_messages"))
    if nearby:
        return nearby
    raw_candidates = verify.get("candidates")
    if not isinstance(raw_candidates, list):
        return []
    items: list[dict] = []
    for entry in raw_candidates[:3]:
        if not isinstance(entry, dict):
            continue
        body = _nearby_body(entry)
        if not body:
            continue
        items.append(
            {
                "body": body[:500],
                "amount": entry.get("amount"),
                "phone": entry.get("phone"),
                "timestamp": entry.get("received_at") or entry.get("timestamp"),
                "is_match": False,
                "score": entry.get("score"),
                "sms_type": entry.get("sms_type"),
            }
        )
    return items


def _connect_sms_type_for_transaction(transaction: Transaction) -> str:
    """
    Mapping inversé Transaction → Connect sms_type :
    - retrait → deposit (Connect) (Connect / USSD path)
    - dépôt → withdrawal (Connect)
    """
    if (getattr(transaction, "type_trans", None) or "").strip().lower() == "withdrawal":
        return "deposit"
    return "withdrawal"


def _fetch_nearby_sms_for_agent(
    transaction: Transaction,
    connect_payload: dict | None,
    *,
    sms_type: str | None = None,
) -> list[dict]:
    """
    3 derniers SMS du numéro pour le rapport agent — même source que
    verify-transaction-by-user-sms (nearby_messages / candidates),
    fallback SMS statut TX.
    """
    nearby, _ussd, _meta = _fetch_agent_sms_and_ussd(
        transaction,
        connect_payload,
        sms_type=sms_type,
    )
    return nearby


def _fetch_agent_sms_and_ussd(
    transaction: Transaction,
    connect_payload: dict | None = None,
    *,
    sms_type: str | None = None,
) -> tuple[list[dict], list, dict]:
    """
    Un seul appel Connect verify-transaction-by-user-sms :
    - nearby / candidates (SMS agent)
    - ussd_path / has_ussd_path (si deposit Connect)

    sms_type défaut = mapping inversé Betpay ↔ Connect.
    """
    meta: dict[str, Any] = {
        "attempted": False,
        "ok": None,
        "has_ussd_path": False,
        "sms_type": None,
        "sms_type_filter": None,
        "result": None,
        "reason": None,
        "connect": None,
    }
    nearby: list[dict] = []
    ussd_path: list = []
    connect_uid = (transaction.public_id or "").strip()
    amount_norm = _normalize_amount_str(transaction.amount) or "0"
    network_id = _resolve_connect_network_id(transaction)
    operation_at = _to_iso_utc(getattr(transaction, "created_at", None))
    resolved_sms_type = (sms_type or _connect_sms_type_for_transaction(transaction) or "").strip().lower()
    meta["sms_type"] = resolved_sms_type or None
    last_verify: dict | None = None

    if connect_uid:
        meta["attempted"] = True
        for phone in _phone_variants_for_sms(transaction.phone_number):
            network_attempts: list[str | None] = [network_id] if network_id else [None]
            if network_id:
                network_attempts.append(None)
            for net in network_attempts:
                try:
                    verify = connect_pro_verify_transaction_by_user_sms(
                        transaction_uid=connect_uid,
                        amount=amount_norm,
                        phone=phone,
                        network_id=net,
                        operation_at=operation_at,
                        sms_type=resolved_sms_type or None,
                    )
                except Exception as exc:
                    logger.warning(
                        "verify SMS+ussd failed phone=%s net=%s: %s",
                        phone[-4:] if phone else "",
                        net,
                        exc,
                    )
                    continue
                if not isinstance(verify, dict):
                    continue
                last_verify = verify
                nearby = _sms_entries_from_verify(verify)
                raw_ussd = verify.get("ussd_path")
                ussd_path = raw_ussd if isinstance(raw_ussd, list) else []
                meta["ok"] = bool(verify.get("ok"))
                meta["has_ussd_path"] = bool(verify.get("has_ussd_path") or ussd_path)
                meta["sms_type_filter"] = verify.get("sms_type_filter")
                meta["result"] = verify.get("result")
                meta["connect"] = {
                    "result": verify.get("result"),
                    "sms_found": verify.get("sms_found"),
                    "has_ussd_path": meta["has_ussd_path"],
                    "ussd_steps": len(ussd_path),
                    "nearby_count": len(nearby),
                    "sms_type_filter": meta["sms_type_filter"],
                }
                if nearby or ussd_path:
                    return nearby, ussd_path, meta

    if not nearby:
        nearby = _normalize_nearby_messages(
            _connect_sms_items_as_nearby(_extract_connect_sms_items(connect_payload))
        )
    if last_verify is None and not nearby and not ussd_path:
        meta["reason"] = "verify_unavailable"
    elif not nearby and not ussd_path:
        meta["reason"] = (
            (last_verify or {}).get("message")
            or (last_verify or {}).get("result")
            or "empty"
        )
    return nearby, ussd_path, meta



def _connect_paid_evidence(payload: dict | None, transaction: Transaction) -> bool:
    """
    Paiement reçu côté Connect même si le statut n'est plus « success ».

    Cas réel : la transaction momo-pay passe en `expired` après la fenêtre
    de paiement alors que l'argent a bien été reçu (`confirmed_at` renseigné
    et SMS opérateur rattaché à la transaction).
    """
    if not isinstance(payload, dict):
        return False
    if str(payload.get("confirmed_at") or "").strip():
        return True
    expected = _normalize_amount_str(transaction.amount)
    for item in _extract_connect_sms_items(payload):
        got = _normalize_amount_str(item.get("amount"))
        if expected and got:
            try:
                if float(got) == float(expected):
                    return True
            except ValueError:
                continue
    return False


def _match_proof_against_status_sms(
    transaction: Transaction,
    *,
    amount: str,
    tid: str = "",
    ref: str = "",
) -> dict | None:
    """
    Secours quand verify-transaction-by-user-sms échoue (ex. 404 sur
    transaction expirée) : compare la preuve capture aux SMS déjà rattachés
    à la transaction dans le statut Connect.
    """
    payload = _connect_status_payload(transaction)
    items = _extract_connect_sms_items(payload)
    if not items:
        return None
    expected = _normalize_amount_str(amount)
    refs = [str(r).strip() for r in (tid, ref) if r and str(r).strip()]
    for item in items:
        body_compact = re.sub(r"\s+", "", str(item.get("body") or "")).lower()
        got = _normalize_amount_str(item.get("amount"))
        amount_ok = False
        if expected and got:
            try:
                amount_ok = float(got) == float(expected)
            except ValueError:
                amount_ok = False
        ref_ok = any(
            re.sub(r"\s+", "", r).lower() in body_compact for r in refs
        )
        if not (amount_ok or ref_ok):
            continue
        result = "confirmed" if (amount_ok and (ref_ok or not refs)) else "possible"
        return {
            "ok": True,
            "result": result,
            "sms_found": True,
            "match_score": 1.0 if result == "confirmed" else 0.5,
            "message": "",
            "refs_used": refs,
            "candidates": [
                {
                    "body": item.get("body"),
                    "amount": item.get("amount"),
                    "phone": item.get("phone"),
                    "timestamp": item.get("timestamp"),
                    "ref": refs[0] if ref_ok and refs else None,
                }
            ],
            "source": "connect_status_sms",
        }
    return None


def _sms_body_from_candidate(candidate: dict | None) -> str:
    if not isinstance(candidate, dict):
        return ""
    data = candidate.get("data") if isinstance(candidate.get("data"), dict) else {}
    for key in (
        "original_body",
        "body",
        "text",
        "sms_body",
        "content",
        "message",
    ):
        val = candidate.get(key) or data.get(key)
        if val not in (None, ""):
            return str(val).strip()[:500]
    return ""


def _deposit_connect_success_message(transaction: Transaction, *, phone_number: str) -> str:
    """Paiement MM confirmé côté Connect, crédit Betpay encore en attente."""
    amount = transaction.amount or 0
    payer_phone = (transaction.phone_number or "").strip() or (phone_number or "").strip()
    return (
        f"Oui, nous avons bien trouvé votre dépôt de {amount} FCFA.\n\n"
        f"Votre paiement Mobile Money a bien été effectué : l'argent a quitté le numéro {payer_phone}. "
        "Le blocage est de notre côté, pas un problème de paiement de votre part.\n\n"
        f"Nous allons finaliser le crédit. Vous recevrez vos {amount} FCFA sur votre compte sous peu."
    )



def _connect_proof_lines_for_agent(
    connect_payload: dict | None,
    *,
    connect_status: str | None = None,
) -> str:
    """Preuve Connect lisible pour le rapport agent (SMS / confirmed_at)."""
    lines: list[str] = []
    if isinstance(connect_payload, dict):
        confirmed = str(connect_payload.get("confirmed_at") or "").strip()
        if confirmed:
            lines.append(f"confirmed_at: {confirmed}")
        st = (connect_status or _connect_status_value(connect_payload) or "").strip()
        if st:
            lines.append(f"statut Connect: {st}")
        sms_items = _extract_connect_sms_items(connect_payload)
        for i, item in enumerate(sms_items, 1):
            body = str(
                item.get("body")
                or item.get("original_body")
                or item.get("text")
                or ""
            ).strip()
            if body:
                lines.append(f"SMS {i}: {body[:400]}")
            amt = item.get("amount")
            if amt not in (None, ""):
                lines.append(f"  montant SMS: {amt}")
    if not lines:
        return "Preuve Connect disponible (paiement confirmé), détail SMS non disponible."
    return "\n".join(lines)


def _mark_deposit_accept_aligned(transaction: Transaction) -> bool:
    """
    Aligne le statut en accept quand Connect OK + crédit app déjà Success.
    """
    if transaction.status == "accept":
        return False
    old_status = transaction.status
    try:
        transaction.status = "accept"
        transaction.message = (
            "Crédité — aligné via support lookup (Connect OK + app Success)"
        )
        transaction.save(update_fields=["status", "message"])
        TransactionStatusHistory.objects.create(
            transaction=transaction,
            old_status=old_status,
            new_status="accept",
            trigger_source=TransactionStatusHistory.Source.AGENT_BOT,
            trigger_data={
                "action": "align_accept_connect_and_mobcash_success",
            },
            message=transaction.message[:500],
        )
        logger.info(
            "TX %s aligned to accept (Connect OK + mobcash Success)",
            transaction.reference,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to align TX %s to accept",
            getattr(transaction, "reference", None),
        )
        return False


def _deposit_credit_pending_agent_message(
    transaction: Transaction,
    *,
    phone_number: str,
    connect_payload: dict | None,
    connect_status: str | None,
) -> str:
    app_label = _app_public_label(transaction)
    proof = _connect_proof_lines_for_agent(
        connect_payload,
        connect_status=connect_status,
    )
    payer = (
        (transaction.phone_number or "").strip()
        or (phone_number or "").strip()
        or "N/A"
    )
    player = (transaction.user_app_id or "").strip() or "N/A"
    amount = transaction.amount or 0
    return (
        f"À traiter — dépôt : paiement reçu, compte {app_label} non rechargé\n\n"
        f"• Référence : {transaction.reference}\n"
        f"• Montant : {amount} FCFA\n"
        f"• ID joueur : {player}\n"
        f"• Numéro payeur : {payer}\n"
        "• **Connect a bien confirmé le paiement Mobile Money.**\n"
        "• Preuve de succès :\n"
        f"{proof}\n"
        f"• **Nous avons bien reçu l'argent de l'utilisateur, mais son compte "
        f"{app_label} n'a pas été rechargé.**"
    )


def _format_verify_matched_sms_lines(connect_result: dict | None) -> str:
    """Corps SMS matchés (candidates) pour la preuve agent."""
    if not isinstance(connect_result, dict):
        return "  (détail SMS non disponible)"
    lines: list[str] = []
    raw = connect_result.get("candidates")
    if isinstance(raw, list):
        for entry in raw[:3]:
            if not isinstance(entry, dict):
                continue
            body = (_nearby_body(entry) or "").strip()
            if body:
                lines.append(f"  {body[:400]}")
    if not lines:
        for entry in _sms_entries_from_verify(connect_result)[:3]:
            body = (_nearby_body(entry) or "").strip()
            if body:
                lines.append(f"  {body[:400]}")
    if not lines:
        return "  (détail SMS non disponible)"
    return "\n".join(lines)


def _sms_proof_found_agent_message(
    transaction: Transaction,
    *,
    connect_result: dict | None,
) -> str:
    """Rapport agent : preuve SMS trouvée → créditer le jeu."""
    app_label = _app_public_label(transaction)
    payer = (transaction.phone_number or "").strip() or "N/A"
    player = (transaction.user_app_id or "").strip() or "N/A"
    amount = transaction.amount or 0
    proof = _format_verify_matched_sms_lines(connect_result)
    return (
        f"À traiter — dépôt : paiement reçu, compte {app_label} non rechargé\n\n"
        f"• Référence : {transaction.reference}\n"
        f"• Montant : {amount} FCFA\n"
        f"• ID joueur : {player}\n"
        f"• Numéro payeur : {payer}\n"
        "• **Connect a bien confirmé le paiement Mobile Money.**\n"
        "• Preuve de succès :\n"
        f"{proof}\n"
        f"• **Nous avons bien reçu l'argent de l'utilisateur, mais son compte "
        f"{app_label} n'a pas été rechargé.**"
    )


def _sms_proof_not_found_agent_message(
    transaction: Transaction,
    *,
    nearby: list[dict] | None,
) -> str:
    """Rapport agent : capture reçue, aucun SMS matché."""
    app_label = _app_public_label(transaction)
    payer = (transaction.phone_number or "").strip() or "N/A"
    player = (transaction.user_app_id or "").strip() or "N/A"
    amount = transaction.amount or 0
    nearby_block = _format_nearby_for_agent(nearby or [])
    if not nearby_block:
        nearby_block = "Aucun SMS / notification récent pour ce numéro."
    return (
        "À traiter — dépôt : capture reçue, preuve non trouvée chez Connect\n\n"
        f"• Référence : {transaction.reference}\n"
        f"• Montant : {amount} FCFA\n"
        f"• ID joueur : {player}\n"
        f"• Numéro payeur : {payer}\n"
        "• **Connect n'a trouvé aucun SMS / notification correspondant "
        "à ce paiement.**\n"
        f"{nearby_block}\n"
        "• **Vérifier la capture manuellement avant de créditer le compte "
        f"{app_label}.**"
    )


def _sms_verify_agent_message(
    transaction: Transaction,
    *,
    result_key: str,
    connect_result: dict | None,
    nearby: list[dict] | None,
    fallback: str,
) -> str:
    key = (result_key or "").strip().lower()
    if key in {"confirmed", "possible", "ambiguous"}:
        return _sms_proof_found_agent_message(
            transaction,
            connect_result=connect_result,
        )
    if key in {"not_found", "mismatch"}:
        return _sms_proof_not_found_agent_message(
            transaction,
            nearby=nearby,
        )
    return fallback


def _mobcash_success_flag(transaction: Transaction) -> bool | None:
    """True/False si Success est présent dans mobcash_response, sinon None."""
    data = _parse_jsonish(transaction.mobcash_response)
    if not data:
        return None
    if "Success" not in data and "success" not in data:
        return None
    val = data.get("Success", data.get("success"))
    if val is True or str(val).strip().lower() in {"true", "1", "yes"}:
        return True
    if val is False or str(val).strip().lower() in {"false", "0", "no"}:
        return False
    return None


def _app_public_label(transaction: Transaction) -> str:
    app = getattr(transaction, "app", None)
    if not app:
        return "votre application de jeu"
    return (
        (getattr(app, "public_name", None) or getattr(app, "name", None) or "")
        .strip()
        or "votre application de jeu"
    )


def _withdrawal_info_block(transaction: Transaction) -> str:
    """Infos claires pour le client (réclamation retrait)."""
    app_label = _app_public_label(transaction)
    network = ""
    if transaction.network:
        network = (
            (getattr(transaction.network, "public_name", None) or getattr(transaction.network, "name", None) or "")
            .strip()
        )
    lines = [
        "Voici les informations de votre retrait :",
        f"• Application : {app_label}",
        f"• Référence : {transaction.reference}",
        f"• Montant : {transaction.amount or 0} FCFA",
        f"• Téléphone : {(transaction.phone_number or '').strip() or 'N/A'}",
    ]
    if network:
        lines.append(f"• Réseau : {network}")
    player_id = (transaction.user_app_id or "").strip()
    if player_id:
        lines.append(f"• Identifiant joueur : {player_id}")
    return "\n".join(lines)


_DEPOSIT_SMS_HINTS = (
    "reçu",
    "recu",
    "dépôt",
    "depot",
    "crédité",
    "credite",
    "vous avez reçu",
    "vous avez recu",
    "transaction réussie",
    "transaction reussie",
    "paiement reçu",
    "paiement recu",
)


def _sms_suggests_mm_credit(
    sms_items: list[dict],
    transaction: Transaction,
) -> bool:
    """True si un SMS opérateur ressemble à un crédit MM sur le numéro."""
    expected = _normalize_amount_str(transaction.amount)
    for item in sms_items or []:
        body = str(item.get("body") or "").lower()
        if not body:
            continue
        hint_ok = any(h in body for h in _DEPOSIT_SMS_HINTS)
        amount_ok = False
        got = _normalize_amount_str(item.get("amount"))
        if expected and got:
            try:
                amount_ok = float(got) == float(expected)
            except ValueError:
                amount_ok = False
        if not amount_ok and expected and expected in re.sub(r"\D", "", body):
            amount_ok = True
        if hint_ok or amount_ok:
            return True
    return False


def _request_withdrawal_mm_transfer(transaction: Transaction) -> dict:
    """
    Demande un transfert Connect (retry-deposit) pour un retrait.
    Ne lève pas : retourne meta pour le payload agent.
    """
    from django.conf import settings as dj_settings

    meta = {
        "attempted": False,
        "success": None,
        "reason": None,
        "connect_action": None,
    }
    if not getattr(dj_settings, "ALLOW_USER_TRANSACTION_ACTIONS", False):
        meta["reason"] = "actions_disabled"
        return meta
    uid = (transaction.public_id or "").strip()
    if not uid:
        meta["reason"] = "missing_connect_uid"
        return meta
    meta["attempted"] = True
    try:
        result = connect_pro_retry_deposit(
            transaction_uid=uid,
            note="support_lookup:withdrawal_success_request_transfer",
        )
    except Exception as exc:
        logger.warning("connect_pro_retry_deposit failed: %s", exc)
        meta["success"] = False
        meta["reason"] = str(exc)
        return meta
    meta["connect_action"] = result if isinstance(result, dict) else {"raw": result}
    http_status = int((result or {}).get("http_status") or 200) if isinstance(result, dict) else 200
    meta["success"] = bool(isinstance(result, dict) and result.get("ok")) and http_status < 400
    if meta["success"] is False:
        meta["reason"] = (
            (result or {}).get("detail")
            or (result or {}).get("error")
            or (result or {}).get("message")
            or "transfer_failed"
        )
    return meta



def _connect_status_value(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("status_code") == 404:
        return "not_found"
    if payload.get("error") and not payload.get("status"):
        return "error"
    for candidate in (
        payload.get("status"),
        (payload.get("data") or {}).get("status") if isinstance(payload.get("data"), dict) else None,
        payload.get("state"),
        payload.get("payment_status"),
    ):
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip().lower()
    return None


def _classify_connect(payload: dict | None) -> str:
    """
    Retourne: ok | fail | pending | unknown
    Même logique que le webhook Connect Pro.
    """
    value = _connect_status_value(payload)
    if not value:
        return "unknown" if payload is None else "unknown"
    if value in CONNECT_OK:
        return "ok"
    if value in CONNECT_FAIL or value == "not_found":
        return "fail"
    if value in CONNECT_PENDING:
        return "pending"
    return "unknown"


def _intro(transaction: Transaction, type_trans: str) -> str:
    amount = transaction.amount or 0
    player_id = (transaction.user_app_id or "").strip() or "non renseigné"
    if type_trans == "deposit":
        return (
            f"Oui, nous avons remarqué un dépôt de {amount} FCFA "
            f"pour l'identifiant {player_id}."
        )
    return (
        f"Oui, nous avons remarqué un retrait de {amount} FCFA "
        f"pour l'identifiant {player_id}."
    )


def _base_payload(transaction: Transaction, *, message: str, **extra) -> dict:
    return {
        "found": True,
        "reference": transaction.reference,
        "type": transaction.type_trans,
        "amount": transaction.amount,
        "status": transaction.status,
        "message": message,
        "pipeline_message": transaction.message,
        "mobcash_message": _mobcash_message(transaction),
        "app": {
            "name": transaction.app.name if transaction.app else None,
            # Mobcash AppName n'a pas public_name (contrairement à Betpay) — on renvoie name.
            "public_name": transaction.app.name if transaction.app else None,
        },
        "user_app_id": transaction.user_app_id,
        "phone_number": transaction.phone_number,
        **extra,
    }


def _resolve_transaction(reference: str, type_raw: str, phone_number: str):
    type_trans = _normalize_type(type_raw)
    if not reference or not type_trans or not phone_number:
        return None, None, {
            "found": False,
            "phase": "done",
            "message": (
                "Merci de préciser le type (dépôt ou retrait), la référence "
                "de la transaction et le numéro Mobile Money concerné."
            ),
        }, status.HTTP_400_BAD_REQUEST

    transaction = _find_transaction_by_reference(reference)
    if not transaction:
        return None, type_trans, {
            "found": False,
            "phase": "done",
            "reference": reference.strip(),
            "message": (
                "Nous n'avons trouvé aucune transaction avec cette référence. "
                "Pouvez-vous vérifier la référence, puis réessayer ?"
            ),
        }, status.HTTP_200_OK

    if transaction.type_trans != type_trans:
        expected = "dépôt" if transaction.type_trans == "deposit" else "retrait"
        return None, type_trans, {
            "found": False,
            "phase": "done",
            "reference": transaction.reference,
            "type": transaction.type_trans,
            "message": (
                f"Cette référence correspond à un {expected}, pas au type indiqué. "
                f"Pouvez-vous confirmer s'il s'agit bien d'un {expected} ?"
            ),
        }, status.HTTP_200_OK

    return transaction, type_trans, None, None


def _handle_phone_mismatch(
    transaction: Transaction,
    *,
    type_trans: str,
    phone_number: str,
    has_screenshot: bool = False,
) -> dict:
    intro = _intro(transaction, type_trans)
    stored = (transaction.phone_number or "").strip() or "non renseigné"
    indicated = phone_number.strip()
    mismatch = (
        f"Cependant, le numéro Mobile Money que vous avez indiqué {indicated} "
        f"ne correspond pas à celui enregistré sur cette transaction {stored}."
    )
    app_label = _app_public_label(transaction)

    transfer_retried = False
    transfer_ok = None
    needs_escalation = False
    phase = "done"

    if type_trans == "withdrawal":
        # Mauvais numéro : jamais de transfert auto (succès app ou non).
        app_ok = (
            _mobcash_success_flag(transaction) is True
            or transaction.status == "accept"
        )
        if app_ok:
            detail = (
                f"{mismatch}\n\n"
                "Ce retrait a déjà été payé sur le numéro enregistré sur la transaction.\n"
                "Vous pouvez demander à parler à un humain."
            )
        else:
            detail = (
                f"{mismatch}\n\n"
                f"Sur {app_label}, nous n'avons pas non plus reçu votre transfert.\n"
                f"Vérifiez sur votre compte {app_label}, puis relancez votre retrait."
            )
        needs_escalation = False
        phase = "done"
    else:
        # Dépôt : demander le vrai numéro payeur + capture — pas de transfert pour l'instant.
        detail = (
            f"{mismatch}\n\n"
            "Merci d'envoyer le numéro Mobile Money qui a réellement effectué "
            "le transfert, ainsi que la capture d'écran de l'opération."
        )
        phase = "await_payer_details"
        needs_escalation = False

    return _base_payload(
        transaction,
        message=f"{intro}\n\n{detail}".strip(),
        phase=phase,
        phone_match=False,
        phone_number_on_transaction=stored,
        phone_number_indicated=indicated,
        has_screenshot=bool(has_screenshot),
        needs_escalation=needs_escalation,
        connect={"checked": False, "ok": None, "status": None, "class": None},
        transfer_retry={
            "attempted": transfer_retried,
            "success": transfer_ok,
            "reason": "phone_mismatch",
        },
    )


def build_lookup_response(
    *,
    reference: str,
    type_raw: str,
    phone_number: str,
) -> tuple[dict, int]:
    transaction, type_trans, err, code = _resolve_transaction(reference, type_raw, phone_number)
    if err is not None:
        return err, code

    if not _phone_matches(transaction, phone_number):
        return _handle_phone_mismatch(
            transaction, type_trans=type_trans, phone_number=phone_number
        ), status.HTTP_200_OK

    # Dépôt : statut local + Connect (lecture seule) pour le message client.
    if type_trans == "deposit":
        intro = _intro(transaction, type_trans)
        if transaction.status == "accept":
            app_label = _app_public_label(transaction)
            amount = transaction.amount or 0
            msg = (
                f"Oui, nous avons bien reçu votre dépôt de {amount} FCFA.\n"
                f"Votre compte {app_label} a bien été crédité.\n"
                "Si le solde n'apparaît pas encore, actualisez l'application "
                "ou reconnectez-vous."
            )
            return _base_payload(
                transaction,
                message=msg,
                phase="done",
                phone_match=True,
                needs_escalation=False,
                connect={"checked": False, "ok": None, "status": None, "class": "skipped"},
                transfer_retry={"attempted": False, "success": None},
            ), status.HTTP_200_OK

        connect_payload = _connect_status_payload(transaction)
        connect_class = _classify_connect(connect_payload)
        connect_ok = connect_class == "ok"
        connect_status = _connect_status_value(connect_payload)
        connect_sms = _extract_connect_sms_items(connect_payload)
        connect_paid = connect_ok or _connect_paid_evidence(connect_payload, transaction)
        connect_meta = {
            "checked": connect_payload is not None,
            "ok": connect_ok if connect_payload is not None else None,
            "status": connect_status,
            "class": connect_class if connect_payload is not None else "skipped",
            "sms": connect_sms,
            "paid_evidence": connect_paid,
            "confirmed_at": (
                connect_payload.get("confirmed_at")
                if isinstance(connect_payload, dict)
                else None
            ),
        }

        # Paiement MM confirmé chez Connect.
        # - MobCash Success=true → aligner accept, message client, pas de transfert
        # - sinon → transfert + rapport agent (crédit jeu non fait)
        if connect_paid:
            app_label = _app_public_label(transaction)
            amount = transaction.amount or 0
            mobcash_ok = _mobcash_success_flag(transaction)
            if mobcash_ok is True:
                _mark_deposit_accept_aligned(transaction)
                transaction.refresh_from_db()
                msg = (
                    f"Oui, nous avons bien reçu votre dépôt de {amount} FCFA.\n"
                    f"Votre compte {app_label} a bien été crédité."
                )
                return _base_payload(
                    transaction,
                    message=msg,
                    phase="done",
                    phone_match=True,
                    needs_escalation=False,
                    connect=connect_meta,
                    transfer_retry={"attempted": False, "success": None},
                    mobcash_success=True,
                ), status.HTTP_200_OK

            payer_phone = (
                (transaction.phone_number or "").strip()
                or (phone_number or "").strip()
                or "le numéro enregistré"
            )
            client_msg = (
                f"Oui, nous avons bien reçu votre dépôt de {amount} FCFA.\n"
                f"Votre paiement Mobile Money a bien été effectué depuis {payer_phone}.\n"
                f"Le crédit sur votre compte {app_label} n'est pas encore finalisé.\n"
                "Un conseiller s'en occupe ; vous serez crédité sous peu."
            )
            agent_msg = _deposit_credit_pending_agent_message(
                transaction,
                phone_number=phone_number,
                connect_payload=connect_payload,
                connect_status=connect_status,
            )
            return _base_payload(
                transaction,
                message=client_msg,
                phase="done",
                phone_match=True,
                needs_escalation=True,
                connect=connect_meta,
                transfer_retry={"attempted": False, "success": None},
                mobcash_success=mobcash_ok,
                agent_message=agent_msg,
            ), status.HTTP_200_OK

        payer_phone = (transaction.phone_number or "").strip() or "le numéro utilisé"
        message = (
            f"{intro}\n\n"
            "Nous n'avons pas encore pu confirmer votre paiement Mobile Money.\n"
            "Merci d'envoyer la capture d'écran de votre transfert\n"
            f"(depuis le numéro {payer_phone}).\n\n"
            "Assurez-vous que c'est bien le numéro de la transaction qui a effectué "
            "le dépôt : cela peut aussi être la raison du problème.\n"
            "Si c'est un autre numéro qui a fait le transfert, envoyez-nous la capture "
            "de paiement et le bon numéro."
        ).strip()
        return _base_payload(
            transaction,
            message=message,
            phase="await_screenshot",
            phone_match=True,
            connect=connect_meta,
            transfer_retry={"attempted": False, "success": None},
        ), status.HTTP_200_OK

    # --- Retrait ---
    intro = _intro(transaction, type_trans)
    app_label = _app_public_label(transaction)
    info = _withdrawal_info_block(transaction)

    # Déjà accepté : message clair, pas d'échec trompeur.
    if transaction.status == "accept":
        message = (
            f"{intro}\n\n"
            "Votre retrait a déjà été traité avec succès : l'argent a été envoyé "
            "vers votre numéro Mobile Money.\n\n"
            f"{info}"
        ).strip()
        return _base_payload(
            transaction,
            message=message,
            phase="done",
            phone_match=True,
            needs_escalation=False,
            connect={"checked": False, "ok": None, "status": None, "class": "skipped"},
            transfer_retry={"attempted": False, "success": None},
            mobcash_success=_mobcash_success_flag(transaction),
        ), status.HTTP_200_OK

    mobcash_ok = _mobcash_success_flag(transaction)
    # Retrait : Success=true et status=payment_init_success = même chose (débité jeu).
    app_debited = mobcash_ok is True or (
        mobcash_ok is not False
        and (transaction.status or "").strip() == "payment_init_success"
    )

    # Success == false : pas de virement depuis l'app → pas d'escalade.
    if mobcash_ok is False:
        message = (
            f"{intro}\n\n"
            f"Nous n'avons pas reçu de virement depuis {app_label}.\n"
            f"Merci de vérifier sur {app_label} que le retrait a bien été lancé\n"
            "(demande de paiement ouverte / en attente de validation).\n\n"
            f"{info}"
        ).strip()
        return _base_payload(
            transaction,
            message=message,
            phase="done",
            phone_match=True,
            needs_escalation=False,
            connect={"checked": False, "ok": None, "status": None, "class": "skipped"},
            transfer_retry={"attempted": False, "success": None},
            mobcash_success=False,
        ), status.HTTP_200_OK

    # Débité côté jeu (Success=true ou payment_init_success) → Connect + SMS.
    if app_debited:
        connect_payload = _connect_status_payload(transaction)
        connect_class = _classify_connect(connect_payload)
        connect_ok = connect_class == "ok"
        connect_status = _connect_status_value(connect_payload)
        connect_sms = _extract_connect_sms_items(connect_payload)
        sms_credit = _sms_suggests_mm_credit(connect_sms, transaction)
        connect_paid = connect_ok or _connect_paid_evidence(connect_payload, transaction)
        connect_meta = {
            "checked": connect_payload is not None,
            "ok": connect_ok if connect_payload is not None else None,
            "status": connect_status,
            "class": connect_class if connect_payload is not None else "skipped",
            "sms": connect_sms,
            "sms_mm_credit": sms_credit,
            "paid_evidence": connect_paid,
            "confirmed_at": (
                connect_payload.get("confirmed_at")
                if isinstance(connect_payload, dict)
                else None
            ),
        }

        transfer_meta = {"attempted": False, "success": None, "reason": None}
        needs_escalation = False

        nearby: list[dict] = []
        ussd_path: list = []
        ussd_meta: dict[str, Any] = {
            "attempted": False,
            "ok": None,
            "has_ussd_path": False,
            "reason": None,
        }
        agent_message = None

        if connect_ok or connect_paid:
            user_message = (
                f"{intro}\n\n"
                f"Bonne nouvelle : votre retrait a bien été validé sur {app_label}.\n"
                "L'envoi Mobile Money est confirmé.\n\n"
                f"{info}"
            ).strip()
        else:
            # Connect pas success → escalade + rapport agent (SMS / USSD).
            transfer_meta = _request_withdrawal_mm_transfer(transaction)
            needs_escalation = True
            nearby, ussd_path, ussd_meta = _fetch_agent_sms_and_ussd(
                transaction,
                connect_payload,
            )
            phone_label = (
                (transaction.phone_number or "").strip() or "N/A"
            )
            player_id = (transaction.user_app_id or "").strip() or "N/A"
            amount = transaction.amount or 0
            user_message = (
                f"{intro}\n\n"
                f"Bonne nouvelle : votre retrait a bien été validé sur {app_label}.\n"
                "Un conseiller va vous aider pour le virement Mobile Money.\n\n"
                f"{info}"
            ).strip()

            if transfer_meta.get("attempted") and transfer_meta.get("success"):
                renvoi_label = "demandé et accepté"
            elif transfer_meta.get("attempted"):
                renvoi_label = "demandé mais échec"
            else:
                renvoi_label = "non lancé"

            agent_nearby = _format_nearby_for_agent(nearby)
            sms_block = agent_nearby or "Aucun SMS / notification récent pour ce numéro."
            agent_ussd = _format_ussd_path_for_agent(ussd_path)
            ussd_block = agent_ussd or "Aucun chemin USSD pour cette transaction."

            agent_message = (
                "À traiter — retrait : compte jeu débité, Mobile Money non reçu\n\n"
                f"• Référence : {transaction.reference}\n"
                f"• Montant : {amount} FCFA\n"
                f"• ID joueur : {player_id}\n"
                f"• Numéro MM : {phone_label}\n"
                f"• Application : {app_label}\n"
                f"• **Nous avons bien reçu le virement depuis le compte "
                f"{app_label} de l'utilisateur, mais l'envoi Mobile Money "
                f"côté Connect n'a pas réussi.**\n"
                f"• Renvoi auto : {renvoi_label}\n"
                "• SMS du numéro (indicatif) :\n"
                f"{sms_block}\n"
                "• Chemin USSD :\n"
                f"{ussd_block}\n"
                "• **Envoyer le montant au client sur son Mobile Money "
                "si le renvoi auto n'a pas abouti**"
            )

        payload_extra: dict[str, Any] = {
            "phase": "done",
            "phone_match": True,
            "needs_escalation": needs_escalation,
            "connect": connect_meta,
            "transfer_retry": {
                "attempted": bool(transfer_meta.get("attempted")),
                "success": transfer_meta.get("success"),
                "reason": transfer_meta.get("reason"),
            },
            "mobcash_success": True if mobcash_ok is True else None,
            "transfer_request": transfer_meta,
        }
        if agent_message is not None:
            payload_extra["agent_message"] = agent_message
            payload_extra["nearby_messages"] = nearby
            payload_extra["ussd_path"] = ussd_path
            payload_extra["has_ussd_path"] = bool(
                ussd_path or ussd_meta.get("has_ussd_path")
            )
            payload_extra["ussd_path_meta"] = ussd_meta

        return _base_payload(
            transaction,
            message=user_message,
            **payload_extra,
        ), status.HTTP_200_OK

    # Ni Success=false, ni débit jeu détecté → encore en cours.
    message = (
        f"{intro}\n\n"
        "Le retrait est encore en cours de traitement.\n"
        f"Statut actuel : {transaction.message or transaction.status}.\n\n"
        f"{info}"
    ).strip()
    return _base_payload(
        transaction,
        message=message,
        phase="done",
        phone_match=True,
        needs_escalation=False,
        connect={"checked": False, "ok": None, "status": None, "class": "skipped"},
        transfer_retry={"attempted": False, "success": None},
        mobcash_success=None,
    ), status.HTTP_200_OK


def build_confirm_payment_response(
    *,
    reference: str,
    type_raw: str,
    phone_number: str,
    money_sent_raw: str,
    has_screenshot_raw: str,
) -> tuple[dict, int]:
    transaction, type_trans, err, code = _resolve_transaction(reference, type_raw, phone_number)
    if err is not None:
        return err, code

    money_sent = _normalize_boolish(money_sent_raw)
    has_screenshot = _normalize_boolish(has_screenshot_raw) is True
    # Présence image : aussi accepter "1", "true", ou texte type "[image]"
    proof_hint = (has_screenshot_raw or "").strip().lower()
    if proof_hint in {"[image]", "image", "screenshot", "capture", "photo"}:
        has_screenshot = True

    if not _phone_matches(transaction, phone_number):
        # Numéro payeur ≠ numéro transaction : collecter preuve puis transfert conseiller.
        return _handle_phone_mismatch(
            transaction,
            type_trans=type_trans,
            phone_number=phone_number,
            has_screenshot=has_screenshot,
        ), status.HTTP_200_OK

    intro = _intro(transaction, type_trans)
    capture_client = (
        "Nous avons bien reçu votre capture. "
        "Un conseiller va la vérifier et revenir vers vous."
    )

    # Capture reçue = preuve que l'argent a quitté le compte.
    # Sans capture : un seul rappel (pas de question oui/non séparée).
    if not has_screenshot:
        if money_sent is False:
            return _base_payload(
                transaction,
                message=(
                    f"{intro}\n\n"
                    "D'accord. Tant que le débit Mobile Money n'est pas effectif, "
                    "nous ne pouvons pas forcer le crédit. Validez le paiement USSD / le lien, "
                    "puis revenez vers nous avec la référence si besoin."
                ).strip(),
                phase="done",
                phone_match=True,
                needs_escalation=False,
            ), status.HTTP_200_OK
        payer_phone = (transaction.phone_number or "").strip() or "le numéro utilisé"
        return _base_payload(
            transaction,
            message=(
                f"{intro}\n\n"
                "Nous n'avons pas encore pu confirmer votre paiement Mobile Money.\n"
                "Merci d'envoyer la capture d'écran de votre transfert\n"
                f"(depuis le numéro {payer_phone})."
            ).strip(),
            phase="await_screenshot",
            phone_match=True,
            money_sent=True if money_sent else None,
            needs_escalation=False,
        ), status.HTTP_200_OK

    # Lecture seule : aligné sur verify-sms (client) + rapport agent simple.
    player = (transaction.user_app_id or "").strip() or "N/A"
    payer = (transaction.phone_number or "").strip() or "N/A"
    amount = transaction.amount or 0
    if type_trans == "deposit":
        agent_message = (
            "À traiter — dépôt : capture reçue, à vérifier\n\n"
            f"• Référence : {transaction.reference}\n"
            f"• Montant : {amount} FCFA\n"
            f"• ID joueur : {player}\n"
            f"• Numéro payeur : {payer}\n"
            "• Capture : reçue\n"
            "• **Vérifier la capture et traiter le dossier manuellement.**"
        )
        return _base_payload(
            transaction,
            message=capture_client,
            phase="done",
            phone_match=True,
            money_sent=True,
            has_screenshot=True,
            needs_escalation=True,
            agent_message=agent_message,
            transfer_retry={"attempted": False, "success": None, "reason": "read_only_lookup"},
        ), status.HTTP_200_OK

    # Retrait : lecture seule, aucune relance de payout.
    if transaction.status == "accept":
        client_extra = (
            f"{capture_client}\n"
            "Ce retrait apparaît déjà comme payé."
        )
    else:
        client_extra = capture_client
    agent_message = (
        "À traiter — retrait : capture reçue, à vérifier\n\n"
        f"• Référence : {transaction.reference}\n"
        f"• Montant : {amount} FCFA\n"
        f"• ID joueur : {player}\n"
        f"• Numéro MM : {payer}\n"
        "• Capture : reçue\n"
        "• **Vérifier la capture et traiter le dossier manuellement.**"
    )
    return _base_payload(
        transaction,
        message=client_extra,
        phase="done",
        phone_match=True,
        money_sent=True,
        has_screenshot=True,
        needs_escalation=True,
        agent_message=agent_message,
        transfer_retry={"attempted": False, "success": None, "reason": "read_only_lookup"},
    ), status.HTTP_200_OK


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_amount_str(raw: Any) -> str:
    text = str(raw or "").strip().replace("\u00a0", " ")
    text = re.sub(r"[^\d,.\-]", "", text).replace(" ", "")
    if not text or text in {"-", ".", ","}:
        return ""
    # 5.000 / 103.807.000 → séparateur milliers
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", text):
        return text.replace(".", "")
    if "," in text and "." in text:
        # 1.557,10 → 1557.10
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    return text


def _resolve_connect_network_id(transaction: Transaction) -> str | None:
    """Même filtre que dépôt/retrait Connect (get_connect_network_code)."""
    network = transaction.network
    if not network or not network.name:
        return None
    try:
        code = get_connect_network_code(network)
    except Exception as exc:
        logger.warning("get_connect_network_code failed: %s", exc)
        code = f"{network.name}-{network.country_code}"
    try:
        return get_network_id(name=code) or None
    except Exception as exc:
        logger.warning("get_network_id failed for %s: %s", code, exc)
        return None


def _to_iso_utc(value: Any) -> str | None:
    """Normalise une date (str/datetime) en ISO UTC `…Z` pour Connect."""
    if value is None or value == "":
        return None
    dt = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        dt = parse_datetime(text.replace("Z", "+00:00"))
        if dt is None:
            # Déjà une chaîne ISO plausible → on la renvoie telle quelle
            return text
    if not isinstance(dt, datetime):
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nearby_body(entry: dict) -> str:
    data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    body = (
        entry.get("content_preview")
        or entry.get("body")
        or entry.get("text")
        or entry.get("original_body")
        or entry.get("content")
        or data.get("original_body")
        or data.get("body")
        or data.get("text")
        or data.get("content_preview")
        or ""
    )
    return str(body).strip()


def _format_nearby_for_agent(nearby: list[dict]) -> str:
    """
    Texte des nearby SMS pour le conseiller (jamais pour le client WhatsApp).

    Segments explicites pour l'UI agent (évite de parser « 1. / 300.00 » à tort) :
      [[SMS_LIST count=N]]
      [[SMS i=1]]
      ...body...
      [[/SMS]]
      [[/SMS_LIST]]
    """
    if not nearby:
        return ""
    lines = [
        f"Voici les {len(nearby)} derniers SMS/notifications du numéro "
        "(indicatif seulement — ce n'est PAS une preuve de paiement).",
        f"[[SMS_LIST count={len(nearby)}]]",
    ]
    for i, entry in enumerate(nearby, 1):
        body = (_nearby_body(entry) or "(vide)").replace("\r\n", "\n").strip()
        ts = entry.get("timestamp") or entry.get("received_at") or ""
        amount = entry.get("amount")
        lines.append(f"[[SMS i={i}]]")
        lines.append(body[:500])
        meta_parts = []
        if ts:
            meta_parts.append(f"ts={ts}")
        if amount not in (None, ""):
            meta_parts.append(f"montant={amount}")
        if meta_parts:
            lines.append(f"meta: {', '.join(meta_parts)}")
        lines.append("[[/SMS]]")
    lines.append("[[/SMS_LIST]]")
    return "\n".join(lines)


def _format_ussd_path_for_agent(ussd_path: list) -> str:
    """Texte USSD pour le conseiller (jamais pour le client)."""
    if not ussd_path:
        return ""
    lines = [
        f"Chemin USSD Connect ({len(ussd_path)} étape(s)) :",
        f"[[USSD_PATH count={len(ussd_path)}]]",
    ]
    for i, step in enumerate(ussd_path, 1):
        lines.append(f"[[USSD i={i}]]")
        if isinstance(step, dict):
            # Affiche les clés utiles sans dump JSON brut illisible.
            for key in (
                "label",
                "title",
                "step",
                "action",
                "ussd",
                "code",
                "text",
                "message",
                "description",
            ):
                val = step.get(key)
                if val not in (None, ""):
                    lines.append(f"{key}: {str(val).strip()[:300]}")
            # Si rien de connu, une ligne compacte.
            if len(lines) and lines[-1] == f"[[USSD i={i}]]":
                lines.append(str(step)[:400])
        else:
            lines.append(str(step).strip()[:400] or "(vide)")
        lines.append("[[/USSD]]")
    lines.append("[[/USSD_PATH]]")
    return "\n".join(lines)



def _normalize_nearby_messages(raw: Any) -> list[dict]:
    """Nearby = indicatif seulement (jamais une preuve / is_match false)."""
    if not isinstance(raw, list):
        return []
    items: list[dict] = []
    for entry in raw[:3]:
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        item["is_match"] = False
        items.append(item)
    return items


def _sms_proof_user_message(
    result: str,
    connect_message: str | None = None,
    *,
    nearby: list[dict] | None = None,
) -> tuple[str, bool]:
    """
    Message chatbot client + besoin d'escalade humaine.
    Ne crédite jamais : escalate pour revue admin quand une preuve existe.
    Les nearby SMS restent dans nearby_messages / agent_message — jamais ici.
    """
    key = (result or "").strip().lower()
    del nearby  # réservé au contexte agent, pas au message client
    capture_received = (
        "Nous avons bien reçu votre capture. "
        "Un conseiller va la vérifier et revenir vers vous."
    )
    if key in {
        "confirmed",
        "possible",
        "ambiguous",
        "not_found",
        "mismatch",
    }:
        return (capture_received, True)
    if key == "tx_already_success":
        return (
            "Cette transaction est déjà marquée en succès côté opérateur. "
            "Si le solde n'apparaît pas, un conseiller pourra vérifier.",
            True,
        )
    if key == "tx_not_found":
        return (
            "La transaction Connect Pro liée est introuvable. Un conseiller vérifiera le dossier.",
            True,
        )
    if key == "forbidden":
        return (
            "Impossible de vérifier cette preuve auprès de Connect Pro. "
            "Un conseiller prendra le relais.",
            True,
        )
    return (
        connect_message
        or "La vérification SMS/notification n'a pas pu aboutir. Un conseiller vérifiera.",
        True,
    )


def build_verify_sms_proof_response(
    *,
    reference: str,
    type_raw: str = "",
    amount: str = "",
    tid: str = "",
    ref: str = "",
    operator_id: str = "",
    operation_at: str = "",
) -> tuple[dict, int]:
    """
    Vérifie une preuve SMS/FCM via Connect Pro.

    - transaction_uid = transaction.public_id
    - network_id = get_network_id("{name}-{country_code}") comme dépôt/retrait
    - amount / phone = ceux de la transaction (amount surchargeable via requête)
    - operation_at (optionnel) → sinon created_at de la TX
    - Fenêtre Connect : operation_at → now ; nearby = 3 derniers SMS (pas une preuve)
    - tid / ref / id = extraits de la capture
    - L'utilisateur envoie surtout la référence.
    """
    if not (reference or "").strip():
        return {
            "found": False,
            "phase": "done",
            "ok": False,
            "sms_found": False,
            "result": "missing_params",
            "validates_transaction": False,
            "message": "Merci d'indiquer la référence de la transaction.",
            "needs_escalation": False,
            "candidates": [],
            "nearby_messages": [],
        }, status.HTTP_400_BAD_REQUEST

    type_trans = _normalize_type(type_raw) if type_raw else None
    if type_raw and not type_trans:
        return {
            "found": False,
            "phase": "done",
            "ok": False,
            "result": "missing_params",
            "validates_transaction": False,
            "message": "Type invalide. Indiquez dépôt ou retrait.",
            "needs_escalation": False,
            "candidates": [],
            "nearby_messages": [],
        }, status.HTTP_400_BAD_REQUEST

    transaction = _find_transaction_by_reference(reference)
    if not transaction:
        return {
            "found": False,
            "phase": "done",
            "ok": False,
            "sms_found": False,
            "result": "tx_not_found",
            "validates_transaction": False,
            "reference": reference.strip(),
            "message": (
                "Nous n'avons trouvé aucune transaction Blaffa avec cette référence."
            ),
            "needs_escalation": False,
            "candidates": [],
            "nearby_messages": [],
        }, status.HTTP_200_OK

    if type_trans and transaction.type_trans != type_trans:
        expected = "dépôt" if transaction.type_trans == "deposit" else "retrait"
        return {
            "found": False,
            "phase": "done",
            "ok": False,
            "sms_found": False,
            "result": "mismatch",
            "validates_transaction": False,
            "reference": transaction.reference,
            "type": transaction.type_trans,
            "message": (
                f"Cette référence correspond à un {expected}, pas au type indiqué."
            ),
            "needs_escalation": False,
            "candidates": [],
            "nearby_messages": [],
        }, status.HTTP_200_OK

    connect_uid = (transaction.public_id or "").strip()
    if not connect_uid:
        intro = _intro(transaction, transaction.type_trans)
        return _base_payload(
            transaction,
            message=(
                f"{intro} Impossible de vérifier la preuve SMS : aucun public_id "
                "Connect Pro n'est lié à cette transaction. Un conseiller vérifiera."
            ),
            phase="done",
            ok=False,
            sms_found=False,
            result="missing_connect_uid",
            validates_transaction=False,
            needs_escalation=True,
            candidates=[],
            nearby_messages=[],
        ), status.HTTP_200_OK

    phone_norm = _digits(transaction.phone_number)
    if not phone_norm:
        intro = _intro(transaction, transaction.type_trans)
        return _base_payload(
            transaction,
            message=(
                f"{intro} Impossible de vérifier la preuve : aucun numéro n'est "
                "enregistré sur cette transaction. Un conseiller vérifiera."
            ),
            phase="done",
            ok=False,
            sms_found=False,
            result="missing_phone",
            validates_transaction=False,
            needs_escalation=True,
            candidates=[],
            nearby_messages=[],
        ), status.HTTP_200_OK

    amount_norm = _normalize_amount_str(amount) or _normalize_amount_str(transaction.amount)
    if not amount_norm:
        intro = _intro(transaction, transaction.type_trans)
        return _base_payload(
            transaction,
            message=(
                f"{intro} Impossible de vérifier la preuve : montant manquant "
                "sur la transaction. Un conseiller vérifiera."
            ),
            phase="done",
            ok=False,
            sms_found=False,
            result="missing_amount",
            validates_transaction=False,
            needs_escalation=True,
            candidates=[],
            nearby_messages=[],
        ), status.HTTP_200_OK

    # operation_at app → sinon created_at TX (Connect : start → now)
    resolved_operation_at = _to_iso_utc(operation_at) or _to_iso_utc(
        getattr(transaction, "created_at", None)
    )

    resolved_network_id = _resolve_connect_network_id(transaction)
    connect_result = connect_pro_verify_transaction_by_user_sms(
        transaction_uid=connect_uid,
        amount=amount_norm,
        phone=phone_norm,
        network_id=resolved_network_id,
        tid=tid,
        ref=ref,
        operator_id=operator_id,
        operation_at=resolved_operation_at,
    )
    result_key = str(connect_result.get("result") or "technical_error")

    # L'endpoint verify de Connect ne retrouve plus les transactions expirées
    # (404 tx_not_found) alors que le statut expose encore les SMS reçus :
    # on compare alors la preuve capture aux SMS rattachés à la transaction.
    verify_fallback = None
    if result_key not in {"confirmed", "possible", "ambiguous", "tx_already_success"}:
        verify_fallback = _match_proof_against_status_sms(
            transaction, amount=amount_norm, tid=tid, ref=ref
        )
        if verify_fallback is not None:
            connect_result = verify_fallback
            result_key = str(verify_fallback.get("result"))

    nearby = _normalize_nearby_messages(connect_result.get("nearby_messages"))
    # Never treat nearby as proof — only surface on not_found / mismatch
    if result_key not in {"not_found", "mismatch"}:
        nearby = []

    user_message, needs_escalation = _sms_proof_user_message(
        result_key,
        connect_message=str(connect_result.get("message") or ""),
        nearby=nearby,
    )
    intro = _intro(transaction, transaction.type_trans)
    agent_nearby = _format_nearby_for_agent(nearby)
    agent_fallback = (
        f"{intro} {user_message}".strip()
        + (f"\n\n{agent_nearby}" if agent_nearby else "")
    ).strip()
    agent_message = _sms_verify_agent_message(
        transaction,
        result_key=result_key,
        connect_result=connect_result,
        nearby=nearby,
        fallback=agent_fallback,
    )

    # ok=true seulement si Connect confirme une preuve exploitable.
    # nearby_messages ne compte JAMAIS comme preuve.
    connect_ok = bool(connect_result.get("ok")) and result_key in {
        "confirmed",
        "possible",
    }
    return _base_payload(
        transaction,
        message=f"{intro} {user_message}".strip(),
        phase="done",
        ok=connect_ok,
        sms_found=connect_result.get("sms_found"),
        result=result_key,
        match_score=connect_result.get("match_score"),
        validates_transaction=False,
        needs_escalation=needs_escalation,
        refs_used=connect_result.get("refs_used") or [],
        candidates=connect_result.get("candidates") or [],
        nearby_messages=nearby,
        agent_message=agent_message,
        search_from=connect_result.get("search_from"),
        search_to=connect_result.get("search_to"),
        network_warning=connect_result.get("network_warning"),
        connect_verify={
            "transaction_uid": connect_uid,
            "network_id": resolved_network_id,
            "network_code": (
                get_connect_network_code(transaction.network)
                if transaction.network and transaction.network.name
                else None
            ),
            "amount_sent": amount_norm,
            "amount_source": "request" if _normalize_amount_str(amount) else "transaction",
            "phone_sent": phone_norm,
            "operation_at": resolved_operation_at,
            "tid": tid or None,
            "ref": ref or None,
            "id": operator_id or None,
            "raw_result": result_key,
            "connect_message": connect_result.get("message"),
            "fallback": (
                "status_sms" if verify_fallback is not None else None
            ),
        },
    ), status.HTTP_200_OK


class PublicTransactionLookupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        body, code = build_lookup_response(
            reference=(request.query_params.get("reference") or "").strip(),
            type_raw=(
                request.query_params.get("type")
                or request.query_params.get("type_trans")
                or ""
            ).strip(),
            phone_number=(
                request.query_params.get("phone_number")
                or request.query_params.get("phone")
                or ""
            ).strip(),
        )
        return Response(body, status=code)


class PublicTransactionConfirmPaymentView(APIView):
    """
    Suite du lookup dépôt (preuve / capture).
    Lecture seule — aucun crédit ni appel Connect.
    GET ?reference=&type=&phone_number=&money_sent=oui|non&has_screenshot=true|false
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        body, code = build_confirm_payment_response(
            reference=(request.query_params.get("reference") or "").strip(),
            type_raw=(
                request.query_params.get("type")
                or request.query_params.get("type_trans")
                or ""
            ).strip(),
            phone_number=(
                request.query_params.get("phone_number")
                or request.query_params.get("phone")
                or ""
            ).strip(),
            money_sent_raw=(
                request.query_params.get("money_sent")
                or request.query_params.get("money_left")
                or ""
            ).strip(),
            has_screenshot_raw=(
                request.query_params.get("has_screenshot")
                or request.query_params.get("screenshot")
                or request.query_params.get("payment_proof")
                or ""
            ).strip(),
        )
        return Response(body, status=code)


class PublicTransactionVerifySmsProofView(APIView):
    """
    Vérifie une capture / SMS extrait via Connect Pro
    (verify-transaction-by-user-sms). Ne valide jamais la TX.

    POST JSON (ou GET query) :
      reference (obligatoire — référence),
      type?, amount? (sinon montant TX),
      operation_at? (sinon created_at TX),
      tid?, ref?, id? (extraits capture)
    → transaction_uid = public_id
    → network_id = get_network_id("{name}-{country_code}")
    → phone = phone_number de la TX
    → nearby_messages = 3 derniers SMS si not_found/mismatch (pas une preuve)
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def _params(self, request) -> dict:
        data = {}
        if isinstance(getattr(request, "data", None), dict):
            data.update(request.data)
        data.update(request.query_params.dict())
        return data

    def post(self, request):
        return self._handle(request)

    def get(self, request):
        return self._handle(request)

    def _handle(self, request):
        data = self._params(request)
        body, code = build_verify_sms_proof_response(
            reference=_first_nonempty(data.get("reference"), data.get("blaffa_reference")),
            type_raw=_first_nonempty(data.get("type"), data.get("type_trans")),
            amount=_first_nonempty(data.get("amount"), data.get("montant")),
            tid=_first_nonempty(data.get("tid")),
            ref=_first_nonempty(
                data.get("ref"),
                data.get("operator_ref"),
                data.get("reference_op"),
            ),
            operator_id=_first_nonempty(
                data.get("id"),
                data.get("operator_id"),
                data.get("wave_id"),
            ),
            operation_at=_first_nonempty(
                data.get("operation_at"),
                data.get("operated_at"),
                data.get("sms_at"),
            ),
        )
        return Response(body, status=code)


def _resolve_tx_for_connect_action(
    *,
    reference: str,
    expected_type: str | None = None,
) -> tuple[Transaction | None, dict | None, int]:
    """Résout une TX pour action Connect (uid = public_id)."""
    if not (reference or "").strip():
        return None, {
            "ok": False,
            "result": "missing_params",
            "message": "Merci d'indiquer la référence de la transaction.",
        }, status.HTTP_400_BAD_REQUEST

    transaction = _find_transaction_by_reference(reference)
    if not transaction:
        return None, {
            "ok": False,
            "result": "tx_not_found",
            "reference": reference.strip(),
            "message": "Aucune transaction avec cette référence.",
        }, status.HTTP_200_OK

    if expected_type and transaction.type_trans != expected_type:
        expected = "dépôt" if expected_type == "deposit" else "retrait"
        return None, {
            "ok": False,
            "result": "mismatch",
            "reference": transaction.reference,
            "type": transaction.type_trans,
            "message": f"Cette référence n'est pas un {expected}.",
        }, status.HTTP_200_OK

    connect_uid = (transaction.public_id or "").strip()
    if not connect_uid:
        return None, _base_payload(
            transaction,
            message=(
                "Impossible d'appeler Connect : aucun public_id lié à cette transaction."
            ),
            ok=False,
            result="missing_connect_uid",
            needs_escalation=True,
        ), status.HTTP_200_OK

    return transaction, None, status.HTTP_200_OK


def _mark_tx_fixed_via_bot(
    transaction: Transaction,
    *,
    action: str,
    note: str = "",
    connect_result: dict | None = None,
) -> None:
    """Marque une TX comme corrigée via agent/bot après action Connect OK."""
    msg = "Corrigé via agent/bot"
    try:
        transaction.bot_transaction = True
        transaction.message = msg
        transaction.save(update_fields=["bot_transaction", "message"])
        TransactionStatusHistory.objects.create(
            transaction=transaction,
            old_status=transaction.status,
            new_status=transaction.status,
            trigger_source=TransactionStatusHistory.Source.AGENT_BOT,
            trigger_data={
                "action": action,
                "note": (note or "").strip(),
                "connect_uid": (transaction.public_id or "").strip(),
                "connect_action": connect_result or {},
                "bot_transaction": True,
            },
            message=msg,
        )
        logger.info(
            "TX %s marked bot_transaction=True via AGENT_BOT action=%s",
            transaction.reference,
            action,
        )
    except Exception:
        logger.exception(
            "Failed to mark TX %s as fixed via bot (action=%s)",
            getattr(transaction, "reference", None),
            action,
        )


def build_confirm_withdrawal_response(
    *,
    reference: str,
    amount: str = "",
    note: str = "",
) -> tuple[dict, int]:
    """
    Endpoint public confirm-withdrawal.

    Mapping imposé:
    - dépôt Betpay → Connect confirm-withdrawal
    - amount jamais envoyé à Connect (MoMoPay/Wave le refuse)
    """
    from django.conf import settings as dj_settings

    if not getattr(dj_settings, "ALLOW_USER_TRANSACTION_ACTIONS", False):
        return {
            "ok": False,
            "result": "actions_disabled",
            "message": (
                "Actions utilisateur désactivées "
                "(ALLOW_USER_TRANSACTION_ACTIONS=False)."
            ),
            "needs_escalation": True,
        }, status.HTTP_403_FORBIDDEN

    transaction, err, code = _resolve_tx_for_connect_action(
        reference=reference, expected_type="deposit"
    )
    if err is not None:
        return err, code

    # Ne jamais forward amount vers Connect.
    connect_result = connect_pro_confirm_withdrawal(
        transaction_uid=transaction.public_id,
        amount=None,
        note=note,
    )
    http_status = int(connect_result.get("http_status") or 200)
    ok = bool(connect_result.get("ok")) and http_status < 400
    if http_status == 403:
        msg = (
            "Action confirm-withdrawal désactivée côté Connect "
            "(ALLOW_USER_TRANSACTION_ACTIONS=False)."
        )
        return _base_payload(
            transaction,
            message=msg,
            ok=False,
            result="actions_disabled",
            connect_action=connect_result,
            needs_escalation=True,
        ), status.HTTP_403_FORBIDDEN

    if ok:
        msg = "Dépôt traité via confirm-withdrawal côté Connect."
        result = "confirmed"
        _mark_tx_fixed_via_bot(
            transaction,
            action="confirm-withdrawal",
            note=note,
            connect_result=connect_result if isinstance(connect_result, dict) else None,
        )
        transaction.refresh_from_db(fields=["bot_transaction", "message", "status"])
    else:
        connect_detail = (
            connect_result.get("detail")
            or connect_result.get("error")
            or connect_result.get("message")
            or ""
        )
        msg = str(connect_detail).strip() or "Échec du traitement du dépôt côté Connect."
        if http_status:
            msg = f"{msg} (Connect HTTP {http_status})"
        result = "error"

    return _base_payload(
        transaction,
        message=msg,
        ok=ok,
        result=result,
        connect_action=connect_result,
        connect_uid=transaction.public_id,
        bot_transaction=bool(getattr(transaction, "bot_transaction", False)),
        needs_escalation=not ok,
    ), status.HTTP_200_OK


def build_retry_deposit_response(
    *,
    reference: str,
    amount: str = "",
    note: str = "",
) -> tuple[dict, int]:
    """
    Endpoint public retry-deposit.

    Mapping imposé:
    - retrait Betpay → Connect retry-deposit
    """
    from django.conf import settings as dj_settings

    if not getattr(dj_settings, "ALLOW_USER_TRANSACTION_ACTIONS", False):
        return {
            "ok": False,
            "result": "actions_disabled",
            "message": (
                "Actions utilisateur désactivées "
                "(ALLOW_USER_TRANSACTION_ACTIONS=False)."
            ),
            "needs_escalation": True,
        }, status.HTTP_403_FORBIDDEN

    transaction, err, code = _resolve_tx_for_connect_action(
        reference=reference, expected_type="withdrawal"
    )
    if err is not None:
        return err, code

    # Ne jamais forward amount vers Connect.
    connect_result = connect_pro_retry_deposit(
        transaction_uid=transaction.public_id,
        note=note,
    )
    http_status = int(connect_result.get("http_status") or 200)
    ok = bool(connect_result.get("ok")) and http_status < 400
    if http_status == 403:
        msg = (
            "Action retry-deposit désactivée côté Connect "
            "(ALLOW_USER_TRANSACTION_ACTIONS=False)."
        )
        return _base_payload(
            transaction,
            message=msg,
            ok=False,
            result="actions_disabled",
            connect_action=connect_result,
            needs_escalation=True,
        ), status.HTTP_403_FORBIDDEN

    if ok:
        msg = "Retrait traité via retry-deposit côté Connect."
        result = "retried"
        _mark_tx_fixed_via_bot(
            transaction,
            action="retry-deposit",
            note=note,
            connect_result=connect_result if isinstance(connect_result, dict) else None,
        )
        transaction.refresh_from_db(fields=["bot_transaction", "message", "status"])
    else:
        connect_detail = (
            connect_result.get("detail")
            or connect_result.get("error")
            or connect_result.get("message")
            or ""
        )
        msg = str(connect_detail).strip() or "Échec du traitement du retrait côté Connect."
        if http_status:
            msg = f"{msg} (Connect HTTP {http_status})"
        result = "error"

    return _base_payload(
        transaction,
        message=msg,
        ok=ok,
        result=result,
        connect_action=connect_result,
        connect_uid=transaction.public_id,
        bot_transaction=bool(getattr(transaction, "bot_transaction", False)),
        needs_escalation=not ok,
    ), status.HTTP_200_OK


class PublicTransactionConfirmWithdrawalView(APIView):
    """
    POST : reference (Blaffa), amount?, note?
    Mapping: dépôt Betpay → Connect confirm-withdrawal
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = {}
        if isinstance(getattr(request, "data", None), dict):
            data.update(request.data)
        data.update(request.query_params.dict())
        body, code = build_confirm_withdrawal_response(
            reference=_first_nonempty(data.get("reference"), data.get("blaffa_reference")),
            amount=_first_nonempty(data.get("amount"), data.get("montant")),
            note=_first_nonempty(data.get("note"), data.get("commentaire")),
        )
        return Response(body, status=code)


class PublicTransactionRetryDepositView(APIView):
    """
    POST : reference (Blaffa), note?
    Mapping: retrait Betpay → Connect retry-deposit
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = {}
        if isinstance(getattr(request, "data", None), dict):
            data.update(request.data)
        data.update(request.query_params.dict())
        body, code = build_retry_deposit_response(
            reference=_first_nonempty(data.get("reference"), data.get("blaffa_reference")),
            amount=_first_nonempty(data.get("amount"), data.get("montant")),
            note=_first_nonempty(data.get("note"), data.get("commentaire")),
        )
        return Response(body, status=code)

def build_expire_transaction_response(
    *,
    reference: str,
    note: str = "",
) -> tuple[dict, int]:
    """
    Endpoint public agent : marque une TX en expired.
    Idempotent si déjà expired.
    """
    if not (reference or "").strip():
        return {
            "ok": False,
            "result": "missing_params",
            "message": "Merci d'indiquer la référence de la transaction.",
        }, status.HTTP_400_BAD_REQUEST

    transaction = (
        Transaction.objects.select_related("app", "network")
        .filter(reference=reference.strip())
        .first()
    )
    if not transaction:
        return {
            "ok": False,
            "result": "tx_not_found",
            "reference": reference.strip(),
            "message": "Aucune transaction avec cette référence.",
        }, status.HTTP_200_OK

    if transaction.status == "accept":
        return _base_payload(
            transaction,
            message=(
                "Cette transaction est déjà acceptée : "
                "elle ne peut pas être passée en expired."
            ),
            ok=False,
            result="already_accepted",
            needs_escalation=True,
        ), status.HTTP_200_OK

    if transaction.status == "expired":
        return _base_payload(
            transaction,
            message="Transaction déjà expirée.",
            ok=True,
            result="already_expired",
            needs_escalation=False,
        ), status.HTTP_200_OK

    reason = (note or "").strip() or "Refusé depuis l'app agent support"
    old_status = transaction.status
    transaction.status = "expired"
    transaction.error_message = reason[:1000]
    transaction.save(update_fields=["status", "error_message"])
    try:
        TransactionStatusHistory.objects.create(
            transaction=transaction,
            old_status=old_status,
            new_status="expired",
            trigger_source=TransactionStatusHistory.Source.AGENT_BOT,
            trigger_data={
                "action": "expire",
                "note": reason[:500],
            },
            message=reason[:500],
        )
    except Exception:
        logger.exception("TransactionStatusHistory expire failed ref=%s", reference)

    logger.info(
        "TX expired by support ref=%s from=%s",
        transaction.reference,
        old_status,
    )
    return _base_payload(
        transaction,
        message="Transaction passée en expired.",
        ok=True,
        result="expired",
        previous_status=old_status,
        needs_escalation=False,
    ), status.HTTP_200_OK


class PublicTransactionExpireView(APIView):
    """
    POST : reference, note?
    Passe la transaction en status=expired (refus agent).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = {}
        if isinstance(getattr(request, "data", None), dict):
            data.update(request.data)
        data.update(request.query_params.dict())
        body, code = build_expire_transaction_response(
            reference=_first_nonempty(data.get("reference"), data.get("blaffa_reference")),
            note=_first_nonempty(data.get("note"), data.get("commentaire"), data.get("reason")),
        )
        return Response(body, status=code)
