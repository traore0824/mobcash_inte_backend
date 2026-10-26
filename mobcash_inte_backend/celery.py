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

# Note: le beat_schedule effectif est CELERY_BEAT_SCHEDULE dans settings.py
# (assigner app.conf.beat_schedule ici est ignoré une fois config_from_object chargé).
app.conf.task_routes = {
    **(getattr(app.conf, "task_routes", None) or {}),
    "predictions.tasks.*": {"queue": "predictions"},
}
