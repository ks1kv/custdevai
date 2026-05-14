"""Ежедневный pg_dump БД + ротация 7 копий (FR-DB-08, NFR-REL-03/05/06).

Celery beat (см. apps/worker/celery_app.py) запускает task `backup.database`
ежедневно в 03:00 UTC. Файл `custdevai-YYYYMMDD-HHMMSS.dump` пишется в
BACKUP_STORAGE_DIR (volume `backups_storage` в docker-compose). Старше
BACKUP_RETENTION_COUNT копий — удаляются.

Восстановление описано в docs/DISASTER_RECOVERY.md. Целевые показатели:
- NFR-REL-03: ≥ 1 копия / сутки, глубина 7 копий ✓
- NFR-REL-05: RTO ≤ 60 минут — проверяется на тестовом инстансе ✓
- NFR-REL-06: RPO ≤ 24 часа — обеспечивается расписанием ✓
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from apps.api.config import Settings, get_settings
from apps.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="backup.database", bind=True, max_retries=2, default_retry_delay=300)
def backup_database(self) -> dict:
    """Снять pg_dump -Fc и сохранить в BACKUP_STORAGE_DIR.

    Возвращает метаданные созданного файла. Падение pg_dump — Celery retry
    с задержкой 5 минут (≤ 2 раза); после исчерпания таск падает, и
    отсутствие свежей копии будет видно в logs/monitoring.
    """
    settings = get_settings()
    try:
        return _perform_backup(settings)
    except subprocess.CalledProcessError as exc:
        logger.exception("pg_dump_failed", extra={"returncode": exc.returncode})
        raise self.retry(exc=exc) from exc


def _perform_backup(settings: Settings) -> dict:
    backup_dir = Path(settings.backup_storage_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"custdevai-{ts}.dump"

    pg_url = _to_libpq_url(settings.effective_database_url)
    # -Fc — custom format, поддерживает pg_restore -j.
    # --no-owner / --no-privileges — переносимо между окружениями.
    cmd = [
        "pg_dump",
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "--dbname",
        pg_url,
        "--file",
        str(target),
    ]
    # cmd состоит из литералов + читаемой нами Settings.backup_storage_dir
    # + URL подключения из ENV — никаких пользовательских входов нет.
    subprocess.run(cmd, check=True, capture_output=True)  # noqa: S603

    size = target.stat().st_size
    digest = _sha256_of_file(target)
    removed = _rotate(backup_dir, keep=settings.backup_retention_count)

    payload = {
        "file": target.name,
        "path": str(target),
        "size": size,
        "sha256": digest.hex(),
        "rotated_removed": removed,
        "created_at": ts,
    }
    logger.info("database_backup_created", extra=payload)
    return payload


def _to_libpq_url(async_url: str) -> str:
    """`postgresql+asyncpg://...` → `postgresql://...` для pg_dump."""
    parsed = urlparse(async_url)
    scheme = parsed.scheme.split("+", 1)[0] or "postgresql"
    if scheme == "postgres":
        scheme = "postgresql"
    return parsed._replace(scheme=scheme).geturl()


def _sha256_of_file(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def _rotate(backup_dir: Path, *, keep: int) -> int:
    """Оставить только `keep` самых свежих dump-файлов. Возвращает число удалённых."""
    dumps = sorted(
        backup_dir.glob("custdevai-*.dump"),
        key=lambda p: p.name,
        reverse=True,
    )
    removed = 0
    for old in dumps[keep:]:
        try:
            old.unlink()
            removed += 1
        except OSError as exc:
            logger.warning("backup_rotate_failed", extra={"path": str(old), "error": str(exc)})
    return removed
