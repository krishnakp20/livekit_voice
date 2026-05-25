from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "vbots",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
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
        "process-campaign-dials": {
            "task": "app.tasks.campaign_tasks.process_scheduled_campaigns",
            "schedule": crontab(minute="*/5"),
        },
    },
)

celery_app.autodiscover_tasks(["app.tasks"])
