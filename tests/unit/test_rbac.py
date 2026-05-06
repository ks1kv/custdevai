"""Unit-тесты RBAC (FR-AUTH-02, FR-AUTH-05)."""

from __future__ import annotations

import pytest

from apps.api.auth.rbac import Role, require
from apps.api.errors import PermissionDenied


def test_require_passes_when_user_has_role() -> None:
    require([Role.ADMIN], ["Admin"])
    require([Role.RESEARCHER, Role.ADMIN], ["Researcher"])


def test_require_blocks_when_user_lacks_role() -> None:
    with pytest.raises(PermissionDenied):
        require([Role.ADMIN], ["Researcher"])


def test_require_blocks_empty_roles() -> None:
    with pytest.raises(PermissionDenied):
        require([Role.ADMIN], [])
