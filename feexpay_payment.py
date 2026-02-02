from uuid import uuid4
from decimal import Decimal
from mobcash_inte.models import (
    Caisse, Setting, Transaction, Reward
)
from accounts.models import User
import os
from dotenv import load_dotenv
from django.db.models import Q
from mobcash_inte.serializers import TransactionDetailsSerializer
from mobcash_inte.helpers import send_notification, send_telegram_message
from django.utils import timezone
from django.utils.timezone import now
from django.db import transaction as db_transaction
load_dotenv()
import requests
import constant
import random
import time
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from dateutil.relativedelta import relativedelta
from celery import shared_task
import logging

connect_pro_logger = logging.getLogger("mobcash_inte_backend.transactions")


def send_event(channel_name, event_name, data):
    """Envoie un événement via WebSocket"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        channel_name,
        {
            "type": event_name,
            "data": data,
        },
    )


def feexpay_payout(transaction: Transaction):
    """
    Fonction pour créer un retrait Feexpay
    Suit le même pattern que feexpay_deposit
    """
    # Vérifier les variables d'environnement
    shop = os.getenv("FEEXPAY_CUSTOMER_ID")
    if not shop:
        connect_pro_logger.error("FEEXPAY_CUSTOMER_ID non configuré")
        return
    
    api_key = os.getenv('FEEXPAY_API_KEY')
    if not api_key:
        connect_pro_logger.error("FEEXPAY_API_KEY non configuré")
        return
    
    # URL pour les retraits
    url = "https://api.feexpay.me/api/payouts/public/transfer/global"
    
    # Préparer les données
    amount = int(float(transaction.amount)) if transaction.amount else 0
    if amount <= 0:
        connect_pro_logger.error(f"Montant invalide: {transaction.amount}")
        return
    
    # Récupérer le numéro de téléphone
    phone_number = transaction.phone_number 
    # Nettoyer le numéro (retirer le préfixe si présent, comme dans deposit_connect)
    # if len(phone_number) > 10:
    #     phone_number = phone_number[3:] if phone_number.startswith("229") else phone_number
    # elif not phone_number.startswith("229") and len(phone_number) == 10:
    #     # Ajouter le préfixe si absent (pour les retraits, Feexpay peut nécessiter le format complet)
    #     phone_number = f"229{phone_number}"
    
    # Déterminer le réseau depuis payment_mode ou network
    network_name = None
    if transaction.payment_mode:
        network_name = transaction.payment_mode.upper()
    elif transaction.network:
        network_name = transaction.network.name.upper()
    
    if not network_name:
        connect_pro_logger.error("Réseau non spécifié pour le retrait")
        return
    
    data = {
        "phoneNumber": phone_number,
        "amount": str(amount),
        "shop": shop,
        "network": network_name,
        "motif": "Retrait de caisse",
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        connect_pro_logger.info("debut de creatuion de retrait feexpay")
        response = requests.post(url=url, json=data, headers=headers, timeout=45)
        connect_pro_logger.info(f" feexpay payout response {response.json()}")
        
        response_data = response.json()
        
        # Sauvegarder la référence Feexpay dans la transaction
        feexpay_reference = response_data.get("reference") or response_data.get("data", {}).get("reference")
        if feexpay_reference:
            transaction.reference = feexpay_reference
            # Si Feexpay retourne un UID/public_id, le sauvegarder aussi
            feexpay_uid = response_data.get("uid") or response_data.get("data", {}).get("uid")
            if feexpay_uid:
                transaction.public_id = feexpay_uid
            transaction.save()

    except requests.exceptions.Timeout as e:
        connect_pro_logger.critical(f" Erreur de creation feexpay payout timeout {e}")
    except requests.exceptions.RequestException as e:
        connect_pro_logger.critical(f" Erreur de creation feexpay payout network error {e}")
    except Exception as e:
        connect_pro_logger.critical(f" Erreur de creation feexpay payout {e}")


def feexpay_deposit(transaction: Transaction):
    """
    Fonction pour créer une demande de paiement Feexpay
    Suit le même pattern que deposit_connect
    """
    # Vérifier les variables d'environnement
    shop = os.getenv("FEEXPAY_CUSTOMER_ID")
    if not shop:
        connect_pro_logger.error("FEEXPAY_CUSTOMER_ID non configuré")
        return

    api_key = os.getenv('FEEXPAY_API_KEY')
    if not api_key:
        connect_pro_logger.error("FEEXPAY_API_KEY non configuré")
        return

    # Déterminer l'URL selon le réseau
    url = None
    network_name = transaction.network.name.lower() if transaction.network else None

    if network_name == "moov":
        url = "https://api.feexpay.me/api/transactions/public/requesttopay/moov"
        connect_pro_logger.info("debut de creatuion de transaction feexpay MOOV")
    elif network_name == "mtn":
        url = "https://api.feexpay.me/api/transactions/public/requesttopay/mtn"
        connect_pro_logger.info("debut de creatuion de transaction feexpay MTN")
    else:
        url = "https://api.feexpay.me/api/transactions/public/requesttopay/celtiis_bj"
        connect_pro_logger.info("debut de creatuion de transaction feexpay Celtiis")

    if not url:
        connect_pro_logger.error(f"Réseau non supporté: {network_name}")
        return

    # Préparer les données
    amount = int(float(transaction.amount)) if transaction.amount else 0
    if amount <= 0:
        connect_pro_logger.error(f"Montant invalide: {transaction.amount}")
        return

    # Récupérer le numéro de téléphone
    phone_number = transaction.phone_number 
    # Nettoyer le numéro (retirer le préfixe si présent, comme dans deposit_connect)
    # if len(phone_number) > 10:
    #     phone_number = phone_number[3:] if phone_number.startswith("229") else phone_number

    # Récupérer les informations utilisateur
    user = transaction.user if transaction.user else transaction.telegram_user
    first_name = ""
    last_name = ""
    if user:
        if hasattr(user, 'first_name'):
            first_name = user.first_name or ""
        if hasattr(user, 'last_name'):
            last_name = user.last_name or ""
        elif hasattr(user, 'full_name'):
            # Pour TelegramUser
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

    try:
        response = requests.post(url=url, json=data, headers=headers, timeout=45)
        connect_pro_logger.info(f" feexpay response {response.json()}")

        response_data = response.json()

        # Sauvegarder la référence Feexpay dans la transaction
        feexpay_reference = response_data.get("reference") or response_data.get("data", {}).get("reference")
        if feexpay_reference:
            transaction.reference = feexpay_reference
            # Si Feexpay retourne un UID/public_id, le sauvegarder aussi
            feexpay_uid = response_data.get("uid") or response_data.get("data", {}).get("uid")
            if feexpay_uid:
                transaction.public_id = feexpay_uid
            transaction.save()

    except requests.exceptions.Timeout as e:
        connect_pro_logger.critical(f" Erreur de creation feexpay timeout {e}")
    except requests.exceptions.RequestException as e:
        connect_pro_logger.critical(f" Erreur de creation feexpay network error {e}")
    except Exception as e:
        connect_pro_logger.critical(f" Erreur de creation feexpay {e}")


def feexpay_withdrawall_process(transaction: Transaction, disbursements=False):
    """
    Traite le retrait Feexpay après création de la transaction
    Suit le même pattern que connect_pro_withd_process
    """
    connect_pro_logger.info("Demarrage dans la fonction de retrait feexpay")
    
    if transaction.type_trans == "withdrawal" and not disbursements:
        # Importer xbet_withdrawal_process depuis payment.py
        from payment import xbet_withdrawal_process
        response = xbet_withdrawal_process(transaction=transaction)
    else:
        response = True
    
    if response == True:
        feexpay_payout(transaction=transaction)


@shared_task
def feexpay_webhook(data):
    """
    Traite le webhook Feexpay
    Suit le même pattern que connect_pro_webhook
    """
    connect_pro_logger.info(
        f"feexpay webhook reçu avec le data {data} et la reference {data.get('reference') or data.get('externalId')}"
    )
    
    reference = data.get("externalId") or data.get("reference") or data.get("uid")
    transaction_status = data.get("status")

    if not reference:
        connect_pro_logger.info("Webhook Feexpay reçu sans référence")
        return

    with db_transaction.atomic():
        # Chercher par reference ou public_id (comme Connect cherche par public_id)
        transaction = (
            Transaction.objects.filter(
                Q(reference=reference) | Q(public_id=reference)
            )
            .exclude(Q(status="error") | Q(status="accept"))
            .select_for_update(nowait=True)
            .first()
        )

        if not transaction:
            connect_pro_logger.info(
                f"La transaction avec reference {reference} n'existe pas ou a ete deja traiter"
            )
            return
                
        transaction.wehook_receive_at = timezone.now()
        # Convertir data en string pour TextField (comme dans connect_pro_webhook)
        import json
        transaction.webhook_data = json.dumps(data) if isinstance(data, dict) else str(data)
        connect_pro_logger.info(f"la reference qui a ete transmi {reference}")
        
        setting = Setting.objects.first()
        
        # Adapter les statuts Feexpay aux statuts Connect
        if transaction_status == "FAILED" or transaction_status == "failed" or transaction_status == "cancelled":
            connect_pro_logger.info("Transaction is fail")
            from payment import webhook_transaction_failled
            webhook_transaction_failled(transaction=transaction)
        elif transaction_status == "SUCCESSFUL" or transaction_status == "success" or transaction_status == "confirmed":
            connect_pro_logger.info("Transaction is success")
            from payment import webhook_transaction_success
            webhook_transaction_success(transaction=transaction, setting=setting)
