import asyncio
import requests
import os
from accounts.models import User
import constant
from dotenv import load_dotenv

from mobcash_external_service import MobCashExternalService
load_dotenv()
from mobcash_balance import get_balance
from mobcash_inte.helpers import (
    init_mobcash,
    send_admin_notification,
    send_notification,
    send_telegram_message,
)
from mobcash_inte.models import Bonus, Caisse, Reward, Setting, Transaction
from django.utils import timezone
from dateutil.relativedelta import relativedelta
import logging
from django.db import OperationalError, transaction as db_transaction
from django.db.models import Q
from mobcash_inte.serializers import TransactionDetailsSerializer
from mobcash_inte_backend.settings import BASE_URL
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from celery import shared_task
import json

connect_pro_logger = logging.getLogger("mobcash_inte_backend.transactions")
payment_logger = logging.getLogger("Payment transaction process")
logger = logging.getLogger(__name__)


def track_status_change(transaction: Transaction, new_status: str, source: str = "system", admin_id: int = None):
    """
    Fonction utilitaire pour tracker les changements de statut d'une transaction.
    
    Args:
        transaction: Instance de Transaction
        new_status: Nouveau statut
        source: "system" ou "admin"
        admin_id: ID de l'admin si source="admin"
    """
    if not hasattr(transaction, 'all_status') or transaction.all_status is None:
        transaction.all_status = []
    
    status_entry = {
        "status": new_status,
        "timestamp": timezone.now().isoformat(),
        "source": source
    }
    
    if source == "admin" and admin_id:
        status_entry["admin_id"] = admin_id
    
    transaction.all_status.append(status_entry)
    transaction.save(update_fields=['all_status'])


def connect_base_url():
    setting = Setting.objects.first()
    return setting.connect_pro_base_url or "https://connect.turaincash.com"

CONNECT_PRO_BASE_URL = os.getenv("CONNECT_PRO_BASE_URL")


def connect_pro_token():
    setting = Setting.objects.first()
    token = None
    if (
        setting.expired_connect_pro_token
        and setting.expired_connect_pro_token > timezone.now()
    ):
        connect_pro_logger.info(
            f"Le token existe deja {setting.connect_pro_token} et expire le {setting.expired_connect_pro_token}"
        )
        token = setting.connect_pro_token
        return token
    url = CONNECT_PRO_BASE_URL + "/api/auth/login/"
    data = {
        "identifier": setting.connect_pro_email,
        "password": setting.connect_pro_password,
    }

    headers = {
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)

        setting.expired_connect_pro_token = timezone.now() + relativedelta(hours=23)
        setting.connect_pro_token = response.json().get("access")
        setting.connect_pro_refresh = response.json().get("refresh")
        connect_pro_logger.info(f"Un nouveau token generer {response.json()}")
        setting.save()
        return response.json().get("access")
    except Exception as e:
        connect_pro_logger.critical(f"Une erreur de generation de token {e}")
        return None


def get_network_id(name):
    token = connect_pro_token()
    if not token:
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = CONNECT_PRO_BASE_URL + "/api/payments/networks/"
    try:
        response = requests.get(url, headers=headers, timeout=30)
        connect_pro_logger.debug(f"Liste des réseaux ConnectPro : {response.json()}")
        results = response.json().get("results", [])

        # Comparaison insensible à la casse
        for data in results:
            if data.get("code", "").lower() == name.lower():
                return data.get("uid")

    except Exception as e:
        connect_pro_logger.critical(f"Erreur de récupération de réseau : {e}")

    return None


import math
def fee_wave(montant: int) -> int:
    """Calcule les frais Wave : 1% du montant envoyé, arrondi au multiple de 5 supérieur."""
    return math.ceil(montant * 0.01 / 5) * 5


def total_amount_to_send_wave(montant_souhaite: int) -> int:
    """
    Calcule le montant total que l'expéditeur doit payer pour que
    le destinataire reçoive au moins `montant_souhaite` (tolérance +1 F max).

    Retourne uniquement : total_expediteur
    """
    montant_envoye = montant_souhaite
    while True:
        frais = fee_wave(montant_envoye)
        recu = montant_envoye  # le destinataire reçoit le montant envoyé
        total_expediteur = montant_envoye + frais

        if recu >= montant_souhaite:
            return total_expediteur  # juste le total payé par l'expéditeur

        montant_envoye += 1  # on teste le prochain montant


