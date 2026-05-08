"""Unit-тесты LocalFileSystemBackend (FR-RPT-08, NFR-MNT-03)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from apps.api.reports.storage import (
    LocalFileSystemBackend,
    StorageBackend,
    StoragePutResult,
)


@pytest.fixture()
def backend(tmp_path: Path) -> LocalFileSystemBackend:
    return LocalFileSystemBackend(tmp_path / "reports")


class TestLocalFileSystemBackend:
    def test_implements_abstract_contract(self, backend: LocalFileSystemBackend) -> None:
        # NFR-MNT-03: должен подменяться через интерфейс ABC.
        assert isinstance(backend, StorageBackend)

    @pytest.mark.asyncio
    async def test_put_returns_size_and_sha256(self, backend: LocalFileSystemBackend) -> None:
        data = b"\x25PDF-1.4 ..."
        result = await backend.put("c/1/file.pdf", data, content_type="application/pdf")

        assert isinstance(result, StoragePutResult)
        assert result.file_size == len(data)
        assert result.sha256 == hashlib.sha256(data).digest()
        assert result.file_path == "c/1/file.pdf"

    @pytest.mark.asyncio
    async def test_get_round_trips(self, backend: LocalFileSystemBackend) -> None:
        data = b"hello world"
        await backend.put("a.pdf", data, content_type="application/pdf")
        obj = await backend.get("a.pdf")
        assert obj.content == data
        assert obj.content_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_get_xlsx_content_type(self, backend: LocalFileSystemBackend) -> None:
        await backend.put("a.xlsx", b"PK\x03\x04...", content_type="x")
        obj = await backend.get("a.xlsx")
        assert obj.content_type.endswith("spreadsheetml.sheet")

    @pytest.mark.asyncio
    async def test_get_missing_raises(self, backend: LocalFileSystemBackend) -> None:
        with pytest.raises(FileNotFoundError):
            await backend.get("missing.pdf")

    @pytest.mark.asyncio
    async def test_delete_is_idempotent(self, backend: LocalFileSystemBackend) -> None:
        await backend.put("z.pdf", b"x", content_type="application/pdf")
        await backend.delete("z.pdf")
        # Повторный delete не должен падать.
        await backend.delete("z.pdf")

    @pytest.mark.asyncio
    async def test_rejects_path_traversal(self, backend: LocalFileSystemBackend) -> None:
        with pytest.raises(ValueError):
            await backend.put("../etc/passwd", b"x", content_type="application/octet-stream")

    @pytest.mark.asyncio
    async def test_atomic_write_no_partial_file(
        self, backend: LocalFileSystemBackend, tmp_path: Path
    ) -> None:
        # После успешного put ровно один файл, без .tmp-хвоста.
        await backend.put("nested/deep/file.pdf", b"data", content_type="application/pdf")
        files = sorted(p.name for p in (tmp_path / "reports" / "nested" / "deep").iterdir())
        assert files == ["file.pdf"]
