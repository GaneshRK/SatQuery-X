"""Celery application configuration for asynchronous inference jobs."""

from __future__ import annotations

import os

from backend.config import get_settings

try:
    from celery import Celery

    settings = get_settings()
    celery_app = Celery(
        "satquery_jobs",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["backend.jobs.tasks"],
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
    )
except ImportError:
    celery_app = None