def connect_withdrawal(transaction: Transaction):
    token = connect_pro_token()
    if not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = CONNECT_PRO_BASE_URL + "/api/payments/user/transactions/"

    amount = transaction.amount
    if transaction.network.name.lower() == "wave" and not transaction.network.customer_pay_fee:
        transaction.net_payable_amout = total_amount_to_send_wave(amount)
        transaction.save()
        amount = transaction.net_payable_amout
    transaction.save()

    data = {
        "type": "deposit",
        "amount": f"{amount}",
        "recipient_phone": (
            transaction.phone_number[3:]
            if len(transaction.phone_number) > 10
            else transaction.phone_number
        ),
        "recipient_name": transaction.user.full_name(),
        "objet": "Turnaincash deposit",
        "network": get_network_id(
            name=f"{transaction.network.name.upper()}-{transaction.network.country_code.upper()}"
        ),
        "callback_url": f"{BASE_URL}/connect-pro-webhook",
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        connect_pro_logger.info(f"response connect pro with {response.json()}")
        transaction.public_id = response.json().get("data").get("uid")
        transaction.save()
    except Exception as e:
        connect_pro_logger.info(f"response connect pro with errer {e}")


def connect_pro_withd_process(transaction: Transaction, disbursements=False):
    logger.info("Demarrage dans la fonction de retrait")
    if transaction.type_trans == "withdrawal" and not disbursements:
        response = xbet_withdrawal_process(transaction=transaction)
    else:
        response = True
    if response == True:
        if (
            os.getenv("CAN_WITHDRAWAL")
            and os.getenv("CAN_WITHDRAWAL").lower() == "false"
        ) or transaction.network.manual_processing:
            content = (
            "💸 **Nouvelle demande de retrait** 💸\n\n"
            f"**Référence :** {transaction.reference}\n"
            f"**Nom de la plateforme :** {transaction.app.name if transaction.app else 'N/A'}\n"
            f"**User ID :** {transaction.user_app_id}\n"
            f"**Email :** {transaction.user.email if transaction.user and hasattr(transaction.user, 'email') else 'N/A'}\n"
            f"**Téléphone :** {transaction.phone_number or 'N/A'}"
            f"**Montant :** {transaction.amount } Franc"
            f"**Reseau :** {transaction.network.name }"
            f"**Date de confirmation :** {transaction.validated_at }"
        )
            send_telegram_message(content=content, chat_id=os.getenv("USER_CHAT_ID"))
        else:
            connect_withdrawal(transaction=transaction)


from decimal import Decimal, ROUND_HALF_UP


def round_up_half(n):
    return int(Decimal(n).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def deposit_connect(transaction: Transaction):
    token = connect_pro_token()
    setting = Setting.objects.first()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = None
    if transaction.network.name == "wave":
        connect_pro_logger.info("debut de creatuion de transaction wave")
        url = CONNECT_PRO_BASE_URL + "/api/payments/wave-business-transactions/"
        data = {
            "amount": transaction.amount,
            "recipient_phone": (
                transaction.phone_number[3:]
                if len(transaction.phone_number) > 10
                else transaction.phone_number
            ),
            "callback_url": f"{BASE_URL}/connect-pro-webhook",
        }
        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            connect_pro_logger.info(f" connect pro  response {response.json()}")
            transaction.public_id = response.json().get("data").get("uid")
            transaction.transaction_link = (
                setting.wave_default_link + f"?amount={transaction.amount}"
            )
            transaction.save()
        except Exception as e:
            connect_pro_logger.critical(
                f" Erreur de creation wave pour connect pro {e}"
            )
    elif transaction.network.payment_by_link:
        connect_pro_logger.info(
            f"debut de creatuion de transaction {transaction.network.name}"
        )
        url = CONNECT_PRO_BASE_URL + "/api/payments/momo-pay-transactions/"
        data = {
            "amount": transaction.amount,
            "recipient_phone": (
                transaction.phone_number[3:]
                if len(transaction.phone_number) > 10
                else transaction.phone_number
            ),
            "callback_url": f"{BASE_URL}/connect-pro-webhook",
            "payment_type": f"{transaction.network.name}-{transaction.network.country_code}",
        }
        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            connect_pro_logger.info(f" connect pro  response {response.json()}")
            transaction.public_id = response.json().get("data").get("uid")
            if transaction.network.name == "orange":
                transaction.transaction_link = (
                    setting.orange_default_link
                    + f"&amount={transaction.amount}"
                )
            else:
                transaction.transaction_link = (
                    setting.mtn_default_link
                    + f"?amount={transaction.amount}&reference={transaction.reference}"
                )
            transaction.save()
        except Exception as e:
            connect_pro_logger.critical(
                f" Erreur de creation de transaction {transaction.network.name} pour connect pro {e}"
            )

    else:
        connect_pro_logger.info(" Test de transaction par USSD")
        url = CONNECT_PRO_BASE_URL + "/api/payments/user/transactions/"
        amount = 0
        # Vérifier si MTN_NOT_FEE est activé pour MTN en CI
        mtn_not_fee = os.getenv("MTN_NOT_FEE", "False").lower() == "true"
        is_mtn_ci = transaction.network.name == "mtn" and transaction.network.country_code.lower() == "ci"
        
        # Vérifier si MOOV_NOT_FEE est activé pour MOOV en CI
        moov_not_fee = os.getenv("MOOV_NOT_FEE", "False").lower() == "true"
        is_moov_ci = transaction.network.name == "moov" and transaction.network.country_code.lower() == "ci"
        
        if is_mtn_ci and mtn_not_fee:
            # Pas de fee pour MTN si MTN_NOT_FEE=True
            amount = transaction.amount
        elif is_moov_ci and moov_not_fee:
            # Pas de fee pour MOOV si MOOV_NOT_FEE=True
            amount = transaction.amount
        elif ((
            transaction.network.name == "moov" or transaction.network.name == "mtn"
        ) or transaction.network.name == "orange") and transaction.network.country_code.lower()=="ci":
            amount = round(transaction.amount - (transaction.amount / 100))
        else:
            amount = transaction.amount
        transaction.net_payable_amout = amount
        full_name = (
            transaction.user.full_name()
            if transaction.user
            else transaction.telegram_user.full_name()
        )
        data = {
            "type": "withdrawal",
            "amount": amount,
            "recipient_phone": (
                transaction.phone_number[3:]
                if len(transaction.phone_number) > 10
                else transaction.phone_number
            ),
            "recipient_name": full_name,
            "objet": "Blaffa deposit",
            "network": get_network_id(
                name=f"{transaction.network.name.upper()}-{transaction.network.country_code.upper()}"
            ),
            "callback_url": f"{BASE_URL}/connect-pro-webhook",
        }
        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            connect_pro_logger.info(f" connect pro  response {response.json()}")
            transaction.public_id = response.json().get("data").get("uid")
            transaction.save()
        except Exception as e:
            connect_pro_logger.info(f" connect pro  response exep {e}")


def connect_pro_status(reference, is_wave=False, is_momo_pay=False):
    url = None
    connect_pro_logger.info(f"la reference qui a ete transmi 1111 {reference}")
    if is_wave:
        url = (
            CONNECT_PRO_BASE_URL
            + f"/api/payments/wave-business-transactions/{reference}/"
        )
    elif is_momo_pay:
        url = CONNECT_PRO_BASE_URL + f"/api/payments/momo-pay-transactions/{reference}/"
    else:
        url = CONNECT_PRO_BASE_URL + f"/api/payments/user/transactions/{reference}"
    token = connect_pro_token()
    if not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        connect_pro_logger.info(
            f" connect pro  response status {response.content} status {response.status_code}"
        )
        return response.json()
    except Exception as e:
        connect_pro_logger.critical(f"Erreur de verification de status {e}")


def transaction_process(reference):
    payment_logger.info(f"Debut de process de transaction a {timezone.now()}")
    transaction = Transaction.objects.filter(reference=reference).first()
    if not transaction:
        payment_logger.info(f"Transaction avec reference {reference} non trouver")
    if transaction.type_trans == "deposit" or transaction.type_trans == "reward":
        deposit_connect(transaction=transaction)
    elif transaction.type_trans == "withdrawal":
        pass


@shared_task
def connect_pro_webhook(data):
    connect_pro_logger.info(
        f"le data recue est {data} aavec le public id {data.get('uid')}"
    )
    with db_transaction.atomic():
        transaction = (
            Transaction.objects.filter(public_id=data.get("uid"))
            .exclude(Q(status="error") | Q(status="accept"))
            .select_for_update()
            .first()
        )
        if not transaction:
            connect_pro_logger.info(
                f"La transaction avec public id {data.get('uid')} n'existe pas ou a ete deja traiter"
            )
            return
            # data = None
        transaction.wehook_receive_at = timezone.now()
        transaction.webhook_data = data
        connect_pro_logger.info(f"la reference qui a ete transmi {data.get('uid')}")
        if (
            transaction.network.name == "wave"
            and transaction.type_trans != "withdrawal"
        ):
            data = connect_pro_status(reference=transaction.public_id, is_wave=True)
        else:
            data = connect_pro_status(
                reference=transaction.public_id,
                is_momo_pay=(
                    False
                    if (
                        not transaction.network.payment_by_link
                        or transaction.type_trans == "withdrawal"
                    )
                    else True
                ),
            )
        setting = Setting.objects.first()
        if (
            data.get("status") == "failed" or data.get("status") == "cancelled"
        ) or data.get("status") == "timeout":
            connect_pro_logger.info("Transaction is fail")
            webhook_transaction_failled(transaction=transaction)
        elif data.get("status") == "success" or data.get("status") == "confirmed":
            connect_pro_logger.info("Transaction is success")
            webhook_transaction_success(transaction=transaction, setting=setting)


def webhook_transaction_success(transaction: Transaction, setting: Setting):
    try:
        connect_pro_logger.info(
            f"Début traitement transaction {transaction.id} - Type: {transaction.type_trans}, Status: {transaction.status}"
        )

        if (
            transaction.type_trans == "deposit" or transaction.type_trans == "reward"
        ) and transaction.status != "accept":

            try:
                transaction.status = "init_payment"
                track_status_change(transaction, "init_payment", source="system")
                transaction.save()
                app = transaction.app
                servculAPI = init_mobcash(app_name=app)
                amount = transaction.amount

                if setting.deposit_reward and transaction.type_trans != "reward":
                    bonus = (
                        setting.deposit_reward_percent * transaction.amount
                    ) / constant.BONUS_PERCENT_MAX
                    amount = amount + bonus
                    transaction.deposit_reward_amount = bonus
                    transaction.net_payable_amout = amount
                    transaction.save()

                if transaction.app.hash:
                    response = servculAPI.recharge_account(
                        amount=float(amount), userid=transaction.user_app_id
                    )
                    connect_pro_logger.info(
                        f"Reponse de l'api de {transaction.app.name}: {response}"
                    )
                    xbet_response_data = response.get("data")
                else:
                    response = MobCashExternalService().create_deposit(transaction=transaction)
                    connect_pro_logger.info( 
                        f"Reponse de l'api de {transaction.app.name}: {response}"
                    )
                    xbet_response_data = response
                if xbet_response_data.get("Success") == True:
                    payment_logger.info(
                        f"Transaction de {transaction.app.name} success"
                    )
                    transaction.validated_at = timezone.now()
                    transaction.status = "accept"
                    track_status_change(transaction, "accept", source="system")
                    transaction.save()

                    # Appel de la tâche Celery pour les opérations lentes (notifications, bonus, etc.)
                    try:
                        process_transaction_notifications_and_bonus.delay(transaction_id=transaction.id)
                    except Exception as e:
                        connect_pro_logger.error(
                            f"Erreur process_transaction_notifications_and_bonus.delay pour transaction {transaction.id}: {str(e)}",
                            exc_info=True,
                        )

                    # Si c'est une reward, on doit aussi appeler check_solde
                    if transaction.type_trans == "reward":
                        try:
                            check_solde.delay(transaction_id=transaction.id)
                        except Exception as e:
                            connect_pro_logger.error(
                                f"Erreur check_solde.delay pour transaction {transaction.id}: {str(e)}",
                                exc_info=True,
                            )
                        return 

                    # Pour les dépôts normaux, on appelle aussi check_solde
                    try:
                        check_solde.delay(transaction_id=transaction.id)
                    except Exception as e:
                        connect_pro_logger.error(
                            f"Erreur check_solde.delay pour transaction {transaction.id}: {str(e)}",
                            exc_info=True,
                        )
                else:
                    # Handle transaction failure - Appel de la tâche Celery pour les notifications d'erreur
                    app_name = transaction.app.name.upper() if transaction.app else "l'application"
                    error_message = (
                        f"Une erreur est survenue lors de votre dépôt de {transaction.amount} FCFA sur "
                        f"{app_name}. "
                        f"{app_name} Message: {xbet_response_data.get('Message')}. "
                        f"Référence de la transaction {transaction.reference}"
                    )
                    transaction.message=xbet_response_data.get('Message')
                    transaction.save()
                    try:
                        process_transaction_notifications_and_bonus.delay(
                            transaction_id=transaction.id,
                            is_error=True,
                            error_message=error_message
                        )
                    except Exception as e:
                        connect_pro_logger.error(
                            f"Erreur process_transaction_notifications_and_bonus.delay (erreur) pour transaction {transaction.id}: {str(e)}",
                            exc_info=True,
                        )

            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur traitement deposit/reward transaction {transaction.id}: {str(e)}",
                    exc_info=True,
                )
                raise
        else:
            try:
                connect_pro_logger.info(f"Operation success")
                transaction.status = "accept"
                track_status_change(transaction, "accept", source="system")
                transaction.save()

                # Appel de la tâche Celery pour les notifications (retrait)
                try:
                    process_transaction_notifications_and_bonus.delay(transaction_id=transaction.id)
                except Exception as e:
                    connect_pro_logger.error(
                        f"Erreur process_transaction_notifications_and_bonus.delay pour transaction {transaction.id}: {str(e)}",
                        exc_info=True,
                    )
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur traitement retrait transaction {transaction.id}: {str(e)}",
                    exc_info=True,
                )
                raise
    except Exception as e:
        connect_pro_logger.error(
            f"Erreur globale webhook_transaction_success transaction {transaction.id}: {str(e)}"
        )


