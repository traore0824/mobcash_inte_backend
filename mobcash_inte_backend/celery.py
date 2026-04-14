from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mobcash_inte_backend.settings")

app = Celery("mobcash_inte_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.broker_connection_retry_on_startup = True

app.conf.beat_schedule = {
    'grant-coupon-publishing-permissions': {
        'task': 'mobcash_inte.tasks.grant_coupon_publishing_permissions',
        'schedule': crontab(hour=0, minute=0),
    },
    'grant-coupon-rating-permissions': {
        'task': 'mobcash_inte.tasks.grant_coupon_rating_permissions',
        'schedule': crontab(hour=0, minute=0),
    },
    'expire-coupons': {
        'task': 'mobcash_inte.tasks.expire_coupons',
        'schedule': crontab(minute='*/30'),  # Toutes les 30 minutes
    },
    'grant-daily-user-credits': {
        'task': 'mobcash_inte.tasks.grant_daily_user_credits',
        'schedule': crontab(hour=0, minute=0),  # Tous les jours à minuit
    },
}
