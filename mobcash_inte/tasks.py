from celery import shared_task
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.db.models import Sum


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