def webhook_transaction_failled(transaction: Transaction):
    payment_logger.info(f"Transaction with ")
    transaction.status = "error"
    track_status_change(transaction, "error", source="system")
    transaction.save()
    if transaction.type_trans == "reward":
        reward_failed_process(transaction=transaction)
    transaction.refresh_from_db()
    
    # Envoyer une notification d'erreur à l'utilisateur
    try:
        app_name = transaction.app.name.upper() if transaction.app else "l'application"
        if transaction.type_trans == "deposit":
            error_message = (
                f"Une erreur est survenue lors de votre dépôt de {transaction.amount} FCFA sur "
                f"{app_name}. "
                f"Référence de la transaction : {transaction.reference}"
            )
        elif transaction.type_trans == "withdrawal":
            error_message = (
                f"Une erreur est survenue lors de votre retrait de {transaction.amount} FCFA sur "
                f"{app_name}. "
                f"Référence de la transaction : {transaction.reference}"
            )
        elif transaction.type_trans == "reward":
            error_message = (
                f"Une erreur est survenue lors de l'utilisation de vos rewards de {transaction.amount} FCFA sur "
                f"{app_name}. "
                f"Référence de la transaction : {transaction.reference}"
            )
        else:
            error_message = (
                f"Une erreur est survenue lors de votre transaction de {transaction.amount} FCFA. "
                f"Référence de la transaction : {transaction.reference}"
            )
        
        process_transaction_notifications_and_bonus.delay(
            transaction_id=transaction.id,
            is_error=True,
            error_message=error_message
        )
    except Exception as e:
        connect_pro_logger.error(
            f"Erreur envoi notification échec transaction {transaction.id}: {str(e)}",
            exc_info=True,
        )


