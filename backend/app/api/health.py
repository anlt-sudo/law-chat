"""GET /api/v1/health – trạng thái các kho dữ liệu. GET /api/v1/health/live – process còn sống."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.core.clock import now_vn
from app.db import neo4j
from app.db.es import get_es, installed_plugins
from app.db.pg import get_engine

router = APIRouter(prefix="/health", tags=["health"])

CHECK_TIMEOUT_S = 3.0


class ComponentStatus(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: int
    error: str | None = None
    info: dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    today: str
    components: dict[str, ComponentStatus]


async def _check(fn: Callable[[], Awaitable[dict[str, Any]]]) -> ComponentStatus:
    start = time.perf_counter()
    try:
        info = await asyncio.wait_for(fn(), timeout=CHECK_TIMEOUT_S)
        return ComponentStatus(status="ok", latency_ms=_ms(start), info=info)
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        return ComponentStatus(status="error", latency_ms=_ms(start), error=msg[:300])


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


async def _pg() -> dict[str, Any]:
    async with get_engine().connect() as conn:
        version = await conn.scalar(text("SHOW server_version"))
    return {"server_version": version}


async def _neo4j() -> dict[str, Any]:
    rows = await neo4j.read(
        "CALL dbms.components() YIELD name, versions, edition "
        "RETURN name, versions[0] AS version, edition"
    )
    return rows[0] if rows else {}


async def _es() -> dict[str, Any]:
    info = await get_es().info()
    plugins = await installed_plugins()
    if "analysis-icu" not in plugins:
        raise RuntimeError("Thiếu plugin analysis-icu")
    return {"version": info["version"]["number"], "plugins": sorted(plugins)}


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    pg, neo, es = await asyncio.gather(_check(_pg), _check(_neo4j), _check(_es))
    components = {"postgres": pg, "neo4j": neo, "elasticsearch": es}
    ok = all(c.status == "ok" for c in components.values())
    if not ok:
        response.status_code = 503
    return HealthResponse(
        status="ok" if ok else "degraded",
        version=__version__,
        today=now_vn().date().isoformat(),
        components=components,
    )
