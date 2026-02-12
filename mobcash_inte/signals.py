from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
import requests
from logger import LoggerService
from mobcash_inte.models import Caisse, TestModel, Transaction
import logging
import os 
from dotenv import load_dotenv

from payment import connect_balance, send_transaction_event_once
logger = logging.getLogger(__name__)

from accounts.models import AppName
load_dotenv()
from django.db import (
    transaction as db_transaction,
)

compta_log = logging.getLogger("mobcash_inte_backend.compta_log")


COMPTA_BASE_URL = os.getenv("COMPTA_BASE_URL")
def send_transaction(transaction: Transaction):
    # check_solde.delay(transaction_id=transaction.id)
    if (
        transaction.status == "accept" and not transaction.event_send
    ) and COMPTA_BASE_URL:
        try:
            data = {
               
                "reference": transaction.reference,
                "amount": float(transaction.amount),
                "user_mobcash_id": transaction.user_app_id,
                "source": transaction.source or "other",
                "type": (
                    "depot"
                    if transaction.type_trans == "deposit"
                    else (
                        "retrait" if transaction.type_trans == "withdrawal" else "other"
                    )
                ),
                "api": transaction.api,
                "network": transaction.network.name,
                "mobcash": transaction.app.name,
                "mobcash_balance": float(get_mobcash_balance(app=transaction.app)),
                # "api_balance": float(get_api_balance(transaction=transaction)),
            }

            url = f"{COMPTA_BASE_URL}/compta/transaction"
            headers = {
                "Content-Type": "application/json",
            }

            # ✅ Correction ici : utilisation de json=data au lieu de data=data
            response = requests.post(url=url, json=data, headers=headers)

            # Log de debug
            TestModel.objects.create(name=f"Renvoie de comptat body {response.content} data1111 {data}")

            if str(response.status_code).startswith("2"):
                transaction.event_send = True
                transaction.save()
        except Exception as e:
            TestModel.objects.create(name=f"Renvoie de comptat error {e}")


@receiver(post_save, sender=Transaction)
def on_transaction_update(sender, instance, created, **kwargs):
    if not created:
        send_transaction(transaction=instance)


API_CHOICES = [
    ("bpay", "BPAY"),
    # ("bizao", "Bizao"),
    ("barkapay", "BarkaPay"),
    ("pal", "PAL"),
    ("connect", "Blaffa Connect"),
    ("dgs_pay", "dgs_pay"),
]


def get_api_balance(transaction: Transaction):
    balance = None
    # if transaction.api == "bpay":
    #     update_bpay_balance(transaction=transaction)
    #     balance = BpaySold.objects.first().balance
    # elif transaction.api == "barkapay":
    #     balance = barkapay_balance()
    # elif transaction.api == "pal":
    #     balance = pal_balance()
    if transaction.api == "connect":
        balance = connect_balance()
    # elif transaction.api == "dgs_pay":
    #     balance = dgs_pay_balance()
    compta_log.info(
        f"La balance qui a ete recuperer pour api {transaction.api} balance {balance}"
    )
    return round(float(balance), 2)


def get_mobcash_balance(app: AppName):
    caisse, created = Caisse.objects.get_or_create(bet_app=app)
    return round(float(caisse.solde), 2)


@receiver(pre_save, sender=Transaction)
def transaction_pre_save(sender, instance, **kwargs):
    """Sauvegarde l'ancien statut avant la sauvegarde"""
    if instance.pk:
        try:
            old_instance = Transaction.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Transaction.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Transaction)
def transaction_post_save(sender, instance, created, **kwargs):
    logger.info(f"signal recue avec  111{instance.status}")
    """Envoie un événement si le statut a changé"""

    # Si c'est une nouvelle transaction, ne pas envoyer d'événement ici
    # car l'API s'en charge déjà
    if created:
        LoggerService.d(
            f"Nouvelle transaction créée: {instance.id} avec statut: {instance.status}"
        )
        return

    # Si c'est une mise à jour, vérifier si le statut a changé
    old_status = getattr(instance, "_old_status", None)
    if old_status is not None and old_status != instance.status:
        logger.info(f"signal event ernvoyer {instance.status}")
        LoggerService.d(
            f"Statut de transaction {instance.id} changé de '{old_status}' à '{instance.status}'"
        )
        # send_transaction_event_once(instance)
    else:
        logger.info(f"signal non envoyer {instance.status}")
        LoggerService.d(
            f"Transaction {instance.id} mise à jour sans changement de statut"
        )