def reward_failed_process(transaction: Transaction):
    payment_logger.info(f"Remboursement des bonus pris ")
    bonus = Bonus.objects.filter(
        user=transaction.user, bonus_with=True, bonus_delete=False
    )
    if bonus.exists():
        bonus = bonus.update(bonus_with=False)
        return bonus
    return


def accept_bonus_transaction(transaction: Transaction):
    bonus = Bonus.objects.filter(user=transaction.user, bonus_delete=False)
    if bonus.exists():
        bonus = bonus.update(bonus_with=True, bonus_delete=True)


@shared_task
def process_transaction_notifications_and_bonus(transaction_id, is_error=False, error_message=None):
    user = transaction.user if transaction.user else transaction.telegram_user
    """
    Tâche Celery pour traiter les notifications et bonus après une transaction.
    Cette fonction gère toutes les opérations lentes de manière asynchrone.
    
    Args:
        transaction_id: ID de la transaction
        is_error: True si c'est une notification d'erreur
        error_message: Message d'erreur à envoyer (si is_error=True)
    """
    try:
        transaction = Transaction.objects.select_related(
            'user', 'telegram_user', 'app', 'network'
        ).filter(id=transaction_id).first()

        if not transaction:
            connect_pro_logger.error(
                f"Transaction {transaction_id} non trouvée dans process_transaction_notifications_and_bonus"
            )
            return

        setting = Setting.objects.first()
        if not setting:
            connect_pro_logger.error("Setting non trouvé dans process_transaction_notifications_and_bonus")
            return

        # Gestion des notifications d'erreur
        if is_error:
            try:
                user = transaction.user if transaction.user else transaction.telegram_user
                if user:
                    send_notification(
                        title="Erreur de transaction",
                        content=error_message or f"Une erreur est survenue lors de votre transaction de {transaction.amount} FCFA.",
                        user=user,
                        reference=transaction.reference,
                    )
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur send_notification échec transaction {transaction_id}: {str(e)}",
                    exc_info=True,
                )

            # Message Telegram pour les admins en cas d'erreur
            try:
                user_obj = transaction.user if transaction.user else transaction.telegram_user
                if user_obj:
                    first_name = getattr(user_obj, "first_name", "") or getattr(user_obj, "username", "Inconnu")
                    last_name = getattr(user_obj, "last_name", "")
                    full_name = f"{first_name.upper()} {last_name.capitalize()}".strip()

                    app_name = getattr(transaction.app, "name", "Application inconnue").upper() if transaction.app else "Application inconnue"
                    network_name = getattr(transaction.network, "name", "Réseau inconnu").upper() if transaction.network else "Réseau inconnu"
                    indication = getattr(transaction.network, "indication", "") if transaction.network else ""

                    content = (
                        f"{full_name} a lancé une demande de dépôt de {app_name}. "
                        f"Montant : {transaction.amount} F CFA | "
                        f"Numéro de référence : {transaction.reference} | "
                        f"Réseau : {network_name} Mobile Money | "
                        f"User App ID : {transaction.user_app_id} | "
                        f"Téléphone : +{indication} {transaction.phone_number}."
                    )

                    send_telegram_message(content=content)
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur send_telegram_message pour transaction {transaction_id}: {str(e)}",
                    exc_info=True,
                )
            return

        # 1. Notification à l'utilisateur pour transaction réussie
        if transaction.type_trans in ["deposit", "reward"]:
            try:
                if user:
                    app_name = transaction.app.name if transaction.app else "l'application"
                    send_notification(
                        title="Opération réussie avec succès",
                        content=f"Vous avez effectué un dépôt de {transaction.amount} FCFA sur votre compte {app_name}",
                        user=user,
                    )
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur send_notification utilisateur pour transaction {transaction_id}: {str(e)}",
                    exc_info=True,
                )

        # 2. Si c'est une reward, accepter les bonus
        if transaction.type_trans == "reward":
            try:
                accept_bonus_transaction(transaction=transaction)
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur accept_bonus_transaction pour transaction {transaction_id}: {str(e)}",
                    exc_info=True,
                )

        # 3. Attribution de bonus de parrainage (si applicable)
        if (
            transaction.type_trans in ["deposit", "withdrawal"]
            and transaction.user 
            and transaction.user.referrer_code 
            and setting.referral_bonus
        ):
            try:
                user_referrer = User.objects.filter(
                    referral_code=transaction.user.referrer_code
                ).first()

                if user_referrer:
                    bonus_amount = (
                        setting.bonus_percent * transaction.amount
                    ) / constant.BONUS_PERCENT_MAX

                    Bonus.objects.create(
                        transaction=transaction,
                        user=user_referrer,
                        amount=bonus_amount,
                        reason_bonus="Bonus de parrainage de transaction",
                    )

                    reward, _ = Reward.objects.get_or_create(
                        user=user_referrer
                    )
                    reward.amount = float(reward.amount) + float(bonus_amount)
                    reward.save()

                    # Notification au parrain
                    send_notification(
                        title="Félicitations, vous avez un bonus !",
                        content=f"Vous venez de recevoir un bonus grâce à une opération de {transaction.amount} FCFA effectuée par {transaction.user.email}.",
                        user=user_referrer,
                    )
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur bonus parrainage pour transaction {transaction_id}: {str(e)}",
                    exc_info=True,
                )

        # 4. Notification pour retrait
        if transaction.type_trans == "withdrawal":
            try:
                app_name = transaction.app.name if transaction.app else "l'application"
                if transaction.user:
                    send_notification(
                        title="Opération réussie",
                        content=f"Vous avez effectué un retrait de {transaction.amount} FCFA sur {app_name}",
                        user=transaction.user,
                    )
                elif transaction.telegram_user:
                    send_telegram_message(
                        chat_id=transaction.telegram_user.telegram_user_id,
                        content=f"Vous avez effectué un retrait de {transaction.amount} FCFA sur {app_name}",
                    )
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur notification retrait pour transaction {transaction_id}: {str(e)}",
                    exc_info=True,
                )

        connect_pro_logger.info(
            f"process_transaction_notifications_and_bonus terminé avec succès pour transaction {transaction_id}"
        )

    except Exception as e:
        connect_pro_logger.error(
            f"Erreur globale process_transaction_notifications_and_bonus pour transaction {transaction_id}: {str(e)}",
            exc_info=True,
        )


