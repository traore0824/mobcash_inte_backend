from celery import shared_task
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.db.models import Sum
import logging

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
    Protégé par select_for_update pour éviter check+poll en parallèle
    (double notif dépôt / double payout Connect retrait).
    """
    from django.db import transaction as db_transaction
    from django.utils import timezone as dj_tz

    from integrations.betmomo.service import BetMomoService
    from mobcash_inte.helpers import get_betmomo_token, uses_betmomo
    from mobcash_inte.models import Transaction

    if not txn or not uses_betmomo(txn.app):
        return "skipped"

    txn_id = txn.id
    token = get_betmomo_token(txn.app)
    if not token:
        return "skipped"

    # Snapshot hors lock (appel HTTP ne doit pas bloquer la row longtemps)
    op_type = "WITHDRAWAL" if txn.type_trans == "withdrawal" else "DEPOSIT"
    operation_ref = txn.betmomo_operation_ref
    if not operation_ref:
        logger.warning(
            "[BETMOMO] [FINALIZE] txn=%s sans betmomo_operation_ref — skip",
            txn_id,
        )
        return "skipped"

    try:
        service = BetMomoService(token=token)
        details = service.get_transaction_details(
            operation_ref,
            op_type,
            mobcash_response=getattr(txn, "mobcash_response", None),
        )
        op_status = (details or {}).get("status") or ""
        logger.info(
            "[BETMOMO] [FINALIZE] txn=%s ref=%s api_status=%r queried=%s",
            txn_id,
            operation_ref,
            op_status,
            (details or {}).get("queried_ref"),
        )
    except Exception as exc:
        logger.warning(
            "[BETMOMO] [FINALIZE] Erreur statut txn=%s: %s",
            txn_id,
            exc,
        )
        return "error"

    if details is None:
        logger.warning(
            "[BETMOMO] [FINALIZE] txn=%s status API indisponible — retry plus tard",
            txn_id,
        )
        return "error"

    if not op_status or op_status == "pending":
        raw = str(txn.mobcash_response or "")
        if '"Success": True' in raw or "'Success': True" in raw:
            if '"Pending": False' in raw or "'Pending': False" in raw:
                op_status = "success"
                details = details or {
                    "status": "success",
                    "reference": operation_ref,
                }
            else:
                return "pending"
        else:
            return "pending"

    if op_status not in ("success", "failed"):
        return "pending"

    safe_data = {
        "status": (details or {}).get("status"),
        "reference": (details or {}).get("reference") or operation_ref,
        "amount": (details or {}).get("amount"),
        "queried_ref": (details or {}).get("queried_ref"),
    }

    try:
        with db_transaction.atomic():
            locked = (
                Transaction.objects.select_for_update(of=("self",))
                .select_related("app", "user", "network")
                .filter(id=txn_id)
                .first()
            )
            if not locked or not uses_betmomo(locked.app):
                return "skipped"
            if locked.status not in ("init_payment", "pending"):
                logger.info(
                    "[BETMOMO] [FINALIZE] txn=%s skip status=%s",
                    txn_id,
                    locked.status,
                )
                return "skipped"
            if locked.type_trans == "withdrawal" and locked.validated_at and locked.public_id:
                return "skipped"

            if op_status == "failed":
                locked.change_status(
                    new_status="error",
                    source="API_RESPONSE",
                    data=safe_data,
                    message="Opération BetMomo échouée",
                )
                try:
                    from payment import process_transaction_notifications_and_bonus

                    process_transaction_notifications_and_bonus.delay(
                        transaction_id=locked.id,
                        is_error=True,
                        error_message="Opération BetMomo échouée",
                    )
                except Exception:
                    logger.exception(
                        "[BETMOMO] [FINALIZE] notification erreur txn=%s", locked.id
                    )
                return "failed"

            if locked.type_trans == "withdrawal":
                if locked.validated_at and not locked.public_id:
                    try:
                        from payment import connect_pro_withd_process

                        locked.amount = abs(float(locked.amount or 0))
                        locked.save(update_fields=["amount"])
                        connect_pro_withd_process(locked, disbursements=True)
                    except Exception:
                        logger.exception(
                            "[BETMOMO] [FINALIZE] retry payout txn=%s", locked.id
                        )
                    return "success"
                if locked.validated_at:
                    return "skipped"

                amount = BetMomoService.withdrawal_amount_from_details(details, {})
                if amount:
                    locked.amount = abs(float(amount))
                else:
                    locked.amount = abs(float(locked.amount or 0))
                locked.validated_at = dj_tz.now()
                locked.change_status(
                    new_status="init_payment",
                    source="API_RESPONSE",
                    data=safe_data,
                    message="Retrait BetMomo confirmé, paiement en cours",
                    extra_fields=["amount", "validated_at"],
                )
                try:
                    from payment import connect_pro_withd_process

                    connect_pro_withd_process(locked, disbursements=True)
                except Exception:
                    logger.exception(
                        "[BETMOMO] [FINALIZE] paiement retrait txn=%s", locked.id
                    )
                return "success"

            if locked.status == "accept":
                return "skipped"

            locked.validated_at = dj_tz.now()
            locked.change_status(
                new_status="accept",
                source="API_RESPONSE",
                data=safe_data,
                message="Dépôt BetMomo confirmé",
                extra_fields=["validated_at"],
            )
            logger.info("[BETMOMO] [FINALIZE] txn=%s passé en accept", locked.id)
            if locked.type_trans == "reward":
                from mobcash_inte.models import Bonus

                Bonus.objects.filter(
                    user=locked.user, bonus_with=False, bonus_delete=False
                ).update(bonus_with=True)
            try:
                from payment import (
                    check_solde,
                    process_transaction_notifications_and_bonus,
                )

                process_transaction_notifications_and_bonus.delay(
                    transaction_id=locked.id
                )
                check_solde.delay(transaction_id=locked.id)
            except Exception:
                logger.exception(
                    "[BETMOMO] [FINALIZE] post-success txn=%s", locked.id
                )
            return "success"
    except Exception:
        logger.exception(
            "[BETMOMO] [FINALIZE] ÉCHEC update DB txn=%s api_status=%s",
            txn_id,
            op_status,
        )
        return "error"


def schedule_betmomo_status_check(transaction_id, *, countdown: int = 10) -> None:
    """
    Planifie le check statut BetMomo après commit DB.
    Nécessite un worker Celery actif — sinon la txn reste en init_payment.
    """
    from django.db import connection, transaction as db_transaction

    def _enqueue():
        try:
            async_result = check_betmomo_transaction_status.apply_async(
                args=[transaction_id],
                kwargs={"attempt": 1, "max_attempts": 6},
                countdown=max(0, int(countdown)),
            )
            logger.info(
                "[BETMOMO] [SCHEDULE] check planifié txn=%s countdown=%ss task_id=%s",
                transaction_id,
                countdown,
                getattr(async_result, "id", None),
            )
        except Exception:
            logger.exception(
                "[BETMOMO] [SCHEDULE] échec enqueue txn=%s", transaction_id
            )

    try:
        if connection.in_atomic_block:
            db_transaction.on_commit(_enqueue)
            logger.info(
                "[BETMOMO] [SCHEDULE] on_commit enregistré txn=%s", transaction_id
            )
        else:
            _enqueue()
    except Exception:
        logger.exception(
            "[BETMOMO] Impossible de planifier check statut txn=%s",
            transaction_id,
        )
        _enqueue()


@shared_task(bind=True, max_retries=0)
def check_betmomo_transaction_status(self, transaction_id, attempt=1, max_attempts=6):
    """
    Après dépôt/retrait BetMomo pending : vérifie le statut.
    Si encore pending, retente avec countdown 10s (max_attempts).
    """
    from mobcash_inte.models import Transaction

    logger.info(
        "[BETMOMO] [CHECK] txn=%s attempt=%s/%s",
        transaction_id,
        attempt,
        max_attempts,
    )

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

    if result in ("pending", "error") and attempt < max_attempts:
        check_betmomo_transaction_status.apply_async(
            args=[transaction_id],
            kwargs={"attempt": attempt + 1, "max_attempts": max_attempts},
            countdown=10,
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
    pending_count = 0
    for txn in transactions:
        if not uses_betmomo(txn.app):
            continue
        pending_count += 1
        result = finalize_betmomo_transaction(txn)
        logger.info(
            "[BETMOMO] [POLL] txn=%s ref=%s status=%s result=%s",
            txn.id,
            txn.betmomo_operation_ref,
            txn.status,
            result,
        )
        if result in ("success", "failed"):
            processed += 1

    logger.info(
        "[BETMOMO] [POLL] terminé: %s en file, %s finalisées",
        pending_count,
        processed,
    )
    return processed
