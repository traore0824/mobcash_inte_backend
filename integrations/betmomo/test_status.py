"""
Vérification du statut d'une opération BetMomo (External API).

    python manage.py test_betmomo_status --token "dat_..." --reference BWTSP... --type topup
"""

from __future__ import annotations

import json
from typing import Any, Literal

from integrations.betmomo.service import BetMomoService

OpType = Literal["topup", "payout", "deposit", "withdrawal"]


def test_betmomo_status(
    token: str,
    reference: str,
    op_type: OpType = "topup",
) -> dict[str, Any]:
    if not token or not token.strip():
        raise ValueError("Token BetMomo requis (dat_...)")
    if not reference or not reference.strip():
        raise ValueError("Référence ou transaction_id requis")

    normalized = op_type.lower()
    if normalized in ("topup", "deposit"):
        transaction_type = "DEPOSIT"
    elif normalized in ("payout", "withdrawal"):
        transaction_type = "WITHDRAWAL"
    else:
        raise ValueError("op_type doit être topup, payout, deposit ou withdrawal")

    service = BetMomoService(token=token.strip())
    details = service.get_transaction_details(reference.strip(), transaction_type)

    if not details:
        return {
            "reference": reference.strip(),
            "op_type": normalized,
            "found": False,
            "status": None,
            "details": None,
        }

    return {
        "reference": reference.strip(),
        "op_type": normalized,
        "found": True,
        "status": details.get("status"),
        "amount": details.get("amount"),
        "details": details.get("data"),
        "raw": details.get("raw"),
    }


def format_status_result(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)