@shared_task
def check_solde(transaction_id):
    with db_transaction.atomic():
        transaction = Transaction.objects.filter(
            id=transaction_id,
            fond_calculate=False,
            status__in=["accept", "payment_init_success"],
        ).first()

        if transaction:
            caisse, created = Caisse.objects.get_or_create(bet_app=transaction.app)

            # Tentative de récupération du solde depuis l'API Mobcash
            try:
                # Récupération des credentials depuis AppName
                cashdesk_id = transaction.app.cashdeskid
                hash_key = transaction.app.hash
                cashier_pass = transaction.app.cashierpass

                # Vérification que les credentials existent
                if cashdesk_id and hash_key and cashier_pass:
                    # Conversion de cashdesk_id en int si nécessaire
                    try:
                        cashdesk_id_int = int(cashdesk_id)
                    except (ValueError, TypeError):
                        cashdesk_id_int = None

                    if cashdesk_id_int:
                        # Appel API async
                        balance_result = asyncio.run(
                            get_balance(cashdesk_id_int, hash_key, cashier_pass)
                        )
                    else:
                        # Fallback: cashdesk_id invalide
                        balance_result = None

                    # Mise à jour du solde si succès
                    if (
                        balance_result
                        and isinstance(balance_result, dict)
                        and "Limit" in balance_result
                    ):
                        caisse.solde = float(balance_result["Limit"])
                        caisse.save()
                    else:
                        # Fallback: ancienne logique de calcul
                        if transaction.type_trans == "deposit":
                            caisse.solde = float(caisse.solde) - float(
                                transaction.amount
                            )
                        elif transaction.type_trans == "withdrawal":
                            caisse.solde = float(caisse.solde) + float(
                                transaction.amount
                            )
                        caisse.save()
                elif not hash_key:
                    # Si app n'a pas de hash, utiliser MobCashExternalService
                    connect_pro_logger.info(
                        f"[CHECK_SOLDE] App {transaction.app.name} n'a pas de hash, utilisation de MobCashExternalService.get_wallet_balance()"
                    )
                    mobcash_service = MobCashExternalService()
                    balance = mobcash_service.get_wallet_balance()
                    if balance is not None and balance >= 0:
                        caisse.solde = float(balance)
                        caisse.save()
                        connect_pro_logger.info(
                            f"[CHECK_SOLDE] Solde récupéré via MobCashExternalService: {balance}"
                        )
                    else:
                        # Fallback: ancienne logique de calcul
                        connect_pro_logger.warning(
                            f"[CHECK_SOLDE] Échec récupération solde via MobCashExternalService, utilisation de l'ancienne logique"
                        )
                        if transaction.type_trans == "deposit":
                            caisse.solde = float(caisse.solde) - float(transaction.amount)
                        elif transaction.type_trans == "withdrawal":
                            caisse.solde = float(caisse.solde) + float(transaction.amount)
                        caisse.save()
                else:
                    # Fallback: credentials manquants (cashdesk_id ou cashier_pass), utiliser l'ancienne logique
                    if transaction.type_trans == "deposit":
                        caisse.solde = float(caisse.solde) - float(transaction.amount)
                    elif transaction.type_trans == "withdrawal":
                        caisse.solde = float(caisse.solde) + float(transaction.amount)
                    caisse.save()
            except Exception as e:
                # Fallback en cas d'erreur
                if transaction.type_trans == "deposit":
                    caisse.solde = float(caisse.solde) - float(transaction.amount)
                elif transaction.type_trans == "withdrawal":
                    caisse.solde = float(caisse.solde) + float(transaction.amount)
                caisse.save()
            transaction.fond_calculate = True
            transaction.save()
            transaction.refresh_from_db()


