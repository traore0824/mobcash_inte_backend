from celery import shared_task
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.db.models import Sum
import logging


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


@shared_task
def poll_betmomo_pending_transactions():
    """
    Vérifie le statut des opérations BetMomo encore en init_payment.
    Planifié toutes les 30 secondes.
    """
    from datetime import timedelta
    from django.utils import timezone as dj_tz

    from integrations.betmomo.service import BetMomoService
    from mobcash_inte.helpers import get_betmomo_token, uses_betmomo
    from mobcash_inte.models import Transaction

    logger = logging.getLogger("mobcash_inte_backend.transactions")
    threshold = dj_tz.now() - timedelta(hours=6)
    transactions = (
        Transaction.objects.filter(
            status="init_payment",
            betmomo_operation_ref__isnull=False,
            created_at__gte=threshold,
        )
        .exclude(betmomo_operation_ref="")
        .select_related("app", "user")
    )

    processed = 0
    for txn in transactions:
        if not uses_betmomo(txn.app):
            continue
        token = get_betmomo_token(txn.app)
        if not token:
            continue
        op_type = "WITHDRAWAL" if txn.type_trans == "withdrawal" else "DEPOSIT"
        try:
            service = BetMomoService(token=token)
            details = service.get_transaction_details(
                txn.betmomo_operation_ref, op_type
            )
            op_status = (details or {}).get("status") or ""
        except Exception as exc:
            logger.warning(
                "[BETMOMO] [POLL] Erreur statut txn=%s: %s",
                txn.id,
                exc,
            )
            continue

        if not op_status or op_status == "pending":
            continue

        processed += 1
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
                logger.exception("[BETMOMO] [POLL] notification erreur txn=%s", txn.id)
            continue

        if op_status != "success":
            continue

        if txn.type_trans == "withdrawal":
            if txn.validated_at:
                continue
            amount = BetMomoService.withdrawal_amount_from_details(details, {})
            extra_fields = []
            if amount:
                txn.amount = abs(float(amount))
                extra_fields.append("amount")
            txn.change_status(
                new_status="init_payment",
                source="API_RESPONSE",
                data=details,
                message="Retrait BetMomo confirmé, paiement en cours",
                extra_fields=extra_fields,
            )
            txn.validated_at = dj_tz.now()
            txn.save(update_fields=["validated_at"])
            try:
                from payment import connect_pro_withd_process

                connect_pro_withd_process(txn, disbursements=True)
            except Exception:
                logger.exception(
                    "[BETMOMO] [POLL] paiement retrait txn=%s", txn.id
                )
            continue

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
            logger.exception("[BETMOMO] [POLL] post-success txn=%s", txn.id)

    return processed
