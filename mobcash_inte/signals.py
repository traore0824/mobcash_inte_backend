from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import User


@receiver(post_save, sender=User)
def create_user_coupon_wallet(sender, instance, created, **kwargs):
    """Crée automatiquement un CouponWallet pour chaque nouvel utilisateur."""
    if created:
        from mobcash_inte.models import CouponWallet
        CouponWallet.objects.get_or_create(user=instance)