@shared_task
def payment_fonction(reference):
    transaction = Transaction.objects.filter(reference=reference).first()
    if not transaction:
        connect_pro_logger.info(f"Transaction avec reference {reference} non trouver")
        return
    
    if transaction.type_trans == "deposit" or transaction.type_trans == "reward":
        if transaction.api == "connect":
            deposit_connect(transaction=transaction)
        elif transaction.api == "feexpay":
            feexpay_deposit(transaction=transaction)
    elif transaction.type_trans == "withdrawal":
        if transaction.api == "connect":
            connect_pro_withd_process(transaction=transaction)
        elif transaction.api == "feexpay":
            feexpay_withdrawall_process.delay(transaction_id=transaction.id)


def xbet_withdrawal_process(transaction: Transaction):
    connect_pro_logger.info("Demarraage de retrait avec l'app de mobcash ")
    app_name = transaction.app
    servculAPI = init_mobcash(app_name=app_name)
    
    if transaction.type_trans == "withdrawal":
        if transaction.app.hash:
            response = servculAPI.withdraw_from_account(
                userid=transaction.user_app_id, code=transaction.withdriwal_code
            )
            xbet_response_data = response.get("data")
        else:
            response = MobCashExternalService().create_withdrawal(transaction=transaction)
            connect_pro_logger.info(
                        f"Reponse de l'api de {transaction.app.name}: {response}"
                    )
            xbet_response_data = response
        connect_pro_logger.info(f"La reponse de retrait de mobcash{response}")
        if (
            str(xbet_response_data.get("Success")).lower() == "false"
            or xbet_response_data.get("status") == 401
        ):
            transaction.status = "error"
            track_status_change(transaction, "error", source="system")
            transaction.message=xbet_response_data.get('Message')
            transaction.save()
            transaction.refresh_from_db()
            app_name = transaction.app.name.upper() if transaction.app else "l'application"
            error_message = (
                f"Une erreur est survenue lors de votre retrait de {transaction.amount} FCFA sur "
                f"{app_name}. "
                f"{app_name} Message: {xbet_response_data.get('Message')}. "
                f"Référence de la transaction {transaction.reference}"
            )
            
            send_notification(user=transaction.user, content=error_message, title="Erreur de transaction")
            connect_pro_logger.info("L'appelle a ete success")
        elif str(xbet_response_data.get("Success")).lower() == "true":
            connect_pro_logger.info("app BET step suvccess 11111111")
            amount = float(xbet_response_data.get("Summa")) * (-1)
            transaction.amount = amount
            transaction.status = "init_payment"
            track_status_change(transaction, "init_payment", source="system")
            transaction.validated_at = timezone.now()
            transaction.save()
            transaction.refresh_from_db()
            connect_pro_logger.info("L'appelle a ete echec")
            return True


def send_event(channel_name, event_name, data):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        channel_name,
        {
            "type": event_name,
            "data": data,
        },
    )


def send_transaction_event_once(transaction: Transaction):
    """Envoie un événement de transaction une seule fois par statut"""

    status = transaction.status.lower()
    webhook_flags = {
        "accept": "success_webhook_send",
        "error": "fail_webhook_send",
        "pending": "pending_webhook_send",
        "timeout": "timeout_webhook_send",
    }

    flag_field = webhook_flags.get(status)
    if not flag_field:
        logging.info(f"Statut non reconnu pour les webhooks: {status}")
        return False

    # Si l'événement a déjà  été envoyé et qu'on ne force pas, ne pas renvoyer
    if getattr(transaction, flag_field, False):
        logging.info(
            f"Événement déjà envoyé pour transaction {transaction.id} avec statut {status}"
        )
        return False
    logging.info(f"Event envoyer avec le status {status}")
    send_event(
        channel_name=f"private-channel_{str(transaction.user.id)}",
        event_name="transaction",
        data=TransactionDetailsSerializer(transaction).data,
    )
    # Marquer comme envoyé
    setattr(transaction, flag_field, True)
    transaction.save(update_fields=[flag_field])
    return True


def disbursment_process(transaction: Transaction):
    webhook_transaction_success(transaction=transaction)


