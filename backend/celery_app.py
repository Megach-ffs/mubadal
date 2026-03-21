"""
Celery application configuration.
"""
import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery = Celery(
    "mubadal",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,  # results expire after 1 hour
    worker_max_tasks_per_child=50,  # restart worker after 50 tasks to free memory
    worker_prefetch_multiplier=1,   # one task at a time per worker for heavy conversions
)
