"""Celery-инстанс CustDevAI + расписание периодических задач.

Periodic-задачи (Phase 5):
- backup.database — ежедневный pg_dump (FR-DB-08, NFR-REL-03/05/06).
- sessions.sweep_inactive — UPDATE active → interrupted каждые 15 мин (FR-BOT-05).

Для активации periodic-задач рядом с worker запускается celery beat
(см. docker-compose сервис `worker-beat`).
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

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
    imports=(
        "apps.worker.tasks.ml_pipeline",
        "apps.worker.tasks.backup",
        "apps.worker.tasks.sessions",
    ),
    # CELERY_TASK_ALWAYS_EAGER=True переключает eager-режим в тестах
    # (синхронное выполнение без брокера).
    task_always_eager=os.environ.get("CELERY_TASK_ALWAYS_EAGER", "").lower()
    in {"1", "true", "yes"},
    task_eager_propagates=True,
    # acks_late=True — задача подтверждается только после успешного
    # завершения. Если воркер убили SIGKILL (OOM), задача остаётся в
    # очереди и будет подхвачена другим воркером после рестарта.
    # Без этого падение воркера на CVE-2025-32434 в transformers роняло
    # таску без следа, и кампания залипала в RUNNING.
    task_acks_late=True,
    # Воркер забирает по 1 задаче за раз — без префетча, чтобы упавшая
    # ML-таска не утянула за собой соседние из буфера.
    worker_prefetch_multiplier=1,
    beat_schedule={
        # FR-DB-08 + NFR-REL-03: pg_dump раз в сутки в 03:00 UTC.
        "backup-database-daily": {
            "task": "backup.database",
            "schedule": crontab(hour=3, minute=0),
        },
        # FR-BOT-05: переводим зависшие active-сессии в interrupted каждые 15 минут.
        "sessions-sweeper": {
            "task": "sessions.sweep_inactive",
            "schedule": 900.0,
        },
        # FR-API-04: каждые 5 минут проверяем, нет ли «зависшего» RUNNING-
        # анализа (после OOM/SIGKILL воркера), переставляем такие в FAILED.
        "ml-sweep-stuck-running": {
            "task": "ml.sweep_stuck_running",
            "schedule": 300.0,
        },
    },
)