# ==================== FEEXPAY FUNCTIONS ====================

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
    network_name = None
    if transaction.network.name == "sbin":
        url= "https://api.feexpay.me/api/payouts/public/celtiis_bj"
        network_name = "	CELTIIS BJ"
    else:
        url = "https://api.feexpay.me/api/payouts/public/transfer/global"
        network_name = transaction.network.name.upper()

    # Préparer les données
    amount = int(float(transaction.amount)) if transaction.amount else 0
    if amount <= 0:
        connect_pro_logger.error(f"Montant invalide: {transaction.amount}")
        return

    # Récupérer le numéro de téléphone
    phone_number = transaction.phone_number 

    # Déterminer le réseau depuis payment_mode ou network

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
        response = requests.post(url=url, json=data, headers=headers, timeout=120)
        connect_pro_logger.info(f"le data envoyer data======{data}, url======{url} ")
        connect_pro_logger.info(f" feexpay payout response {response.json()}")

        response_data = response.json()

        # Sauvegarder la référence Feexpay dans la transaction
        feexpay_reference = response_data.get("reference") or response_data.get("data", {}).get("reference")
        if feexpay_reference:
            transaction.public_id = feexpay_reference
            # Si Feexpay retourne un UID/public_id, le sauvegarder aussi
            feexpay_uid = response_data.get("uid") or response_data.get("data", {}).get("uid")
            if feexpay_uid:
                transaction.public_id = feexpay_uid
            transaction.save()

        # connect_pro_logger.critical(f" Erreur de creation feexpay payout network error {e}")
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
        connect_pro_logger.info(
            f" feexpay response 22 {response.json()} data === {data}"
        )

        response_data = response.json()

        # Sauvegarder la référence Feexpay dans la transaction
        feexpay_reference = response_data.get("reference") or response_data.get("data", {}).get("reference")
        if feexpay_reference:
            transaction.public_id = feexpay_reference
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


from django.db import transaction as db_transaction
@shared_task
def feexpay_withdrawall_process(transaction_id, disbursements=False):
    transaction= Transaction.objects.get(id=transaction_id)
    """
    Traite le retrait Feexpay de manière atomique
    Empêche le double traitement même avec Celery
    """

    connect_pro_logger.info(
        f"[FEEXPAY_WITHDRAW] Début process | transaction_id={transaction.id}"
    )

    try:
        with db_transaction.atomic():
            # 🔒 Lock de la transaction en base
            trx = (
                Transaction.objects
                .select_for_update()
                .get(id=transaction.id)
            )

            # 🛑 Sécurité anti double traitement
            if trx.payout_started:
                connect_pro_logger.warning(
                    f"[FEEXPAY_WITHDRAW] Déjà en cours | transaction_id={trx.id}"
                )
                return False

            if trx.payout_done:
                connect_pro_logger.warning(
                    f"[FEEXPAY_WITHDRAW] Déjà traité | transaction_id={trx.id}"
                )
                return False

            # Marquer comme démarré AVANT tout appel externe
            trx.payout_started = True
            trx.save(update_fields=["payout_started"])

            connect_pro_logger.info(
                f"[FEEXPAY_WITHDRAW] Lock OK | transaction_id={trx.id}"
            )

            # 🔁 Traitement métier
            if trx.type_trans == "withdrawal" and not disbursements:
                response = xbet_withdrawal_process(transaction=trx)
            else:
                response = True

            if response is not True:
                raise Exception("Echec du process xbet_withdrawal")

        # ⚠️ On sort volontairement du atomic ici
        # 👉 appel externe (Feexpay)
        connect_pro_logger.info(
            f"[FEEXPAY_WITHDRAW] Appel payout Feexpay | transaction_id={trx.id}"
        )

        feexpay_payout(transaction=trx)

        # ✅ Finalisation
        with db_transaction.atomic():
            trx = Transaction.objects.select_for_update().get(id=trx.id)
            trx.payout_done = True
            trx.save(update_fields=["payout_done"])

            connect_pro_logger.info(
                f"[FEEXPAY_WITHDRAW] Succès final | transaction_id={trx.id}"
            )

        return True

    except OperationalError as e:
        connect_pro_logger.error(
            f"[FEEXPAY_WITHDRAW] Lock DB échoué | transaction_id={transaction.id} | {e}",
            exc_info=True
        )
        return False

    except Exception as e:
        connect_pro_logger.error(
            f"[FEEXPAY_WITHDRAW] Erreur critique | transaction_id={transaction.id} | {e}",
            exc_info=True
        )
        return False


def feexpay_check_status(public_id):
    """
    Vérifie le statut d'une transaction Feexpay
    """
    url = f"https://api.feexpay.me/api/transactions/public/single/status/{public_id}"
    header = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('FEEXPAY_API_KEY')}",
    }
    try:
        connect_pro_logger.info(f"GET {url}")
        response = requests.get(url=url, headers=header, timeout=30)
        connect_pro_logger.info(f"Response: {response.status_code} {response.text}")
        return {"code": constant.CODE_SUCCESS, "data": response.json()}
    except Exception as e:
        connect_pro_logger.error(f"Error during GET {url}: {str(e)}")
        return {"code": constant.CODE_EXEPTION, "erreur": f"{e}"}


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
            .select_for_update()
            .first()
        )

        if not transaction:
            connect_pro_logger.info(
                f"La transaction avec reference {reference} n'existe pas ou a ete deja traiter"
            )
            return

        transaction.wehook_receive_at = timezone.now()
        # Convertir data en string pour TextField (comme dans connect_pro_webhook)
        transaction.webhook_data = json.dumps(data) if isinstance(data, dict) else str(data)
        connect_pro_logger.info(f"la reference qui a ete transmi {reference}")

        setting = Setting.objects.first()

        # Adapter les statuts Feexpay aux statuts Connect
        if transaction_status == "FAILED" or transaction_status == "failed" or transaction_status == "cancelled":
            connect_pro_logger.info("Transaction is fail")
            webhook_transaction_failled(transaction=transaction)
        elif transaction_status == "SUCCESSFUL" or transaction_status == "success" or transaction_status == "confirmed":
            connect_pro_logger.info("Transaction is success")
            webhook_transaction_success(transaction=transaction, setting=setting)


