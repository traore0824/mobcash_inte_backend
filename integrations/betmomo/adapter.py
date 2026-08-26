"""
Adaptateur BetMomo pour l'interface BetApp / OneWinService
(recharge_account / withdraw_from_account / create_deposit / create_withdrawal).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from integrations.betmomo.client import BetmomoAPIError, BetmomoAuthError
from integrations.betmomo.service import BetMomoService

if TYPE_CHECKING:
    from mobcash_inte.models import Transaction

logger = logging.getLogger("mobcash_inte_backend.transactions")


class BetMomoApiAdapter:
    provider = "betmomo"

    def __init__(
        self,
        token: str,
        *,
        email: str | None = None,
        password: str | None = None,
    ):
        self._service = BetMomoService(
            token=token,
            email=email or None,
            password=password or None,
        )

    def recharge_account(self, userid, amount: float) -> dict[str, Any]:
        try:
            parsed, _payload = self._service.deposit(str(userid), float(amount))
            return parsed
        except (BetmomoAPIError, BetmomoAuthError, ValueError) as exc:
            logger.error("[BETMOMO] [DEPOSIT] Erreur API: %s", exc)
            return {
                "Success": False,
                "Pending": False,
                "Failed": True,
                "Message": str(exc),
            }

    def withdraw_from_account(self, userid, code) -> dict[str, Any]:
        try:
            parsed, _payload = self._service.withdrawal(str(userid), str(code))
            return parsed
        except (BetmomoAPIError, BetmomoAuthError, ValueError) as exc:
            logger.error("[BETMOMO] [WITHDRAWAL] Erreur API: %s", exc)
            return {
                "Success": False,
                "Pending": False,
                "Failed": True,
                "Message": str(exc),
            }

    def _persist(self, transaction: "Transaction", parsed: dict, payload: dict) -> dict:
        fields = []
        if hasattr(transaction, "mobcash_response"):
            transaction.mobcash_response = str(payload)
            fields.append("mobcash_response")
        elif hasattr(transaction, "bet_response"):
            transaction.bet_response = str(payload)
            fields.append("bet_response")

        ref = parsed.get("OperationId")
        if ref and hasattr(transaction, "betmomo_operation_ref"):
            transaction.betmomo_operation_ref = ref
            fields.append("betmomo_operation_ref")

        if fields:
            transaction.save(update_fields=fields)
        return parsed

    def create_deposit(self, transaction: "Transaction", amount=None) -> dict[str, Any]:
        amount = float(amount if amount is not None else transaction.amount)
        try:
            parsed, payload = self._service.deposit(
                str(transaction.user_app_id),
                amount,
            )
            logger.info(
                "[BETMOMO] [DEPOSIT] player_id=%s amount=%s status=%s ref=%s",
                transaction.user_app_id,
                amount,
                parsed.get("betmomo_status"),
                parsed.get("OperationId"),
            )
            return self._persist(transaction, parsed, payload)
        except (BetmomoAPIError, BetmomoAuthError, ValueError) as exc:
            logger.error("[BETMOMO] [DEPOSIT] Erreur API: %s", exc)
            return {
                "Success": False,
                "Pending": False,
                "Failed": True,
                "Message": str(exc),
            }

    def create_withdrawal(self, transaction: "Transaction") -> dict[str, Any]:
        try:
            parsed, payload = self._service.withdrawal(
                str(transaction.user_app_id),
                str(transaction.withdriwal_code),
            )
            logger.info(
                "[BETMOMO] [WITHDRAWAL] player_id=%s status=%s ref=%s",
                transaction.user_app_id,
                parsed.get("betmomo_status"),
                parsed.get("OperationId"),
            )
            return self._persist(transaction, parsed, payload)
        except (BetmomoAPIError, BetmomoAuthError, ValueError) as exc:
            logger.error("[BETMOMO] [WITHDRAWAL] Erreur API: %s", exc)
            return {
                "Success": False,
                "Pending": False,
                "Failed": True,
                "Message": str(exc),
            }
