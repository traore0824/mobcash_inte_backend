"""
Service BetMomo — topup, payout, polling statut via BeWallet External API.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from .client import BetmomoClient

logger = logging.getLogger("mobcash_inte")

INITIATED_STATUSES = frozenset({"initiated", "pending", "processing", "in_progress"})
SUCCESS_STATUSES = frozenset(
    {"success", "successful", "completed", "complete", "done", "ok", "confirmed"}
)
FAILED_STATUSES = frozenset(
    {"failed", "failure", "error", "cancelled", "canceled", "rejected"}
)


def _extract_data(raw: dict) -> dict:
    payload = raw if isinstance(raw, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(data.get("data"), dict):
        data = data["data"]
    return data if isinstance(data, dict) else {}


def normalize_betmomo_status(status: str) -> str:
    """Mappe les variantes BeWallet vers pending | success | failed."""
    normalized = str(status or "").strip().lower()
    if normalized in INITIATED_STATUSES:
        return "pending"
    if normalized in SUCCESS_STATUSES:
        return "success"
    if normalized in FAILED_STATUSES:
        return "failed"
    return normalized


def parse_betmomo_write_response(raw: dict) -> Dict[str, Any]:
    """Normalise topup/payout pour compatibilité clients (format MobCash-like)."""
    data = _extract_data(raw)

    ref = data.get("reference") or data.get("transaction_id")
    status = normalize_betmomo_status(data.get("status", ""))

    failed = status == "failed"
    success = status == "success"
    pending = not failed and not success

    return {
        "Success": success,
        "Pending": pending,
        "Failed": failed,
        "OperationId": ref,
        "Summa": data.get("amount"),
        "Message": status or ("pending" if pending else "betmomo"),
        "betmomo_status": status or ("pending" if pending else ""),
        "raw": raw,
    }


def parse_betmomo_status_response(raw: dict) -> Dict[str, Any]:
    """Normalise une réponse de endpoint status."""
    data = _extract_data(raw)
    raw_status = (
        data.get("status")
        or data.get("state")
        or data.get("transaction_status")
        or data.get("payment_status")
        or ""
    )
    status = normalize_betmomo_status(raw_status)
    return {
        "status": status,
        "amount": data.get("amount"),
        "reference": data.get("reference") or data.get("transaction_id"),
        "transaction_id": data.get("transaction_id"),
        "data": data,
        "raw": raw,
    }


def extract_betmomo_status_refs(
    operation_ref: str | None,
    mobcash_response: str | None = None,
) -> list[str]:
    """
    BeWallet peut exposer le statut via reference (BWTSP...) OU transaction_id (WUTO...).
    On tente les deux.
    """
    import re

    refs: list[str] = []
    for value in (operation_ref,):
        if value and str(value).strip() and str(value).strip() not in refs:
            refs.append(str(value).strip())

    raw = str(mobcash_response or "")
    for pattern in (
        r"['\"]transaction_id['\"]\s*:\s*['\"]([^'\"]+)['\"]",
        r"['\"]reference['\"]\s*:\s*['\"]([^'\"]+)['\"]",
    ):
        for match in re.finditer(pattern, raw):
            candidate = match.group(1).strip()
            if candidate and candidate not in refs:
                refs.append(candidate)
    return refs


def build_mobcash_response_payload(parsed: dict, raw: dict) -> dict:
    """Structure attendue par les clients B2B."""
    return {
        "provider": "betmomo",
        "raw_response": {
            "Success": parsed.get("Success"),
            "Pending": parsed.get("Pending"),
            "Failed": parsed.get("Failed"),
            "OperationId": parsed.get("OperationId"),
            "Summa": parsed.get("Summa"),
            "Message": parsed.get("Message"),
        },
        "betmomo_raw": raw,
    }


class BetMomoService:
    def __init__(
        self,
        token: str,
        *,
        email: str | None = None,
        password: str | None = None,
        external_base_url: str | None = None,
        dealer_base_url: str | None = None,
        timeout: int = 30,
    ):
        self._client = BetmomoClient(
            token=token,
            email=email,
            password=password,
            external_base_url=external_base_url,
            dealer_base_url=dealer_base_url,
            timeout=timeout,
        )

    @property
    def external_base_url(self) -> str:
        return self._client.external_base_url

    def topup_request_url(self) -> str:
        return f"{self.external_base_url}/dealer/external/topup"

    def deposit(self, player_id: str, amount: float) -> tuple[dict, dict]:
        raw = self._client.topup(player_id=str(player_id), amount=float(amount))
        parsed = parse_betmomo_write_response(raw)
        return parsed, build_mobcash_response_payload(parsed, raw)

    def withdrawal(self, player_id: str, pin: str) -> tuple[dict, dict]:
        raw = self._client.payout(player_id=str(player_id), pin=str(pin))
        parsed = parse_betmomo_write_response(raw)
        return parsed, build_mobcash_response_payload(parsed, raw)

    def get_transaction_details(
        self,
        operation_ref: str,
        transaction_type: str,
        *,
        mobcash_response: str | None = None,
    ) -> Optional[dict]:
        """Récupère les détails via l'endpoint status (essaie reference + transaction_id)."""
        refs = extract_betmomo_status_refs(operation_ref, mobcash_response)
        if not refs:
            return None

        last_error = None
        for ref in refs:
            try:
                if transaction_type == "WITHDRAWAL":
                    raw = self._client.payout_status(ref)
                else:
                    raw = self._client.topup_status(ref)
                parsed = parse_betmomo_status_response(raw)
                logger.info(
                    "[BETMOMO] [STATUS] type=%s ref=%s status=%s raw_keys=%s",
                    transaction_type,
                    ref,
                    parsed.get("status"),
                    list((parsed.get("data") or {}).keys())[:12],
                )
                # Même pending : on renvoie pour que l'appelant loggue / attende
                if parsed.get("status") or parsed.get("data"):
                    parsed["queried_ref"] = ref
                    return parsed
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[BETMOMO] [STATUS] échec ref=%s type=%s: %s",
                    ref,
                    transaction_type,
                    exc,
                )

        if last_error:
            logger.warning(
                "Impossible de récupérer le statut BetMomo après %s refs: %s",
                len(refs),
                last_error,
                extra={
                    "operation_ref": operation_ref,
                    "transaction_type": transaction_type,
                    "refs": refs,
                },
            )
        return None

    def get_operation_status(
        self,
        operation_ref: str,
        transaction_type: str = "DEPOSIT",
    ) -> Optional[str]:
        details = self.get_transaction_details(operation_ref, transaction_type)
        if details:
            return details.get("status") or None
        return None

    def get_balance(self) -> Optional[float]:
        """Solde via GET /dealer/stats (ancienne API + login email/password)."""
        try:
            data = self._client.stats().get("data", {})
            return float(data.get("current_main_balance", 0))
        except Exception as exc:
            logger.warning("Impossible de récupérer le solde BetMomo: %s", exc)
            return None

    @staticmethod
    def withdrawal_amount_from_details(
        details: Optional[dict],
        parsed: dict,
    ) -> Decimal:
        if details and details.get("amount") is not None:
            return Decimal(str(details.get("amount")))
        summa = parsed.get("Summa")
        if summa is not None:
            return Decimal(str(summa))
        return Decimal("0")
