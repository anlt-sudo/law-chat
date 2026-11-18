"""/api/v1/health trên dịch vụ thật + spike analyzer ICU (M00-T10, M00-T12)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from app.db import es as es_mod
from app.db import neo4j as neo4j_mod
from app.db import pg as pg_mod
from app.main import create_app
from tests.conftest import skip_or_fail

pytestmark = pytest.mark.integration


@pytest.fixture
async def es_ready() -> AsyncIterator[None]:
    try:
        await es_mod.get_es().info()
    except Exception as exc:
        await es_mod.close_es()
        skip_or_fail("elasticsearch", f"{type(exc).__name__}: {exc}")
    yield
    await es_mod.close_es()


async def test_icu_folding_vietnamese(es_ready: None) -> None:
    """'hủy hóa đơn' và 'huy hoa don' phải ra cùng token với analyzer vi_folded (F07 BR-07.6)."""
    client = es_mod.get_es()
    index = "spike-icu-test"
    await client.options(ignore_status=404).indices.delete(index=index)
    await client.indices.create(
        index=index,
        settings={
            "analysis": {
                "analyzer": {
                    "vi_folded": {
                        "tokenizer": "icu_tokenizer",
                        "filter": ["lowercase", "asciifolding"],
                    }
                }
            }
        },
    )
    try:

        async def tokens(t: str) -> list[str]:
            r = await client.indices.analyze(index=index, analyzer="vi_folded", text=t)
            return [x["token"] for x in r["tokens"]]

        assert await tokens("Hủy hóa đơn") == await tokens("huy hoa don") == ["huy", "hoa", "don"]
        assert await tokens("Nghị định") == ["nghi", "dinh"]
    finally:
        await client.indices.delete(index=index)


async def test_health_all_ok(es_ready: None) -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.get("/api/v1/health")
    finally:
        await pg_mod.dispose_engine()
        await neo4j_mod.close_driver()
    body = r.json()
    failed = {k: v["error"] for k, v in body["components"].items() if v["status"] != "ok"}
    if failed:
        for name in failed:
            skip_or_fail(name, str(failed[name]))
    assert r.status_code == 200
    assert body["status"] == "ok"
    assert "analysis-icu" in body["components"]["elasticsearch"]["info"]["plugins"]


async def test_live() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/api/v1/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
