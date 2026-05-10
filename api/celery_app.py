# api/celery_app.py
from celery import Celery
from celery.schedules import crontab

app = Celery(
    'intelliops',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1',
    include=['api.tasks'],
)

app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='Asia/Kolkata',
    enable_utc=True,
)

app.conf.beat_schedule = {
    'forecast-check-every-5-min': {
        'task': 'run_forecast_check',
        'schedule': 300.0,
    },
    'retrain-weekly': {
        'task': 'retrain_models',
        'schedule': crontab(hour=2, minute=0, day_of_week=0),
    },
}
