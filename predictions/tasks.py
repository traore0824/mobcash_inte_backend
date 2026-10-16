import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="predictions.tasks.run_daily_pipeline", queue="predictions")
def run_daily_pipeline_task(self):
    from predictions.models import PredictionSettings
    from predictions.services.pipeline import run_daily_pipeline

    if PredictionSettings.get_solo().kill_switch:
        logger.info("Kill switch actif — daily pipeline ignoré")
        return {"skipped": True}

    result = run_daily_pipeline()
    logger.info("Daily predictions pipeline: %s", result)
    return result


@shared_task(bind=True, name="predictions.tasks.run_update_pipeline", queue="predictions")
def run_update_pipeline_task(self):
    from predictions.models import PredictionSettings
    from predictions.services.pipeline import run_update_pipeline

    if PredictionSettings.get_solo().kill_switch:
        logger.info("Kill switch actif — update pipeline ignoré")
        return {"skipped": True}

    result = run_update_pipeline()
    logger.info("Update predictions pipeline: %s", result)
    return result


@shared_task(bind=True, name="predictions.tasks.train_models", queue="predictions")
def train_models_task(self):
    from predictions.services.pipeline import train_all_domestic_models

    result = train_all_domestic_models()
    logger.info("Train models: %s", result)
    return result
