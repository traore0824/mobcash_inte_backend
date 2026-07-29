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
            "public_name": transaction.app.public_name if transaction.app else None,
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
        f"Cependant, le numéro Mobile Money que vous avez indiqué ({indicated}) "
        f"ne correspond pas à celui enregistré sur cette transaction ({stored})."
    )

    transfer_retried = False
    transfer_ok = None
    needs_escalation = False
    phase = "done"

    if type_trans == "withdrawal":
        if transaction.status == "accept":
            if has_screenshot:
                detail = (
                    f"{mismatch} "
                    "Ce retrait a déjà été payé sur le numéro enregistré sur la transaction. "
                    "Nous avons bien reçu votre capture — un conseiller traitera le dossier "
                    f"avec la référence {transaction.reference}, le numéro indiqué ({indicated}) "
                    f"et le numéro sur la transaction ({stored})."
                )
                needs_escalation = True
                phase = "done"
            else:
                detail = (
                    f"{mismatch} "
                    "Ce retrait a déjà été payé sur le numéro enregistré. "
                    "Indiquez le numéro Mobile Money concerné, puis envoyez la capture "
                    "d'écran pour qu'un conseiller vérifie avant tout nouvel envoi."
                )
                phase = "await_payer_details"
        else:
            detail = (
                f"{mismatch} "
                "Aucun transfert n'est déclenché automatiquement. "
                "Un conseiller doit vérifier le numéro concerné et l'état du retrait."
            )
            needs_escalation = True
    else:
        # Dépôt : ne pas clôturer sans preuve — demander le vrai numéro + capture,
        # puis créer un transfert conseiller avec ces détails (pas de crédit auto).
        if has_screenshot:
            detail = (
                f"{mismatch} "
                "Nous avons bien reçu votre capture. Un conseiller va vérifier le dossier "
                f"avec la référence {transaction.reference}, le numéro indiqué ({indicated}), "
                f"le numéro sur la transaction ({stored}) et la preuve de paiement."
            )
            needs_escalation = True
            phase = "done"
        else:
            detail = (
                f"{mismatch} "
                "Le dépôt reste lié au numéro utilisé lors de l'opération. "
                "Merci d'envoyer le numéro Mobile Money qui a réellement effectué "
                "le transfert, puis la capture d'écran de l'opération."
            )
            phase = "await_payer_details"

    return _base_payload(
        transaction,
        message=f"{intro} {detail}".strip(),
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
            detail = (
                "Le paiement Mobile Money est bien passé et le crédit sur votre compte "
                "de jeu a été effectué avec succès. Si le solde n'apparaît pas encore, "
                "actualisez l'application ou reconnectez-vous."
            )
            return _base_payload(
                transaction,
                message=f"{intro} {detail}".strip(),
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

        # Paiement MM confirmé chez Connect (statut OK, ou preuve reçue :
        # confirmed_at / SMS opérateur, y compris transaction expirée)
        # → problème côté crédit Betpay.
        if connect_paid:
            return _base_payload(
                transaction,
                message=_deposit_connect_success_message(
                    transaction, phone_number=phone_number
                ),
                phase="done",
                phone_match=True,
                needs_escalation=True,
                connect=connect_meta,
                transfer_retry={"attempted": False, "success": None},
            ), status.HTTP_200_OK

        payer_phone = (transaction.phone_number or "").strip() or "le numéro utilisé"
        detail = (
            "Votre dépôt n'a pas encore été approuvé. "
            f"Merci de vérifier si c'est bien ce numéro ({payer_phone}) qui a effectué "
            "la transaction, car le problème peut venir de là. "
            "Si c'est bien ce numéro qui a payé, envoyez-nous la capture d'écran de votre paiement. "
            "Sinon, envoyez-nous le numéro qui a réellement effectué le paiement, "
            "accompagné de la capture d'écran."
        )
        return _base_payload(
            transaction,
            message=f"{intro} {detail}".strip(),
            phase="await_screenshot",
            phone_match=True,
            connect=connect_meta,
            transfer_retry={"attempted": False, "success": None},
        ), status.HTTP_200_OK

    connect_payload = _connect_status_payload(transaction)
    connect_class = _classify_connect(connect_payload)
    connect_ok = connect_class == "ok"
    connect_status = _connect_status_value(connect_payload)
    intro = _intro(transaction, type_trans)

    transfer_retried = False
    transfer_ok = None
    needs_escalation = False
    detail = ""

    if transaction.status == "accept":
        detail = (
            "Le retrait a bien été traité : l'argent a été envoyé vers votre numéro "
            "Mobile Money."
        )
    elif transaction.status == "payment_init_success" and connect_class != "ok":
        detail = (
            "Le montant a déjà été débité de votre compte de jeu, "
            "mais l'envoi Mobile Money n'était pas confirmé côté Connect "
            f"(statut : {connect_status or connect_class}). "
            "Aucune relance automatique n'est effectuée par cette vérification."
        )
        needs_escalation = True
    elif transaction.status == "payment_init_success" and connect_ok:
        detail = (
            "Le compte de jeu a été débité et l'envoi Mobile Money est confirmé côté opérateur."
        )
    else:
        detail = (
            "Le retrait est encore en cours de traitement. "
            f"Statut actuel : {transaction.message or transaction.status}."
        )

    return _base_payload(
        transaction,
        message=f"{intro} {detail}".strip(),
        phase="done",
        phone_match=True,
        needs_escalation=needs_escalation,
        connect={
            "checked": connect_payload is not None,
            "ok": connect_ok,
            "status": connect_status,
            "class": connect_class,
        },
        transfer_retry={"attempted": transfer_retried, "success": transfer_ok},
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

    # Capture reçue = preuve que l'argent a quitté le compte.
    # Sans capture : un seul rappel (pas de question oui/non séparée).
    if not has_screenshot:
        if money_sent is False:
            return _base_payload(
                transaction,
                message=(
                    f"{intro} D'accord. Tant que le débit Mobile Money n'est pas effectif, "
                    "nous ne pouvons pas forcer le crédit. Validez le paiement USSD / le lien, "
                    "puis revenez vers nous avec la référence si besoin."
                ),
                phase="done",
                phone_match=True,
                needs_escalation=False,
            ), status.HTTP_200_OK
        return _base_payload(
            transaction,
            message=(
                f"{intro} Si l'argent a bien quitté votre compte Mobile Money, "
                "envoyez-nous la capture d'écran de votre transfert."
            ),
            phase="await_screenshot",
            phone_match=True,
            money_sent=True if money_sent else None,
            needs_escalation=False,
        ), status.HTTP_200_OK

    # Lecture seule : la preuve est signalée, sans crédit ni transfert automatique.
    if type_trans == "deposit":
        detail = (
            "Nous avons bien reçu votre capture. La vérification ne modifie pas la transaction "
            "et ne déclenche aucun crédit automatique. Un conseiller vérifiera la preuve."
        )
        return _base_payload(
            transaction,
            message=f"{intro} {detail}".strip(),
            phase="done",
            phone_match=True,
            money_sent=True,
            has_screenshot=True,
            needs_escalation=True,
            transfer_retry={"attempted": False, "success": None, "reason": "read_only_lookup"},
        ), status.HTTP_200_OK

    # Retrait : lecture seule, aucune relance de payout.
    if transaction.status == "accept":
        detail = (
            "Votre capture est bien reçue. Ce retrait apparaît déjà comme payé. "
            "Un conseiller vérifiera si un nouvel envoi est nécessaire."
        )
    else:
        detail = (
            "Votre capture est bien reçue. La vérification ne modifie pas la transaction "
            "et ne relance aucun transfert. Un conseiller vérifiera le dossier."
        )
    return _base_payload(
        transaction,
        message=f"{intro} Merci pour la capture. {detail}".strip(),
        phase="done",
        phone_match=True,
        money_sent=True,
        has_screenshot=True,
        needs_escalation=True,
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
    if key == "confirmed":
        return (
            "Nous avons trouvé une preuve SMS correspondant à votre opération. "
            "Le blocage est de notre côté, pas un problème de paiement de votre part. "
            "Nous allons finaliser le crédit. Vous recevrez votre argent sur votre compte sous peu.",
            True,
        )
    if key == "possible":
        return (
            "Nous avons trouvé une correspondance partielle (SMS). "
            "Un conseiller vérifiera manuellement avant de finaliser le crédit.",
            True,
        )
    if key == "ambiguous":
        return (
            "Plusieurs preuves SMS/notification correspondent. "
            "Un conseiller doit vérifier manuellement.",
            True,
        )
    if key == "not_found":
        return (
            "Nous n'avons trouvé aucun SMS/notification correspondant à cette opération "
            "(recherche depuis l'heure d'opération jusqu'à maintenant). "
            "Un conseiller vérifiera votre capture.",
            True,
        )
    if key == "mismatch":
        # Éviter de remonter le debug Connect brut (ex. amount_ok=False, phone_ok=True).
        raw = (connect_message or "").strip()
        looks_like_debug = (
            "amount_ok=" in raw.lower()
            or "phone_ok=" in raw.lower()
            or "derniers SMS" in raw
            or "nearby" in raw.lower()
        )
        if raw and not looks_like_debug:
            msg = raw
        else:
            msg = (
                "Les informations de la capture ne correspondent pas à la transaction. "
                "Merci de vérifier le montant / numéro, ou un conseiller prendra le relais."
            )
        return (msg, True)
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
    - operation_at (optionnel) → sinon created_at de la TX Blaffa
    - Fenêtre Connect : operation_at → now ; nearby = 3 derniers SMS (pas une preuve)
    - tid / ref / id = extraits de la capture
    - L'utilisateur envoie surtout la référence Blaffa.
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

    # operation_at app → sinon created_at TX Blaffa (Connect : start → now)
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
    agent_message = (
        f"{intro} {user_message}".strip()
        + (f"\n\n{agent_nearby}" if agent_nearby else "")
    ).strip()

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
      reference (obligatoire — référence Blaffa),
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
    """Résout une TX Blaffa pour action Connect (uid = public_id)."""
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
            "message": "Aucune transaction Blaffa avec cette référence.",
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
