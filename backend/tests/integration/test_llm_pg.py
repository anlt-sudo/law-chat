"""LLM Gateway với PostgreSQL thật: llm_call_log, runtime_flag, API /admin/llm/*."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import ClassVar

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.api_keys import hash_key
from app.core.auth import get_api_key_repo
from app.db.pg import get_session
from app.llm import set_gateway
from app.llm.busy_flag import PgBusyFlag, wait_until_idle
from app.llm.call_log import PgCallLogSink
from app.llm.gateway import LLMGateway
from app.main import create_app
from tests.mocks.lmstudio_mock import MockLMStudio, Script
from tests.unit.test_llm_gateway import MSG, Relation, make_settings

pytestmark = pytest.mark.integration


@pytest.fixture
async def clean_llm(pg_engine: AsyncEngine) -> AsyncEngine:
    async with pg_engine.begin() as conn:
        await conn.execute(text("TRUNCATE llm_call_log, runtime_flag"))
    return pg_engine


@pytest.fixture
async def pg_gateway(clean_llm: AsyncEngine) -> AsyncIterator[tuple[LLMGateway, MockLMStudio]]:
    mock = MockLMStudio()
    gw = LLMGateway(
        make_settings(),
        transport=mock.transport(),
        call_log=PgCallLogSink(clean_llm),
        busy_flag=PgBusyFlag(clean_llm, min_write_interval_s=0),
        retry_backoff_s=(0, 0),
    )
    yield gw, mock
    await gw.aclose()


async def test_call_log_written(pg_gateway, clean_llm: AsyncEngine) -> None:
    gw, mock = pg_gateway
    mock.script(
        Script(content="sai"),
        Script(content='{"loai": "BAI_BO", "dieu_khoan_dich": "K10"}'),
        Script(exc=httpx.ReadTimeout),
    )
    await gw.complete_json("extract_relations", MSG, Relation, caller_ref="relation_candidate:1")
    with pytest.raises(Exception):  # noqa: B017
        await gw.complete_text("chat_answer", MSG)
    await gw.call_log.flush()
    async with clean_llm.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT task, outcome, attempts, priority, reasoning_tokens, caller_ref, "
                    "prompt IS NOT NULL AS has_prompt FROM llm_call_log ORDER BY task DESC"
                )
            )
        ).all()
    # Ghi log bất đồng bộ → thứ tự id không cố định; sắp theo task
    assert [(r.task, r.outcome, r.attempts) for r in rows] == [
        ("extract_relations", "ok", 2),
        ("chat_answer", "timeout", 1),
    ]
    assert rows[0].caller_ref == "relation_candidate:1"
    assert rows[0].priority == 3 and rows[0].reasoning_tokens is not None
    assert rows[0].has_prompt  # LLM_LOG_CONTENT mặc định bật ở dev


async def test_pg_busy_flag_shared(pg_gateway, clean_llm: AsyncEngine) -> None:
    gw, _ = pg_gateway
    other_process = PgBusyFlag(clean_llm)  # như worker đọc cờ do API ghi
    assert await other_process.busy_until() is None
    await gw.complete_text("chat_answer", MSG)
    until = await other_process.busy_until()
    assert until is not None
    waited = await wait_until_idle(other_process, max_wait_s=0.2, poll_s=0.05)
    assert waited >= 0.15  # batch đã đợi vì cờ còn hạn


# ---------------------------------------------------------------- /admin/llm/*
@dataclass
class Rec:
    id: str
    role: str
    enabled: bool = True


class FakeRepo:
    keys: ClassVar[dict[str, Rec]] = {
        hash_key("admin"): Rec("dev-admin", "quan_tri"),
        hash_key("user"): Rec("u", "nguoi_dung"),
    }

    async def find_by_hash(self, key_hash: str) -> Rec | None:
        return self.keys.get(key_hash)


@pytest.fixture
async def admin_client(pg_gateway, clean_llm: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    gw, _ = pg_gateway
    set_gateway(gw)
    app = create_app()
    maker = async_sessionmaker(clean_llm, expire_on_commit=False)

    async def session_override():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_api_key_repo] = lambda: FakeRepo()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        yield client
    set_gateway(None)


async def test_admin_requires_quan_tri(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.get("/api/v1/admin/llm/health")).status_code == 401
    r = await admin_client.get("/api/v1/admin/llm/health", headers={"X-API-Key": "user"})
    assert r.status_code == 403


async def test_admin_health_config_stats(admin_client: httpx.AsyncClient, pg_gateway) -> None:
    gw, _ = pg_gateway
    h = {"X-API-Key": "admin"}
    health = (await admin_client.get("/api/v1/admin/llm/health", headers=h)).json()
    assert health["status"] == "ok"
    assert health["models_available"] == [
        "deepseek-r1-0528-qwen3-8b",
        "text-embedding-nomic-embed-text-v1.5",
    ]
    assert health["circuit"] == "closed" and "chat" in health["queue"]

    cfg = (await admin_client.get("/api/v1/admin/llm/config", headers=h)).json()
    assert cfg["api_key"] == "***" and "lm-studio" not in str(cfg)
    assert cfg["tasks"]["chat_answer"]["priority"] == 1

    for _ in range(3):
        await gw.complete_text("chat_answer", MSG)
    await gw.call_log.flush()
    stats = (await admin_client.get("/api/v1/admin/llm/stats", headers=h)).json()
    chat = stats["tasks"]["chat_answer"]
    assert chat["calls"] == 3 and chat["error_rate"] == 0 and chat["outcomes"] == {"ok": 3}
    assert chat["p50_ms"] is not None and chat["avg_reasoning_tokens"] is not None
