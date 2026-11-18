"""Fixture dùng chung.

Test tích hợp (`tests/integration`) cần PostgreSQL / Neo4j / Elasticsearch. Không có dịch vụ thì
test bị skip – trừ khi biến REQUIRE_SERVICES liệt kê dịch vụ đó (vd CI: "postgres,neo4j"), khi đó
test FAIL để không bị xanh giả.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from app.core.config import get_settings


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Đặt biến môi trường cho Settings trong một test; tự xóa cache trước / sau."""
    get_settings.cache_clear()
    yield monkeypatch
    monkeypatch.undo()
    get_settings.cache_clear()


def required_services() -> set[str]:
    return {s.strip() for s in os.environ.get("REQUIRE_SERVICES", "").split(",") if s.strip()}


def skip_or_fail(service: str, reason: str) -> None:
    if service in required_services():
        pytest.fail(f"{service} bắt buộc (REQUIRE_SERVICES) nhưng không dùng được: {reason}")
    pytest.skip(f"{service} không chạy: {reason}")
