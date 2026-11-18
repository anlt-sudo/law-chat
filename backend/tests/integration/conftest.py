"""Fixture tích hợp: DB PostgreSQL riêng cho test (tạo nếu chưa có, migrate từ đầu mỗi phiên)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import command
from app.core.config import get_settings
from tests.conftest import skip_or_fail

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _test_db_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


async def _ensure_database(url: str) -> None:
    u = make_url(url)
    conn = await asyncpg.connect(
        host=u.host,
        port=u.port or 5432,
        user=u.username,
        password=u.password,
        database="postgres",
        timeout=3,
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", u.database)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{u.database}"')
    finally:
        await conn.close()


def _alembic(url: str, *revisions: str) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    for rev in revisions:
        if rev == "base":
            command.downgrade(cfg, "base")
        else:
            command.upgrade(cfg, rev)


@pytest.fixture(scope="session")
def pg_url() -> str:
    """URL DB test đã migrate sạch (downgrade base → upgrade head).

    Fixture sync để alembic tự chạy event loop riêng.
    """
    url = _test_db_url()
    try:
        asyncio.run(_ensure_database(url))
    except Exception as exc:
        skip_or_fail("postgres", f"{type(exc).__name__}: {exc}")
    _alembic(url, "base", "head")
    return url


@pytest.fixture(scope="session")
async def pg_engine(pg_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(pg_url, pool_size=10)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_jobs(pg_engine: AsyncEngine) -> AsyncEngine:
    async with pg_engine.begin() as conn:
        await conn.execute(text("TRUNCATE pipeline_job, pipeline_run"))
    return pg_engine
