"""
Test direct d'un dépôt BetMomo (External API topup).

    python manage.py test_betmomo_deposit --token "dat_..." --player-id 108464223 --amount 100
"""

from __future__ import annotations

import json
from typing import Any

from integrations.betmomo.service import BetMomoService


def test_betmomo_deposit(
    token: str,
    player_id: str = "108464223",
    amount: float = 100,
    *,
    external_base_url: str | None = None,
) -> dict[str, Any]:
    if not token or not token.strip():
        raise ValueError("Token BetMomo requis (dat_...)")

    service = BetMomoService(
        token=token.strip(),
        external_base_url=external_base_url,
        dealer_base_url=external_base_url,
    )
    request_url = service.topup_request_url()
    parsed, payload = service.deposit(player_id=str(player_id), amount=float(amount))

    return {
        "request_url": request_url,
        "request_method": "POST",
        "player_id": str(player_id),
        "amount": float(amount),
        "success": parsed.get("Success"),
        "pending": parsed.get("Pending"),
        "failed": parsed.get("Failed"),
        "operation_id": parsed.get("OperationId"),
        "status": parsed.get("betmomo_status"),
        "parsed": parsed,
        "client_payload": payload,
        "raw": parsed.get("raw"),
    }


def format_test_result(result: dict[str, Any]) -> str:
    return json.dumps(
        {
            "player_id": result["player_id"],
            "amount": result["amount"],
            "success": result["success"],
            "pending": result["pending"],
            "failed": result["failed"],
            "operation_id": result["operation_id"],
            "status": result["status"],
            "raw": result["raw"],
        },
        indent=2,
        ensure_ascii=False,
    )
