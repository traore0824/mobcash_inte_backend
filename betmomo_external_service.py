# external_integrations/services/betmomo_external_service.py

"""
Service BetMomo — endpoints documentés :

  GET  /dealer/stats
  GET  /dealer/operations          (polling status)
  POST /dealer/transactions/topup
  POST /dealer/transactions/payout
"""

import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional

from betmomo_client import BetmomoClient

if TYPE_CHECKING:
    from mobcash_inte.models import Transaction

logger = logging.getLogger("mobcash_inte_backend.transactions")


def parse_betmomo_write_response(raw: dict) -> Dict[str, Any]:
    """
    Normalise la réponse topup/payout pour la logique BetPay (compat MobCash).
    Champs API observés : data.reference, data.status (pending|success|failed).
    """
    payload = raw if isinstance(raw, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(data.get("data"), dict):
        data = data["data"]

    ref = data.get("reference")
    status = str(data.get("status", "")).lower()
    amount = data.get("amount")

    pending = status == "pending"
    success = status == "success"
    failed = status == "failed"

    return {
        "Success": success,
        "Pending": pending,
        "Failed": failed,
        "OperationId": ref,
        "Summa": amount,
        "Message": status or "betmomo",
        "betmomo_status": status,
        "raw": payload,
    }


class BetMomoExternalService:
    def __init__(self, token: Optional[str] = None, timeout: int = 30):
        token = token or os.getenv("BETMOMO_TOKEN", "")
        if not token:
            raise ValueError("BETMOMO_TOKEN manquant")
        self._client = BetmomoClient(token=token, timeout=timeout)

    def get_balance(self) -> float:
        data = self._client.stats().get("data", {})
        return data["current_main_balance"]

    def deposit(self, player_id: str, amount: float, dry_run: bool = False) -> dict:
        logger.info("[BETMOMO] deposit player_id=%s amount=%s", player_id, amount)
        return self._client.topup(player_id=str(player_id), amount=amount, dry_run=dry_run)

    def withdrawal(self, player_id: str, pin: str, dry_run: bool = False) -> dict:
        logger.info("[BETMOMO] withdrawal player_id=%s", player_id)
        return self._client.payout(player_id=str(player_id), pin=str(pin), dry_run=dry_run)

    def get_operation_by_ref(self, operation_ref: str) -> Optional[dict]:
        """GET /dealer/operations — recherche par ref (doc : polling)."""
        page = 1
        while page <= 10:
            result = self._client.operations(page=page, per_page=50)
            for operation in result.get("data", []):
                if operation.get("ref") == operation_ref:
                    return operation
                top_up = operation.get("top_up") or {}
                if top_up.get("reference") == operation_ref:
                    return operation
                pay_out = operation.get("pay_out") or {}
                if pay_out.get("transaction_id") == operation_ref:
                    return operation
                parent = operation.get("parent_operation") or {}
                if parent.get("ref") == operation_ref:
                    return parent

            meta = result.get("meta") or {}
            if page >= meta.get("last_page", page):
                break
            page += 1
        return None

    def get_operation_status(self, operation_ref: str) -> Optional[str]:
        operation = self.get_operation_by_ref(operation_ref)
        if operation:
            return str(operation.get("status", "")).lower() or None
        return None

    def _save_transaction_response(
        self,
        transaction: "Transaction",
        raw: dict,
        parsed: dict,
    ) -> None:
        ref = parsed.get("OperationId")
        transaction.mobcash_response = str(raw)
        update_fields = ["mobcash_response"]
        if ref:
            transaction.betmomo_operation_ref = ref
            update_fields.append("betmomo_operation_ref")
        transaction.save(update_fields=update_fields)

    def create_deposit(self, transaction: "Transaction") -> Dict[str, Any]:
        raw = self.deposit(
            player_id=str(transaction.user_app_id),
            amount=float(transaction.amount),
            dry_run=False,
        )
        parsed = parse_betmomo_write_response(raw)
        self._save_transaction_response(transaction, raw, parsed)
        return {**parsed, **raw}

    def create_withdrawal(self, transaction: "Transaction") -> Dict[str, Any]:
        raw = self.withdrawal(
            player_id=str(transaction.user_app_id),
            pin=str(transaction.withdriwal_code),
            dry_run=False,
        )
        parsed = parse_betmomo_write_response(raw)
        self._save_transaction_response(transaction, raw, parsed)
        return {**parsed, **raw}
