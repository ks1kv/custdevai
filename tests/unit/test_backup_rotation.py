"""Unit-тест ротации backup-копий (FR-DB-08, NFR-REL-03).

Сама команда pg_dump в unit-тестах не запускается (нужен реальный
Postgres). Проверяем только логику ротации `_rotate()`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.worker.tasks.backup import _rotate, _to_libpq_url


@pytest.fixture()
def backup_dir(tmp_path: Path) -> Path:
    d = tmp_path / "backups"
    d.mkdir()
    return d


def _touch(p: Path) -> Path:
    p.write_bytes(b"\x00" * 100)
    return p


class TestRotateRetention:
    def test_keeps_n_newest(self, backup_dir: Path) -> None:
        # Создаём 10 dump-файлов с разными метками времени в имени.
        for ts in [
            "20260501-030000",
            "20260502-030000",
            "20260503-030000",
            "20260504-030000",
            "20260505-030000",
            "20260506-030000",
            "20260507-030000",
            "20260508-030000",
            "20260509-030000",
            "20260510-030000",
        ]:
            _touch(backup_dir / f"custdevai-{ts}.dump")

        removed = _rotate(backup_dir, keep=7)
        remaining = sorted(p.name for p in backup_dir.glob("custdevai-*.dump"))

        assert removed == 3
        assert len(remaining) == 7
        # Удалены три самые старые.
        assert "custdevai-20260501-030000.dump" not in remaining
        assert "custdevai-20260502-030000.dump" not in remaining
        assert "custdevai-20260503-030000.dump" not in remaining
        # Семь самых свежих сохранились.
        assert "custdevai-20260510-030000.dump" in remaining

    def test_no_op_when_below_limit(self, backup_dir: Path) -> None:
        _touch(backup_dir / "custdevai-20260510-030000.dump")
        _touch(backup_dir / "custdevai-20260511-030000.dump")
        removed = _rotate(backup_dir, keep=7)
        assert removed == 0
        assert len(list(backup_dir.glob("custdevai-*.dump"))) == 2

    def test_ignores_non_dump_files(self, backup_dir: Path) -> None:
        # Файлы, не подходящие под паттерн, не удаляются и не считаются.
        _touch(backup_dir / "custdevai-20260510-030000.dump")
        _touch(backup_dir / "random.txt")
        _touch(backup_dir / "old_backup.dump")  # отсутствует префикс custdevai-
        removed = _rotate(backup_dir, keep=1)
        assert removed == 0
        assert (backup_dir / "random.txt").exists()
        assert (backup_dir / "old_backup.dump").exists()


class TestLibpqUrl:
    def test_strips_asyncpg_driver(self) -> None:
        assert (
            _to_libpq_url("postgresql+asyncpg://custdev:pwd@postgres:5432/custdevai")
            == "postgresql://custdev:pwd@postgres:5432/custdevai"
        )

    def test_passes_through_libpq(self) -> None:
        assert _to_libpq_url("postgresql://u:p@host/db") == "postgresql://u:p@host/db"

    def test_normalizes_postgres_scheme(self) -> None:
        assert _to_libpq_url("postgres://u:p@host/db") == "postgresql://u:p@host/db"