@shared_task
def check_pending_feexpay_transactions():
    """
    Vérifie le statut de toutes les transactions Feexpay en attente (pending)
    et les traite via feexpay_webhook si leur statut a changé.
    Cette fonction est appelée toutes les 2 minutes par Celery Beat.
    """
    connect_pro_logger.info("Début de la vérification des transactions Feexpay pending")
    
    # Récupérer toutes les transactions pending avec api="feexpay"
    # Exclure celles qui sont déjà acceptées ou en erreur (pour éviter de retraiter)
    pending_transactions = Transaction.objects.filter(
        status="pending",
        api="feexpay"
    ).exclude(
        Q(public_id__isnull=True) | Q(public_id="")
    ).exclude(
        Q(status="accept") | Q(status="error")
    )
    
    if not pending_transactions.exists():
        connect_pro_logger.info("Aucune transaction Feexpay pending à vérifier")
        return
    
    count = pending_transactions.count()
    connect_pro_logger.info(f"Vérification de {count} transaction(s) Feexpay pending")
    
    processed_count = 0
    error_count = 0
    
    for transaction in pending_transactions:
        try:
            # Vérifier le statut avec feexpay_check_status
            # feexpay_check_status utilise public_id dans l'URL, donc on doit utiliser public_id uniquement
            public_id = transaction.public_id
            
            if not public_id:
                connect_pro_logger.warning(
                    f"Transaction {transaction.id} n'a pas de public_id, ignorée"
                )
                continue
            
            connect_pro_logger.info(
                f"Vérification du statut pour transaction {transaction.id} (reference: {transaction.reference}) avec public_id: {public_id}"
            )
            
            status_result = feexpay_check_status(public_id)
            
            # Vérifier si la vérification a réussi
            if status_result.get("code") != constant.CODE_SUCCESS:
                connect_pro_logger.error(
                    f"Erreur lors de la vérification du statut pour transaction {transaction.id}: {status_result.get('erreur')}"
                )
                error_count += 1
                continue
            
            # Récupérer les données de statut
            status_data = status_result.get("data", {})
            
            if not status_data:
                connect_pro_logger.warning(
                    f"Aucune donnée retournée pour transaction {transaction.id}"
                )
                continue
            
            # Formater les données comme un webhook Feexpay
            # Le webhook Feexpay attend un format avec reference/externalId et status
            webhook_data = {
                "reference": status_data.get("reference") or public_id,
                "externalId": transaction.reference or public_id,
                "uid": public_id,
                "status": status_data.get("status") or status_data.get("transactionStatus"),
                **status_data  # Inclure toutes les autres données
            }
            
            # Appeler feexpay_webhook pour traiter la transaction
            feexpay_status = webhook_data.get('status')
            connect_pro_logger.info(
                f"Traitement de la transaction {transaction.id} via feexpay_webhook avec status: {feexpay_status}"
            )
            
            # Sauvegarder l'ID de la transaction avant l'appel
            transaction_id = transaction.id
            
            # Vérifier si la transaction a déjà été tentée dans webhook_transaction_success
            transaction_already_attempted = (
                transaction.status == "init_payment" or 
                transaction.webhook_data is not None or 
                transaction.wehook_receive_at is not None
            )
            
            feexpay_webhook(webhook_data)
            
            # Recharger la transaction depuis la DB pour voir son statut actuel
            transaction.refresh_from_db()
            
            # Vérifier si Feexpay dit SUCCESSFUL mais la transaction n'est pas accept
            if (
                feexpay_status in ["SUCCESSFUL", "success", "confirmed"] and
                transaction.status != "accept" and
                transaction_already_attempted
            ):
                # C'est un 2ème appel qui a échoué - envoyer notification Telegram
                try:
                    user_info = ""
                    if transaction.user:
                        user_info = f"User: {transaction.user.email} (ID: {transaction.user.id})"
                    elif transaction.telegram_user:
                        user_info = f"Telegram User: {transaction.telegram_user.telegram_user_id}"
                    else:
                        user_info = "User inconnu"
                    
                    app_name = transaction.app.name if transaction.app else "Application inconnue"
                    
                    message = (
                        f"⚠️ ALERTE: Transaction Feexpay SUCCESSFUL mais non traitée\n\n"
                        f"Référence: {transaction.reference}\n"
                        f"Numero: {transaction.phone_number}\n"
                        f"Reseau: {transaction.network.public_name}\n"
                        f"Montant: {transaction.amount} FCFA\n"
                        f"Type: {transaction.type_trans}\n"
                        f"Application: {app_name}\n"
                        f"{user_info}\n"
                        f"Statut Feexpay: {feexpay_status}\n"
                        f"Statut actuel DB: {transaction.status}\n"
                        
                        f"Timestamp: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"⚠️ Cette transaction a déjà été tentée dans webhook_transaction_success mais n'a pas été acceptée."
                    )
                    
                    send_telegram_message(content=message)
                    connect_pro_logger.warning(
                        f"Notification Telegram envoyée pour transaction {transaction_id} - "
                        f"Feexpay SUCCESSFUL mais status DB: {transaction.status}"
                    )
                except Exception as e:
                    connect_pro_logger.error(
                        f"Erreur envoi notification Telegram pour transaction {transaction_id}: {str(e)}",
                        exc_info=True
                    )
            
            processed_count += 1
            
        except Exception as e:
            connect_pro_logger.error(
                f"Erreur lors du traitement de la transaction {transaction.id}: {str(e)}",
                exc_info=True
            )
            error_count += 1
            continue
    
    connect_pro_logger.info(
        f"Vérification terminée: {processed_count} transaction(s) traitée(s), {error_count} erreur(s)"
    )
    
    return {
        "total": count,
        "processed": processed_count,
        "errors": error_count
    }


def connect_balance():
    url = f"{CONNECT_PRO_BASE_URL}/api/payments/user/account/"
    token = connect_pro_token()
    if not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url=url, headers=headers, timeout=30)
        return {"data": response.json(), "code": constant.CODE_SUCCESS}
    except Exception as e:
        return {"error": str(e), "code": constant.CODE_EXEPTION}
