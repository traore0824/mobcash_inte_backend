from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from logger import LoggerService
from mobcash_inte.models import Transaction
import logging

from payment import send_transaction_event_once
logger = logging.getLogger(__name__)

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
        send_transaction_event_once(instance)
    else:
        logger.info(f"signal non envoyer {instance.status}")
        LoggerService.d(
            f"Transaction {instance.id} mise à jour sans changement de statut"
        )
