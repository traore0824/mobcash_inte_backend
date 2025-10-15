import requests
from accounts.models import User
import constant
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

connect_pro_logger = logging.getLogger("Connect pro Logger")
payment_logger = logging.getLogger("Payment transaction process")
logger = logging.getLogger(__name__)

CONNECT_PRO_BASE_URL = "https://connect.api.blaffa.net"


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


# def connect_withdrawal(transaction: Transaction):
#     token = connect_pro_token()
#     if not token:
#         return None
#     headers = {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json",
#     }
#     url = CONNECT_PRO_BASE_URL + "/api/payments/user/transactions/"
#     transaction.save()

#     data = {
#         "type": "deposit",
#         "amount": f"{transaction.amount}",
#         "recipient_phone": transaction.phone_number,
#         "recipient_name": transaction.user.full_name(),
#         "objet": "Yapson deposit",
#         "network": get_network_id(
#             name=f"{transaction.network.name}-{transaction.network.country_code}"
#         ),
#         "callback_url": "https://api.blaffa.net/blaffa/connect-pro-webhook",
#     }
#     try:
#         response = requests.post(url, json=data, headers=headers, timeout=30)
#         TestModel.objects.create(name=f"response connect pro with {response.json()}")
#         transaction.public_id = response.json().get("data").get("uid")
#         send_telegram_message(
#             chat_id="5475155671",
#             content=f"{transaction.user.first_name.upper()} {transaction.user.last_name.capitalize()} a lancé une demande de retrait de {transaction.app.name.upper()}. Montant : {transaction.amount} F CFA | Numéro de référence : {transaction.reference} | Réseau : {transaction.network.name.upper()} Mobile Money | User AP ID : {transaction.user_app_id} | Telephone : +{transaction.network.indication} {transaction.phone_number}",
#         )
#         transaction.save()
#     except Exception as e:
#         TestModel.objects.create(name=f"response connect pro with errer {e}")


def connect_pro_withd_process(transaction: Transaction, disbursements=False):
    # if transaction.type_trans == "withdrawal" and not disbursements:
    #     response = xbet_withdrawal_process(transaction=transaction)
    #     TestModel.objects.create(name=f"le retour de xbet {response}")
    # else:
    #     response = True
    # if response == True:
    #     connect_withdrawal(transaction=transaction)
    pass


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
            "amount": transaction.net_payable_amout,
            "recipient_phone": transaction.phone_number,
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
            "amount": transaction.net_payable_amout,
            "recipient_phone": transaction.phone_number,
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
    # else:
    #     TestModel.objects.create(name=f" dans le else 11111111111111111")
    #     url = CONNECT_PRO_BASE_URL + "/api/payments/user/transactions/"
    #     amount = 0
    #     if (
    #         transaction.network.name == "moov" or transaction.network.name == "mtn"
    #     ) or transaction.network.name == "orange":
    #         amount = round_up_half(transaction.amount - (transaction.amount / 100))
    #     else:
    #         amount = transaction.amount
    #     transaction.net_payable_amout = amount
    #     data = {
    #         "type": "withdrawal",
    #         "amount": amount,
    #         "recipient_phone": transaction.phone_number,
    #         "recipient_name": transaction.user.full_name(),
    #         "objet": "Blaffa deposit",
    #         "network": get_network_id(
    #             name=f"{transaction.network.name}-{transaction.network.country_code}"
    #         ),
    #         "callback_url": "https://api.blaffa.net/blaffa/connect-pro-webhook",
    #     }
    #     try:
    #         response = requests.post(url, json=data, headers=headers, timeout=30)
    #         TestModel.objects.create(name=f" connect pro  response {response.json()}")
    #         transaction.public_id = response.json().get("data").get("uid")
    #         transaction.save()
    #     except Exception as e:
    #         TestModel.objects.create(name=f" connect pro  response exep {e}")


def connect_pro_status(reference, is_wave=False, is_momo_pay=False):
    url = None
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
        connect_pro_logger.info(" connect pro  response status {response.json()}")
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


