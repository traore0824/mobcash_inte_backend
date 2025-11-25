import requests
import os
from accounts.models import User
import constant
from dotenv import load_dotenv
load_dotenv()
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
from django.db import transaction as db_transaction
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


def connect_base_url():
    # setting = Setting.objects.first()
    return  "https://connect.turaincash.com"

CONNECT_PRO_BASE_URL = connect_base_url()


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
        connect_pro_logger.debug(f"la liste des resaeu de connect {response.json()}")
        results = response.json().get("results")
        for data in results:
            if data.get("code") == name:
                return data.get("uid")
    except Exception as e:
        connect_pro_logger.critical(f"Erreur de recuperation de resaeu {e}")


def connect_withdrawal(transaction: Transaction):
    token = connect_pro_token()
    if not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = CONNECT_PRO_BASE_URL + "/api/payments/user/transactions/"
    transaction.save()

    data = {
        "type": "deposit",
        "amount": f"{transaction.amount}",
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
        connect_withdrawal(transaction=transaction)
        # content = (
        #     "💸 **Nouvelle demande de retrait** 💸\n\n"
        #     f"**Référence :** {transaction.reference}\n"
        #     f"**Nom de la plateforme :** {transaction.app.name if transaction.app else 'N/A'}\n"
        #     f"**User ID :** {transaction.user_app_id}\n"
        #     f"**Email :** {transaction.user.email if transaction.user and hasattr(transaction.user, 'email') else 'N/A'}\n"
        #     f"**Téléphone :** {transaction.phone_number or 'N/A'}"
        #     f"**Montant :** {transaction.amount } Franc"
        #     f"**Reseau :** {transaction.network.name }"
        #     f"**Date de confirmation :** {transaction.validated_at }"
        # )
        # send_telegram_message(content=content)


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
                    + f"?amount%5Bcurrency%5D=XOF&amount%5Bvalue%5D={transaction.amount}"
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
        if (
            transaction.network.name == "moov" or transaction.network.name == "mtn"
        ) or transaction.network.name == "orange":
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
            .select_for_update(nowait=True)
            .first()
        )
        if not transaction:
            connect_pro_logger.info(
                f"La transaction avec public id {data.get("uid")} n'existe pas ou a ete deja traiter"
            )
            return
            # data = None
        transaction.wehook_receive_at = timezone.now()
        transaction.webhook_data = data
        connect_pro_logger.info(f"la reference qui a ete transmi {data.get('uid')}")
        if transaction.network.name == "wave":
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

                response = servculAPI.recharge_account(
                    amount=float(amount), userid=transaction.user_app_id
                )
                connect_pro_logger.info(
                    f"Reponse de l'api de {transaction.app.name}: {response}"
                )

                xbet_response_data = response.get("data")

                if xbet_response_data.get("Success") == True:
                    payment_logger.info(
                        f"Transaction de {transaction.app.name} success"
                    )
                    transaction.validated_at = timezone.now()
                    transaction.status = "accept"
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
                    error_message = (
                        f"Une erreur est survenue lors de votre dépôt de {transaction.amount} FCFA sur "
                        f"{transaction.app.name.upper() if transaction.app else 'l\'application'}. "
                        f"{transaction.app.name.upper() if transaction.app else ''} Message: {xbet_response_data.get('Message')}. "
                        f"Référence de la transaction {transaction.reference}"
                    )
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
    transaction.save()
    if transaction.type_trans == "reward":
        reward_failed_process(transaction=transaction)
    transaction.refresh_from_db()


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
                user = transaction.user if transaction.user else transaction.telegram_user
                if user:
                    send_notification(
                        title="Opération réussie avec succès",
                        content=f"Vous avez effectué un dépôt de {transaction.amount} FCFA sur votre compte {transaction.app.name if transaction.app else 'l\'application'}",
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
            transaction.type_trans == "deposit" 
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
                if transaction.user:
                    send_notification(
                        title="Opération réussie",
                        content=f"Vous avez effectué un retrait de {transaction.amount} FCFA sur {transaction.app.name if transaction.app else 'l\'application'}",
                        user=transaction.user,
                    )
                elif transaction.telegram_user:
                    send_telegram_message(
                        chat_id=transaction.telegram_user.telegram_user_id,
                        content=f"Vous avez effectué un retrait de {transaction.amount} FCFA sur {transaction.app.name if transaction.app else 'l\'application'}",
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
    transaction = (
        Transaction.objects.filter(id=transaction_id).select_for_update().first()
    )
    setting = Setting.objects.first()
    with db_transaction.atomic():
        if transaction.already_process:
            return
        if transaction.type_trans == "withdrawal":
            caisse = (
                Caisse.objects.filter(bet_app=transaction.app)
                .select_for_update()
                .first()
            )
            caisse.solde = float(caisse.solde) + float(transaction.amount)
            caisse.save()
        else:
            caisse = (
                Caisse.objects.filter(bet_app=transaction.app)
                .select_for_update()
                .first()
            )
            caisse.solde = float(caisse.solde) - float(transaction.amount)
            caisse.save()
        if caisse.solde<setting.minimum_solde:
            try:
                send_telegram_message(
                    content=(
                        f"Il ne vous reste plus que {caisse.solde} FCFA "
                        f"sur votre Caisse {caisse.bet_app.name.upper()}. "
                        f"Pensez à recharger votre compte"
                    )
                )
            except Exception as e:
                connect_pro_logger.error(
                    f"Erreur send_telegram_message solde faible pour transaction {transaction_id}: {str(e)}",
                    exc_info=True,
                )


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
            feexpay_withdrawall_process(transaction=transaction)


def xbet_withdrawal_process(transaction: Transaction):
    connect_pro_logger.info("Demarraage de retrait avec l'app de mobcash ")
    app_name = transaction.app
    servculAPI = init_mobcash(app_name=app_name)
    if transaction.type_trans == "withdrawal":
        response = servculAPI.withdraw_from_account(
            userid=transaction.user_app_id, code=transaction.withdriwal_code
        )
        xbet_response_data = response.get("data")
        connect_pro_logger.info(f"La reponse de retrait de mobcash{response}")
        if (
            str(xbet_response_data.get("Success")).lower() == "false"
            or xbet_response_data.get("status") == 401
        ):
            transaction.status = "error"
            transaction.save()
            transaction.refresh_from_db()
            connect_pro_logger.info("L'appelle a ete success")
        elif str(xbet_response_data.get("Success")).lower() == "true":
            connect_pro_logger.info("app BET step suvccess 11111111")
            amount = float(xbet_response_data.get("Summa")) * (-1)
            transaction.amount = amount
            transaction.status = "init_payment"
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
        channel_name=f"private-channel_{str(transaction.created_by.id)}",
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
    url = "https://api.feexpay.me/api/payouts/public/transfer/global"
    
    # Préparer les données
    amount = int(float(transaction.amount)) if transaction.amount else 0
    if amount <= 0:
        connect_pro_logger.error(f"Montant invalide: {transaction.amount}")
        return
    
    # Récupérer le numéro de téléphone
    phone_number = transaction.phone_number or transaction.phone or ""
    # Nettoyer le numéro (retirer le préfixe si présent, comme dans deposit_connect)
    if len(phone_number) > 10:
        phone_number = phone_number[3:] if phone_number.startswith("229") else phone_number
    elif not phone_number.startswith("229") and len(phone_number) == 10:
        # Ajouter le préfixe si absent (pour les retraits, Feexpay peut nécessiter le format complet)
        phone_number = f"229{phone_number}"
    
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
    phone_number = transaction.phone_number or ""
    # Nettoyer le numéro (retirer le préfixe si présent, comme dans deposit_connect)
    if len(phone_number) > 10:
        phone_number = phone_number[3:] if phone_number.startswith("229") else phone_number
    
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
        "email": user.email if user and hasattr(user, 'email') and user.email else "client@mobcash.com",
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
        response = xbet_withdrawal_process(transaction=transaction)
    else:
        response = True
    
    if response == True:
        feexpay_payout(transaction=transaction)


def feexpay_check_status(reference):
    """
    Vérifie le statut d'une transaction Feexpay
    """
    url = f"https://api.feexpay.me/api/transactions/public/single/status/{reference}"
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
