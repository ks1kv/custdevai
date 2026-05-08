"""Абстрактный StorageBackend и реализация LocalFileSystemBackend (FR-RPT-08).

NFR-MNT-03: backend подменяется в Phase 5 на S3StorageBackend (Selectel
Object Storage) без изменения ReportService / generators. Локальная
реализация — для Phase 4 + dev/единичный production-узел.
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

from apps.api.config import Settings


@dataclass(frozen=True)
class StoragePutResult:
    """Что вернёт `put()` после успешной записи."""

    file_path: str       # абстрактный ключ внутри backend (для S3 — object key)
    file_size: int
    sha256: bytes


@dataclass(frozen=True)
class StorageObject:
    """Что вернёт `get()` для чтения файла отчёта."""

    file_path: str
    content: bytes
    content_type: str


class StorageBackend(abc.ABC):
    """Контракт хранилища. Подменяется в Phase 5 на S3-реализацию."""

    @abc.abstractmethod
    async def put(self, key: str, data: bytes, *, content_type: str) -> StoragePutResult:
        """Сохранить байты под ключом. Возвращает file_path/size/sha256."""

    @abc.abstractmethod
    async def get(self, key: str) -> StorageObject:
        """Прочитать сохранённые байты по ключу."""

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Удалить файл. Idempotent: отсутствующий ключ — без ошибки."""


class LocalFileSystemBackend(StorageBackend):
    """Сохранение в локальный каталог (`settings.reports_storage_dir`).

    Phase 4 default: `/var/lib/custdevai/reports` (см. docker-compose
    volume `reports_storage`). В dev можно переопределить через ENV.

    Файлы пишутся атомарно через tempfile + os.replace, чтобы
    параллельная генерация не давала частичных файлов.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Защита от path traversal: ключ нормализуется и должен оставаться
        # внутри base_dir. ".." и абсолютные пути отбрасываются.
        candidate = (self._base / key).resolve()
        if self._base not in candidate.parents and candidate != self._base:
            raise ValueError(f"Недопустимый storage-key: {key!r}")
        return candidate

    async def put(self, key: str, data: bytes, *, content_type: str) -> StoragePutResult:
        target = self._resolve(key)
        return await asyncio.to_thread(self._write_blocking, target, key, data)

    @staticmethod
    def _write_blocking(target: Path, key: str, data: bytes) -> StoragePutResult:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Атомарная запись: tmp в той же папке + os.replace.
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        return StoragePutResult(
            file_path=key,
            file_size=len(data),
            sha256=hashlib.sha256(data).digest(),
        )

    async def get(self, key: str) -> StorageObject:
        target = self._resolve(key)
        if not target.is_file():
            raise FileNotFoundError(key)
        content = await asyncio.to_thread(target.read_bytes)
        ext = target.suffix.lower().lstrip(".")
        content_type = {
            "pdf": "application/pdf",
            "xlsx": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        }.get(ext, "application/octet-stream")
        return StorageObject(file_path=key, content=content, content_type=content_type)

    async def delete(self, key: str) -> None:
        target = self._resolve(key)
        if target.is_file():
            await asyncio.to_thread(target.unlink)


def get_storage_backend(settings: Settings) -> StorageBackend:
    """Фабрика backend-а согласно настройкам.

    Phase 4 — единственный backend (LocalFileSystemBackend). Phase 5
    добавит ветку для S3 на основе settings.selectel_*.
    """
    return LocalFileSystemBackend(settings.reports_storage_dir)
