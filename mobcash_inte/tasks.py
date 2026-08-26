from celery import shared_task
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.db.models import Sum
import logging
import time

logger = logging.getLogger("mobcash_inte_backend.transactions")
@shared_task
def grant_coupon_publishing_permissions():
    """
    Attribue can_publish_coupons=True aux utilisateurs actifs
    ayant au moins 2 mois d'ancienneté.
    Planifié chaque nuit à 00h00.
    """
    from accounts.models import User
    two_months_ago = timezone.now() - relativedelta(months=2)
    updated_count = User.objects.filter(
        date_joined__lte=two_months_ago,
        can_publish_coupons=False,
        is_active=True,
        is_delete=False,
    ).update(can_publish_coupons=True)
    return updated_count


@shared_task
def grant_coupon_rating_permissions():
    """
    Attribue can_rate_coupons=True aux utilisateurs actifs ayant:
    - Au moins 1 mois d'ancienneté
    - Au moins 15 000 FCFA de transactions de dépôt acceptées
    Planifié chaque nuit à 00h00.
    """
    from accounts.models import User
    from mobcash_inte.models import Transaction

    one_month_ago = timezone.now() - relativedelta(months=1)
    eligible_by_age = User.objects.filter(
        date_joined__lte=one_month_ago,
        can_rate_coupons=False,
        is_active=True,
        is_delete=False,
    )

    updated_count = 0
    for user in eligible_by_age:
        total_amount = Transaction.objects.filter(
            user=user,
            type_trans="deposit",
            status="accept",
        ).aggregate(total=Sum('amount'))['total'] or 0

        if total_amount >= 15000:
            user.can_rate_coupons = True
            user.save(update_fields=['can_rate_coupons'])
            updated_count += 1

    return updated_count


@shared_task
def expire_coupons():
    """
    Marque les coupons expirés (date_expiration dépassée).
    Planifié toutes les 30 minutes.
    """
    from mobcash_inte.models import CouponV2
    
    now = timezone.now()
    expired_count = CouponV2.objects.filter(
        date_expiration__lt=now,
        is_expired=False,
        status='published'
    ).update(is_expired=True)
    
    return expired_count


@shared_task
def grant_daily_user_credits():
    """
    Accorde les crédits quotidiens aux utilisateurs actifs.
    Planifié chaque nuit à 00h00.
    """
    from accounts.models import User
    from mobcash_inte.models import UserCredit
    
    active_users = User.objects.filter(
        is_active=True,
        is_delete=False
    )
    
    created_count = 0
    for user in active_users:
        # Vérifier si l'utilisateur a déjà reçu ses crédits aujourd'hui
        today = timezone.now().date()
        existing_credit = UserCredit.objects.filter(
            user=user,
            granted_at__date=today
        ).exists()
        
        if not existing_credit:
            UserCredit.objects.create(
                user=user,
                credits_remaining=3,
                credits_used=0
            )
            created_count += 1
    
    return created_count


