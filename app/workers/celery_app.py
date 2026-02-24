"""Celery application configuration."""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "ai_academic_os",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.generation_tasks",
        "app.workers.tasks.report_tasks",
        "app.workers.tasks.cleanup_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_soft_time_limit=settings.COURSE_GENERATION_TIMEOUT,
    task_time_limit=settings.COURSE_GENERATION_TIMEOUT + 60,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_routes={
        "app.workers.tasks.generation_tasks.*": {"queue": "generation"},
        "app.workers.tasks.report_tasks.*": {"queue": "reports"},
        "app.workers.tasks.cleanup_tasks.*": {"queue": "cleanup"},
    },
)