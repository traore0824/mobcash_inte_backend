"""
Script manuel de test BetMomo — N'EST PAS utilisé par Django/Celery.

Lancer uniquement à la main :
    python3 betmomo_test.py

Tous les appels topup/payout sont en dry_run (aucun argent réel).
"""

import json

from betmomo_constants import (
    BETMOMO_DRY_RUN,
    BETMOMO_PLAYER_ID,
    BETMOMO_TEST_AMOUNT,
    BETMOMO_TEST_PIN,
    BETMOMO_TOKEN,
)
from betmomo_external_service import BetMomoExternalService


def test_betmomo(
    token: str = BETMOMO_TOKEN,
    player_id: str = BETMOMO_PLAYER_ID,
    amount: int = BETMOMO_TEST_AMOUNT,
    pin: str = BETMOMO_TEST_PIN,
    dry_run: bool = True,
) -> None:
    if not token:
        print("BETMOMO_TOKEN manquant dans .env")
        return

    service = BetMomoExternalService(token=token)

    print(f"\nSolde actuel : {service.get_balance()} XOF")

    print(f"\nDépôt (dry_run={dry_run}) :")
    print(json.dumps(
        service.deposit(player_id=player_id, amount=amount, dry_run=dry_run),
        indent=2,
        ensure_ascii=False,
    ))

    print(f"\nRetrait (dry_run={dry_run}) :")
    print(json.dumps(
        service.withdrawal(player_id=player_id, pin=pin or "******", dry_run=dry_run),
        indent=2,
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    test_betmomo(dry_run=BETMOMO_DRY_RUN)
