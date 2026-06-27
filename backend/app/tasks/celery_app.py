from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "vbots",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    # Explicitly import the task modules so @celery_app.task registers them.
    # autodiscover_tasks(["app.tasks"]) only looks for app/tasks/tasks.py (which
    # doesn't exist) — our tasks live in campaign_tasks.py / whatsapp_tasks.py,
    # so without this the worker registers ZERO tasks and discards every dial job.
    include=["app.tasks.campaign_tasks", "app.tasks.whatsapp_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule={
        "daily-whatsapp-report": {
            "task": "app.tasks.whatsapp_tasks.send_daily_reports",
            "schedule": crontab(hour=9, minute=0),
        },
        # Auto-dialer: top up RUNNING campaigns to their dial_rate every 20s.
        # Concurrency-aware (dial_campaign_leads only dials dial_rate - in_flight),
        # so this keeps the pipeline full and auto-completes when leads run out.
        "process-campaign-dials": {
            "task": "app.tasks.campaign_tasks.process_scheduled_campaigns",
            "schedule": 20.0,
        },
    },
)

celery_app.autodiscover_tasks(["app.tasks"])
