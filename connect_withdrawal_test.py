"""
Test de connect_withdrawal — même logique que payment.connect_withdrawal.
Aucune Transaction n'est créée ni sauvegardée en base.

Usage: python3 manage.py connect_withdrawal_test <network> <phone> <amount>
Exemple: python3 manage.py connect_withdrawal_test moov 0151206286 500
"""

import requests

from mobcash_inte.models import Network
from mobcash_inte_backend.settings import BASE_URL
from payment import (
    CONNECT_PRO_BASE_URL,
    connect_pro_token,
    get_network_id,
    total_amount_to_send_wave,
)


def connect_withdrawal_test(network_name: str, phone_number: str, amount: int):
    """
    Reprend exactement connect_withdrawal (payment.py) sans persister de Transaction.
    Le champ network envoyé à Connect est l'uid (UUID), pas le pays.
    Le code MOOV-BJ sert uniquement à retrouver cet uid via get_network_id().
    """
    network = Network.objects.filter(name__iexact=network_name.strip()).first()
    if not network:
        print(f"ERREUR: réseau '{network_name}' introuvable en base (table Network)")
        return None

    token = connect_pro_token()
    if not token:
        print("ERREUR: impossible de récupérer le token Connect Pro")
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = CONNECT_PRO_BASE_URL + "/api/payments/user/transactions/"

    payout_amount = int(amount)
    if network.name.lower() == "wave" and not network.customer_pay_fee:
        payout_amount = total_amount_to_send_wave(payout_amount)
        print(f"Montant Wave ajusté (frais inclus): {payout_amount}")

    network_code = f"{network.name.upper()}-{network.country_code.upper()}"
    network_uid = get_network_id(name=network_code)
    if not network_uid:
        print(f"ERREUR: réseau Connect '{network_code}' introuvable")
        return None

    data = {
        "type": "deposit",
        "amount": f"{payout_amount}",
        "recipient_phone": (
            phone_number[3:] if len(phone_number) > 10 else phone_number
        ),
        "recipient_name": "Test Mobcash",
        "objet": "Turnaincash deposit",
        "network": network_uid,
        "callback_url": f"{BASE_URL}/connect-pro-webhook",
    }

    print(f"[CONNECT_WITHDRAWAL_TEST] POST {url}")
    print(f"[CONNECT_WITHDRAWAL_TEST] network_code={network_code} | network_uid={network_uid}")
    print(f"[CONNECT_WITHDRAWAL_TEST] body={data}")

    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        print(f"[CONNECT_WITHDRAWAL_TEST] status={response.status_code} | body={response.text[:500]}")
        try:
            body = response.json()
        except ValueError:
            body = response.text
        if response.ok and isinstance(body, dict):
            uid = (body.get("data") or {}).get("uid")
            print(f"[CONNECT_WITHDRAWAL_TEST] uid={uid}")
        return body
    except Exception as exc:
        print(f"[CONNECT_WITHDRAWAL_TEST] Erreur: {exc}")
        return None
