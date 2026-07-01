"""
Script de test standalone pour feexpay_deposit (réseau MOOV).
Usage: python test_feexpay_deposit.py
"""

import requests
from types import SimpleNamespace

# ── Constantes Feexpay ────────────────────────────────────────────────────────
FEEXPAY_CUSTOMER_ID = "647cc45e2a33e24f6ab4df42"
FEEXPAY_API_KEY = "fp_VyNttoaEdgMtGF9yiU4ALrdMDqJ2SAfM1BnsJQaUUFVCgCpMmYD70Btfelcvzpvq"

# ── Données de test ───────────────────────────────────────────────────────────
PHONE_NUMBER = "2290155187395"
NETWORK_NAME = "moov"
AMOUNT = 100
TRANSACTION_REFERENCE = "TEST-FEEXPAY-001"


def feexpay_deposit(transaction):
    """
    Fonction pour créer une demande de paiement Feexpay
    (copie adaptée de payment.py pour test standalone)
    """
    shop = FEEXPAY_CUSTOMER_ID
    if not shop:
        print("ERREUR: FEEXPAY_CUSTOMER_ID non configuré")
        return

    api_key = FEEXPAY_API_KEY
    if not api_key:
        print("ERREUR: FEEXPAY_API_KEY non configuré")
        return

    url = None
    network_name = transaction.network.name.lower() if transaction.network else None

    if network_name == "moov":
        url = "https://api-v2.feexpay.me/api/transactions/public/requesttopay/moov"
        print("debut de creatuion de transaction feexpay MOOV")
    elif network_name == "mtn":
        url = "https://api-v2.feexpay.me/api/transactions/public/requesttopay/mtn"
        print("debut de creatuion de transaction feexpay MTN")
    else:
        url = "https://api-v2.feexpay.me/api/transactions/public/requesttopay/celtiis_bj"
        print("debut de creatuion de transaction feexpay Celtiis")

    if not url:
        print(f"ERREUR: Réseau non supporté: {network_name}")
        return

    amount = int(float(transaction.amount)) if transaction.amount else 0
    if amount <= 0:
        print(f"ERREUR: Montant invalide: {transaction.amount}")
        return

    phone_number = transaction.phone_number

    user = transaction.user if transaction.user else transaction.telegram_user
    first_name = ""
    last_name = ""
    if user:
        if hasattr(user, "first_name"):
            first_name = user.first_name or ""
        if hasattr(user, "last_name"):
            last_name = user.last_name or ""
        elif hasattr(user, "full_name"):
            full_name_parts = user.full_name().split() if user.full_name() else []
            first_name = full_name_parts[0] if full_name_parts else ""
            last_name = " ".join(full_name_parts[1:]) if len(full_name_parts) > 1 else ""

    data = {
        "phoneNumber": phone_number,
        "amount": amount,
        "shop": shop,
        "description": f"Demande de paiement - Transaction {transaction.reference}",
        "firstName": first_name,
        "lastName": last_name,
        "email": (
            user.email
            if user and hasattr(user, "email") and user.email
            else "client@mobcash.com"
        ),
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    print(f"URL: {url}")
    print(f"Payload: {data}")

    try:
        response = requests.post(url=url, json=data, headers=headers, timeout=45)
        print(f"Status HTTP: {response.status_code}")
        print(f"feexpay response: {response.json()} data === {data}")

        response_data = response.json()

        feexpay_reference = response_data.get("reference") or response_data.get("data", {}).get("reference")
        if feexpay_reference:
            transaction.public_id = feexpay_reference
            feexpay_uid = response_data.get("uid") or response_data.get("data", {}).get("uid")
            if feexpay_uid:
                transaction.public_id = feexpay_uid
            print(f"Référence Feexpay sauvegardée: {transaction.public_id}")
        else:
            print("Aucune référence Feexpay retournée dans la réponse")

        return response_data

    except requests.exceptions.Timeout as e:
        print(f"ERREUR: creation feexpay timeout {e}")
    except requests.exceptions.RequestException as e:
        print(f"ERREUR: creation feexpay network error {e}")
    except Exception as e:
        print(f"ERREUR: creation feexpay {e}")

    return None


def build_mock_transaction():
    """Construit un objet transaction minimal pour le test."""
    network = SimpleNamespace(name=NETWORK_NAME)
    user = SimpleNamespace(
        first_name="Test",
        last_name="Mobcash",
        email="test@mobcash.com",
    )
    return SimpleNamespace(
        network=network,
        amount=AMOUNT,
        phone_number=PHONE_NUMBER,
        reference=TRANSACTION_REFERENCE,
        user=user,
        telegram_user=None,
        public_id=None,
    )


if __name__ == "__main__":
    print("=== Test feexpay_deposit (MOOV) ===")
    transaction = build_mock_transaction()
    result = feexpay_deposit(transaction)
    print(f"=== Fin du test | public_id={transaction.public_id} | result={result} ===")
