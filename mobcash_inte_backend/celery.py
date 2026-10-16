from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mobcash_inte_backend.settings")

app = Celery("mobcash_inte_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.broker_connection_retry_on_startup = True
app.conf.task_default_queue = "mobcash_inte"
app.conf.task_default_exchange = "mobcash_inte"
app.conf.task_default_routing_key = "mobcash_inte"

# Fusionner avec CELERY_BEAT_SCHEDULE (settings) — ne pas écraser le poll BetMomo/FeexPay
_extra_beat = {
    "grant-coupon-publishing-permissions": {
        "task": "mobcash_inte.tasks.grant_coupon_publishing_permissions",
        "schedule": crontab(hour=0, minute=0),
    },
    "grant-coupon-rating-permissions": {
        "task": "mobcash_inte.tasks.grant_coupon_rating_permissions",
        "schedule": crontab(hour=0, minute=0),
    },
    "expire-coupons": {
        "task": "mobcash_inte.tasks.expire_coupons",
        "schedule": crontab(minute="*/30"),
    },
    "grant-daily-user-credits": {
        "task": "mobcash_inte.tasks.grant_daily_user_credits",
        "schedule": crontab(hour=0, minute=0),
    },
    # Pronos IA — 01:00 UTC création du jour ; update toutes les 3 h
    "predictions-daily-pipeline": {
        "task": "predictions.tasks.run_daily_pipeline",
        "schedule": crontab(hour=1, minute=0),
        "options": {"queue": "predictions"},
    },
    "predictions-update-pipeline": {
        "task": "predictions.tasks.run_update_pipeline",
        "schedule": crontab(minute=0, hour="*/3"),
        "options": {"queue": "predictions"},
    },
}
app.conf.beat_schedule = {**(app.conf.beat_schedule or {}), **_extra_beat}
app.conf.task_routes = {
    **(getattr(app.conf, "task_routes", None) or {}),
    "predictions.tasks.*": {"queue": "predictions"},
}
