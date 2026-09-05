"""
Gestion liste noire / dette après annulation Connect (transaction_request_cancel).

- Cancel webhook → debt += amount, status txn inchangé
- Déjà en liste noire → dépôt sans crédit plateforme / retrait sans Connect, debt -= amount
- debt = 0 : toujours en liste (blocage continue). Sortie = DELETE admin uniquement.
"""

from __future__ import annotations

import json
from typing import Iterable, Optional, Set, Tuple

from django.db import transaction as db_transaction
from django.db.models import Q

from mobcash_inte.models import (
    CancellationDebtBlacklist,
    CancellationDebtEvent,
    IDLink,
    Transaction,
    UserPhone,
)


def is_transaction_request_cancel(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("transaction_request_cancel") is True:
        return True
    extracted = data.get("extracted_data") or {}
    if isinstance(extracted, dict) and extracted.get("transaction_request_cancel") is True:
        return True
    return False


def normalize_phone(phone) -> Optional[str]:
    if phone is None:
        return None
    digits = "".join(c for c in str(phone) if c.isdigit())
    return digits or None


def _merge_unique(existing: Iterable, additions: Iterable) -> list:
    seen = set()
    out = []
    for item in list(existing or []) + list(additions or []):
        if item is None:
            continue
        val = str(item).strip()
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def _safe_user_phones(user) -> Set[str]:
    phones: Set[str] = set()
    if not user:
        return phones
    try:
        for p in UserPhone.objects.filter(user=user).values_list("phone", flat=True):
            n = normalize_phone(p)
            if n:
                phones.add(n)
    except Exception:
        pass
    return phones


def collect_identifiers(
    *,
    user=None,
    phone=None,
    user_app_id=None,
) -> Tuple[Set[str], Set[str], Set[str]]:
    """Retourne (user_ids, phones, bet_app_ids)."""
    user_ids: Set[str] = set()
    phones: Set[str] = set()
    bet_ids: Set[str] = set()

    n = normalize_phone(phone)
    if n:
        phones.add(n)
    if user_app_id:
        bet_ids.add(str(user_app_id).strip())

    if user:
        user_ids.add(str(user.id))
        phones |= _safe_user_phones(user)

        for link in IDLink.objects.filter(user=user).values_list("user_app_id", flat=True):
            if link:
                bet_ids.add(str(link).strip())

        for p in (
            Transaction.objects.filter(user=user)
            .exclude(phone_number__isnull=True)
            .exclude(phone_number="")
            .values_list("phone_number", flat=True)
            .distinct()
        ):
            np = normalize_phone(p)
            if np:
                phones.add(np)

        for uid in (
            Transaction.objects.filter(user=user)
            .exclude(user_app_id__isnull=True)
            .exclude(user_app_id="")
            .values_list("user_app_id", flat=True)
            .distinct()
        ):
            bet_ids.add(str(uid).strip())

    return user_ids, phones, bet_ids


def collect_identifiers_from_transaction(transaction) -> Tuple[Set[str], Set[str], Set[str]]:
    user = getattr(transaction, "user", None)
    return collect_identifiers(
        user=user,
        phone=getattr(transaction, "phone_number", None),
        user_app_id=getattr(transaction, "user_app_id", None),
    )


def _q_overlap(user_ids: Set[str], phones: Set[str], bet_ids: Set[str]) -> Q:
    q = Q()
    for uid in user_ids:
        q |= Q(user_ids__contains=[uid])
    for phone in phones:
        q |= Q(phones__contains=[phone])
    for bid in bet_ids:
        q |= Q(bet_app_ids__contains=[bid])
    return q


def find_blacklist(
    *,
    user=None,
    phone=None,
    user_app_id=None,
    require_debt: bool = False,
    require_active: bool = True,
) -> Optional[CancellationDebtBlacklist]:
    user_ids, phones, bet_ids = collect_identifiers(
        user=user, phone=phone, user_app_id=user_app_id
    )
    if not user_ids and not phones and not bet_ids:
        return None

    qs = CancellationDebtBlacklist.objects.filter(
        _q_overlap(user_ids, phones, bet_ids)
    ).order_by("-debt_amount", "-updated_at")
    if require_active:
        qs = qs.filter(is_active=True)
    if require_debt:
        qs = qs.filter(debt_amount__gt=0)

    return qs.first()


def find_blacklist_for_transaction(
    transaction, *, require_debt: bool = False, require_active: bool = True
) -> Optional[CancellationDebtBlacklist]:
    return find_blacklist(
        user=getattr(transaction, "user", None),
        phone=getattr(transaction, "phone_number", None),
        user_app_id=getattr(transaction, "user_app_id", None),
        require_debt=require_debt,
        require_active=require_active,
    )


def build_debt_message(blacklist: CancellationDebtBlacklist) -> str:
    refs = blacklist.cancelled_references or []
    refs_txt = ", ".join(str(r) for r in refs) if refs else "N/A"
    return (
        "Cet utilisateur est en liste noire (annulation Connect). "
        f"Référence(s) annulée(s) : {refs_txt}. "
        f"Dette restante : {int(blacklist.debt_amount)} FCFA. "
        "Sortie uniquement par suppression admin."
    )


def _merge_blacklists(entries: list) -> Optional[CancellationDebtBlacklist]:
    if not entries:
        return None
    primary = entries[0]
    if len(entries) == 1:
        return primary

    for other in entries[1:]:
        if other.id == primary.id:
            continue
        primary.debt_amount = int(primary.debt_amount or 0) + int(other.debt_amount or 0)
        primary.user_ids = _merge_unique(primary.user_ids, other.user_ids)
        primary.phones = _merge_unique(primary.phones, other.phones)
        primary.bet_app_ids = _merge_unique(primary.bet_app_ids, other.bet_app_ids)
        primary.cancelled_references = _merge_unique(
            primary.cancelled_references, other.cancelled_references
        )
        CancellationDebtEvent.objects.filter(blacklist=other).update(blacklist=primary)
        other.delete()

    primary.is_active = True
    primary.save()
    return primary


def register_cancellation_from_webhook(transaction, webhook_data: dict) -> CancellationDebtBlacklist:
    """
    Annulation Connect: ajoute/merge la blacklist et debt += amount.
    Ne modifie PAS le status de la transaction.
    """
    user_ids, phones, bet_ids = collect_identifiers_from_transaction(transaction)
    amount = int(getattr(transaction, "amount", 0) or 0)
    reference = getattr(transaction, "reference", None)

    with db_transaction.atomic():
        overlaps = list(
            CancellationDebtBlacklist.objects.select_for_update()
            .filter(_q_overlap(user_ids, phones, bet_ids))
            .order_by("-debt_amount", "-updated_at")
        )
        blacklist = _merge_blacklists(overlaps)
        if not blacklist:
            blacklist = CancellationDebtBlacklist.objects.create(
                debt_amount=0,
                user_ids=list(user_ids),
                phones=list(phones),
                bet_app_ids=list(bet_ids),
                cancelled_references=[],
                is_active=True,
            )
        else:
            blacklist.user_ids = _merge_unique(blacklist.user_ids, user_ids)
            blacklist.phones = _merge_unique(blacklist.phones, phones)
            blacklist.bet_app_ids = _merge_unique(blacklist.bet_app_ids, bet_ids)

        blacklist.debt_amount = int(blacklist.debt_amount or 0) + amount
        if reference:
            blacklist.cancelled_references = _merge_unique(
                blacklist.cancelled_references, [reference]
            )
        blacklist.is_active = True
        message = build_debt_message(blacklist)
        blacklist.last_message = message
        blacklist.save()

        CancellationDebtEvent.objects.create(
            blacklist=blacklist,
            transaction=transaction if isinstance(transaction, Transaction) else None,
            event_type="cancel_add",
            amount=amount,
            reference=reference,
            message=message,
            webhook_data=webhook_data if isinstance(webhook_data, dict) else {},
        )

        try:
            if hasattr(transaction, "error_message"):
                transaction.error_message = message
                transaction.webhook_data = (
                    json.dumps(webhook_data)
                    if isinstance(webhook_data, dict)
                    else str(webhook_data)
                )
                transaction.save(update_fields=["error_message", "webhook_data"])
        except Exception:
            pass

        return blacklist


def apply_debt_repayment(
    *,
    blacklist: CancellationDebtBlacklist,
    transaction,
    amount: int,
    event_type: str,
) -> str:
    """
    Réduit la dette si > 0.
    Ne retire JAMAIS de la liste noire (is_active reste True ; sortie = DELETE admin).
    """
    amount = max(int(amount or 0), 0)
    user_ids, phones, bet_ids = collect_identifiers_from_transaction(transaction)

    with db_transaction.atomic():
        bl = (
            CancellationDebtBlacklist.objects.select_for_update()
            .filter(pk=blacklist.pk)
            .first()
        )
        if not bl:
            return ""

        bl.user_ids = _merge_unique(bl.user_ids, user_ids)
        bl.phones = _merge_unique(bl.phones, phones)
        bl.bet_app_ids = _merge_unique(bl.bet_app_ids, bet_ids)

        current = int(bl.debt_amount or 0)
        applied = min(amount, current)
        bl.debt_amount = max(current - applied, 0)
        bl.is_active = True

        message = build_debt_message(bl)
        bl.last_message = message
        bl.save()

        CancellationDebtEvent.objects.create(
            blacklist=bl,
            transaction=transaction if isinstance(transaction, Transaction) else None,
            event_type=event_type,
            amount=applied,
            reference=getattr(transaction, "reference", None),
            message=message,
            webhook_data={},
        )

        try:
            transaction.error_message = message
            if hasattr(transaction, "save"):
                transaction.save(update_fields=["error_message"])
        except Exception:
            pass

        return message


def should_block_for_debt(transaction) -> Optional[CancellationDebtBlacklist]:
    """Bloque dès qu'une entrée active existe (même si dette = 0)."""
    return find_blacklist_for_transaction(
        transaction, require_debt=False, require_active=True
    )
