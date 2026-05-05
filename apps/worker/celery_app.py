"""Минимальный Celery-инстанс. Задачи добавляются на Phase 3 (ML-модули)."""

from __future__ import annotations

import os

from celery import Celery

broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")

celery_app = Celery(
    "custdevai",
    broker=broker_url,
    backend=result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
