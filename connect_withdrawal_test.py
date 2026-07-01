"""
Test standalone de connect_withdrawal (Connect Pro payout).
Aucune transaction n'est créée en base — appel API Connect Pro uniquement.

Usage: python3 manage.py connect_withdrawal_test <network> <phone> <amount>
"""

import os

import requests

from payment import CONNECT_PRO_BASE_URL, connect_pro_token, get_network_id


def _normalize_network_code(network_name: str) -> str:
    network_name = network_name.strip()
    if "-" in network_name:
        return network_name.upper()
    return f"{network_name.upper()}-BJ"


def connect_withdrawal_test(network_name: str, phone_number: str, amount: int):
    """
    Appelle l'API Connect Pro pour un retrait test (même payload que connect_withdrawal).
    """
    token = connect_pro_token()
    if not token:
        print("ERREUR: impossible de récupérer le token Connect Pro")
        return None

    network_code = _normalize_network_code(network_name)
    payout_amount = int(amount)
    recipient_phone = phone_number[3:] if len(phone_number) > 10 else phone_number

    network_id = get_network_id(name=network_code)
    if not network_id:
        print(f"ERREUR: réseau '{network_code}' introuvable sur Connect Pro")
        return None

    callback_base = os.getenv("BASE_URL", "https://example.com")
    url = CONNECT_PRO_BASE_URL + "/api/payments/user/transactions/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = {
        "type": "deposit",
        "amount": f"{payout_amount}",
        "recipient_phone": recipient_phone,
        "recipient_name": "Test Mobcash",
        "objet": "Turnaincash deposit",
        "network": network_id,
        "callback_url": f"{callback_base}/connect-pro-webhook",
    }

    print(f"URL: {url}")
    print(f"Réseau Connect: {network_code} (uid={network_id})")
    print(f"Payload: {data}")

    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        print(f"Status HTTP: {response.status_code}")
        try:
            body = response.json()
        except ValueError:
            body = response.text
        print(f"Réponse: {body}")

        if response.ok and isinstance(body, dict):
            uid = (body.get("data") or {}).get("uid")
            print(f"UID Connect Pro: {uid}")
        return body
    except requests.exceptions.Timeout as exc:
        print(f"ERREUR: timeout {exc}")
    except requests.exceptions.RequestException as exc:
        print(f"ERREUR: requête {exc}")
    except Exception as exc:
        print(f"ERREUR: {exc}")

    return None