def finalize_betmomo_transaction(txn) -> str:
    """
    Vérifie le statut BetMomo d'une transaction et met à jour si final.
    Retourne: skipped | pending | success | failed | error
    """
    from django.utils import timezone as dj_tz

    from integrations.betmomo.service import BetMomoService
    from mobcash_inte.helpers import get_betmomo_token, uses_betmomo

    if not txn or not uses_betmomo(txn.app):
        return "skipped"
    # pending = retrait BetMomo réussi côté API mais planté avant init_payment
    # (ex: montant négatif sur PositiveIntegerField)
    if txn.status not in ("init_payment", "pending"):
        return "skipped"
    if not txn.betmomo_operation_ref:
        return "skipped"
    # Déjà validé côté betting + payout déjà lancé
    if txn.type_trans == "withdrawal" and txn.validated_at and txn.public_id:
        return "skipped"

    token = get_betmomo_token(txn.app)
    if not token:
        return "skipped"

    op_type = "WITHDRAWAL" if txn.type_trans == "withdrawal" else "DEPOSIT"
    try:
        service = BetMomoService(token=token)
        details = service.get_transaction_details(txn.betmomo_operation_ref, op_type)
        op_status = (details or {}).get("status") or ""
    except Exception as exc:
        logger.warning(
            "[BETMOMO] [FINALIZE] Erreur statut txn=%s: %s",
            txn.id,
            exc,
        )
        return "error"

    # Si l'API status ne répond pas mais la réponse initiale était déjà success
    if not op_status or op_status == "pending":
        raw = str(txn.mobcash_response or "")
        if '"Success": True' in raw or "'Success': True" in raw:
            if '"Pending": False' in raw or "'Pending': False" in raw:
                op_status = "success"
                details = details or {"status": "success", "reference": txn.betmomo_operation_ref}
            else:
                return "pending"
        else:
            return "pending"

    if op_status == "failed":
        txn.change_status(
            new_status="error",
            source="API_RESPONSE",
            data=details,
            message="Opération BetMomo échouée",
        )
        try:
            from payment import process_transaction_notifications_and_bonus

            process_transaction_notifications_and_bonus.delay(
                transaction_id=txn.id,
                is_error=True,
                error_message="Opération BetMomo échouée",
            )
        except Exception:
            logger.exception("[BETMOMO] [FINALIZE] notification erreur txn=%s", txn.id)
        return "failed"

    if op_status != "success":
        return "pending"

    if txn.type_trans == "withdrawal":
        # Si déjà validé mais payout Connect jamais lancé → relancer le paiement
        if txn.validated_at and not txn.public_id:
            try:
                from payment import connect_pro_withd_process

                txn.amount = abs(float(txn.amount or 0))
                txn.save(update_fields=["amount"])
                connect_pro_withd_process(txn, disbursements=True)
            except Exception:
                logger.exception(
                    "[BETMOMO] [FINALIZE] retry payout txn=%s", txn.id
                )
            return "success"
        if txn.validated_at:
            return "skipped"
        amount = BetMomoService.withdrawal_amount_from_details(details, {})
        extra_fields = []
        if amount:
            txn.amount = abs(float(amount))
            extra_fields.append("amount")
        else:
            txn.amount = abs(float(txn.amount or 0))
            extra_fields.append("amount")
        txn.change_status(
            new_status="init_payment",
            source="API_RESPONSE",
            data=details,
            message="Retrait BetMomo confirmé, paiement en cours",
            extra_fields=extra_fields,
        )
        txn.validated_at = dj_tz.now()
        txn.save(update_fields=["validated_at", "amount"])
        try:
            from payment import connect_pro_withd_process

            connect_pro_withd_process(txn, disbursements=True)
        except Exception:
            logger.exception("[BETMOMO] [FINALIZE] paiement retrait txn=%s", txn.id)
        return "success"

    if txn.status == "accept":
        return "skipped"

    txn.validated_at = dj_tz.now()
    txn.change_status(
        new_status="accept",
        source="API_RESPONSE",
        data=details,
        message="Dépôt BetMomo confirmé",
        extra_fields=["validated_at"],
    )
    if txn.type_trans == "reward":
        from mobcash_inte.models import Bonus

        Bonus.objects.filter(
            user=txn.user, bonus_with=False, bonus_delete=False
        ).update(bonus_with=True)
    try:
        from payment import (
            check_solde,
            process_transaction_notifications_and_bonus,
        )

        process_transaction_notifications_and_bonus.delay(transaction_id=txn.id)
        check_solde.delay(transaction_id=txn.id)
    except Exception:
        logger.exception("[BETMOMO] [FINALIZE] post-success txn=%s", txn.id)
    return "success"


def schedule_betmomo_status_check(transaction_id) -> None:
    """Planifie le check statut BetMomo (sleep 10s dans la tâche Celery)."""
    try:
        from django.db import transaction as db_transaction

        db_transaction.on_commit(
            lambda: check_betmomo_transaction_status.delay(transaction_id)
        )
    except Exception:
        logger.exception(
            "[BETMOMO] Impossible de planifier check statut txn=%s",
            transaction_id,
        )
        try:
            check_betmomo_transaction_status.delay(transaction_id)
        except Exception:
            logger.exception(
                "[BETMOMO] Fallback delay échoué txn=%s", transaction_id
            )


@shared_task
def check_betmomo_transaction_status(transaction_id, attempt=1, max_attempts=3):
    """
    Après dépôt/retrait BetMomo pending :
    sleep 10s puis vérifie le statut. Si encore pending, retente (max 3).
    """
    from mobcash_inte.models import Transaction

    logger.info(
        "[BETMOMO] [CHECK] Attente 10s avant check txn=%s attempt=%s",
        transaction_id,
        attempt,
    )
    time.sleep(10)

    txn = (
        Transaction.objects.filter(id=transaction_id)
        .select_related("app", "user")
        .first()
    )
    if not txn:
        logger.warning("[BETMOMO] [CHECK] Transaction introuvable id=%s", transaction_id)
        return "missing"

    result = finalize_betmomo_transaction(txn)
    logger.info(
        "[BETMOMO] [CHECK] txn=%s result=%s attempt=%s",
        transaction_id,
        result,
        attempt,
    )

    if result == "pending" and attempt < max_attempts:
        check_betmomo_transaction_status.delay(
            transaction_id, attempt=attempt + 1, max_attempts=max_attempts
        )

    return result


@shared_task
def poll_betmomo_pending_transactions():
    """
    Filet de sécurité : vérifie les ops BetMomo encore en init_payment.
    Planifié toutes les 30 secondes.
    """
    from datetime import timedelta
    from django.utils import timezone as dj_tz

    from mobcash_inte.helpers import uses_betmomo
    from mobcash_inte.models import Transaction

    threshold = dj_tz.now() - timedelta(hours=6)
    transactions = (
        Transaction.objects.filter(
            status__in=["init_payment", "pending"],
            betmomo_operation_ref__isnull=False,
            created_at__gte=threshold,
        )
        .exclude(betmomo_operation_ref="")
        .select_related("app", "user", "network")
    )

    processed = 0
    for txn in transactions:
        if not uses_betmomo(txn.app):
            continue
        result = finalize_betmomo_transaction(txn)
        if result in ("success", "failed"):
            processed += 1

    return processed