def connect_pro_webhook(data: dict):
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
            # data = None
        transaction.wehook_receive_at = timezone.now()
        if transaction.network.name == "wave":
            data = connect_pro_status(reference=data.get("uid"), is_wave=True)
        else:
            data = connect_pro_status(
                reference=data.get("uid"),
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
            print("payment initier 9999999999999")
            webhook_transaction_failled(transaction=transaction)
        elif data.get("status") == "success" or data.get("status") == "confirmed":
            print("payment initier 100000000000")
            webhook_transaction_success(transaction=transaction, setting=setting)


def webhook_transaction_success(transaction: Transaction, setting: Setting):

    if (
        transaction.type_trans == "deposit" or transaction.type_trans == "reward"
    ) and transaction.status != "accept":
        transaction.status = "init_payment"
        transaction.save()
        app = transaction.app
        servculAPI = init_mobcash(app_name=app)
        amount = transaction.amount
        if setting.deposit_reward:
            bonus = (
                amount(setting.deposit_reward_percent * transaction.amount)
                / constant.BONUS_PERCENT_MAX
            )
            amount = amount + bonus
            transaction.deposit_reward_amount = bonus
            transaction.net_payable_amout = amount
            transaction.save()

        response = servculAPI.recharge_account(
            amount=float(amount), userid=transaction.user_app_id
        )
        payment_logger.info(
            f"Reponse de l'api de {transaction.app.name} de l'api {response}"
        )
        xbet_response_data = response.get("data")

        if xbet_response_data.get("Success") == True:
            payment_logger.info(f"Transaction de {transaction.app.name} success ")
            transaction.validated_at = timezone.now()
            transaction.status = "accept"
            transaction.save()
            if transaction.type_trans == "reward":
                accept_bonus_transaction(transaction=transaction)
            if setting.referral_bonus:
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
                    reward, _ = Reward.objects.get_or_create(user=user_referrer)
                    reward.amount = reward.amount + bonus_amount
                    reward.save()

                    send_notification(
                        title="Félicitations, vous avez un bonus !",
                        content=f" Vous venez de recevoir un bonus grâce à une opération de {transaction.amount} FCFA effectuée par {transaction.user.email}.",
                        user=user_referrer,
                    )

            check_solde.delay(transaction_id=transaction.id)
        else:
            # Handle transaction failure
            send_notification(
                title="Erreur de transaction",
                content=f"Une erreur est survenue lors de votre dépôt de {transaction.amount} FCFA sur {transaction.app.name.upper()}. {transaction.app.name.upper()} Message: {xbet_response_data.get('Message')}. Référence de la transaction {transaction.reference}",
                user=transaction.user,
                reference=transaction.reference,
            )
            send_telegram_message(
                content=f"{transaction.user.first_name.upper()} {transaction.user.last_name.capitalize()} a lancé une demande de depot de {transaction.app.name.upper()}. Montant : {transaction.amount} F CFA | Numéro de référence : {transaction.reference} | Réseau : {transaction.network.name.upper()} Mobile Money | User AP ID : {transaction.user_app_id} | Telephone : +{transaction.network.indication} {transaction.phone_number}. ",
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
    bonus = Bonus.objects.filter(transaction=transaction)
    if bonus.exists():
        bonus = bonus.update(bonus_with=True, bonus_delete=True)


@shared_task
def check_solde(transaction: Transaction):
    with db_transaction.atomic():
        if transaction.already_process:
            return
        if transaction.type_trans == "withdrawal":
            caisse = (
                Caisse.objects.filter(bet_app=transaction.app)
                .select_for_update()
                .first()
            )
            caisse.solde = caisse.solde + transaction.amount
            caisse.save()
        else:
            caisse = (
                Caisse.objects.filter(bet_app=transaction.app)
                .select_for_update()
                .first()
            )
            caisse.solde = caisse.solde - transaction.amount
            caisse.save()


@shared_task
def payment_fonction(reference):
    transaction = Transaction.objects.filter(reference=reference).first()
    if not transaction:
        logger.info(f"Transaction avec reference {reference} non trouver")
    if transaction.type_trans == "deposit" or transaction.type_trans=="reward":
        if transaction.network.deposit_api == "connect":
            deposit_connect(transaction=transaction)
    elif transaction.type_trans == "withdrawal":
        xbet_withdrawal_process(transaction=transaction)


def xbet_withdrawal_process(transaction: Transaction):
    app_name = transaction.app
    servculAPI = init_mobcash(app_name=app_name)
    if transaction.type_trans == "withdrawal":
        response = servculAPI.withdraw_from_account(
            userid=transaction.user_app_id, code=transaction.withdriwal_code
        )
        xbet_response_data = response.get("data")
        logger.info(f"La reponse de retrait de mobcash{response}")
        print(f"xbet_response_data {xbet_response_data}")
        if (
            str(xbet_response_data.get("Success")).lower() == "false"
            or xbet_response_data.get("status") == 401
        ):
            transaction.status = "error"
            transaction.save()
        elif str(xbet_response_data.get("Success")).lower() == "true":
            logger.info("app BET step suvccess 11111111")
            amount = float(xbet_response_data.get("Summa")) * (-1)
            transaction.amount = amount - transaction.fee
            transaction.status = "payment_init_success"
            transaction.last_xbet_trans = timezone.now()
            transaction.save()
            return True
    transaction.refresh_from_db()


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
