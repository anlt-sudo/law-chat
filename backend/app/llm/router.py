"""API quản trị LLM (F17 §5.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_keys import Role
from app.core.auth import require_role
from app.core.config import get_settings
from app.db.pg import get_session
from app.llm import get_gateway
from app.llm.gateway import HealthStatus
from app.llm.profiles import get_profile, task_names

router = APIRouter(
    prefix="/admin/llm", tags=["admin-llm"], dependencies=[Depends(require_role(Role.QUAN_TRI))]
)


@router.get("/health", response_model=HealthStatus)
async def llm_health(refresh: bool = False) -> HealthStatus:
    gw = get_gateway()
    cached = gw.last_health
    max_age = timedelta(seconds=get_settings().llm_health_interval_s * 2)
    if refresh or cached is None or datetime.now(UTC) - cached.last_check > max_age:
        return await gw.check_health()
    state = gw.runtime_state()  # mạch / hàng đợi luôn lấy giá trị hiện tại
    return cached.model_copy(update={"circuit": state["circuit"], "queue": state["queue"]})


class TaskStats(BaseModel):
    calls: int
    p50_ms: float | None
    p95_ms: float | None
    avg_tokens_out: float | None
    avg_reasoning_tokens: float | None
    error_rate: float
    json_retry_rate: float
    outcomes: dict[str, int]


class StatsResponse(BaseModel):
    from_: datetime
    to: datetime
    tasks: dict[str, TaskStats]


@router.get("/stats", response_model=StatsResponse)
async def llm_stats(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> StatsResponse:
    to = to or datetime.now(UTC)
    from_ = from_ or to - timedelta(hours=24)
    rows = (
        await session.execute(
            text(
                """
                SELECT task,
                       count(*) AS calls,
                       percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
                       avg(tokens_out) AS avg_tokens_out,
                       avg(reasoning_tokens) AS avg_reasoning_tokens,
                       avg((outcome <> 'ok')::int) AS error_rate,
                       avg((attempts > 1)::int) AS json_retry_rate,
                       jsonb_object_agg_strict(outcome, n) AS outcomes
                  FROM (SELECT *, count(*) OVER (PARTITION BY task, outcome) AS n
                          FROM llm_call_log
                         WHERE created_at >= :from_ AND created_at < :to) t
                 GROUP BY task
                 ORDER BY task
                """
            ),
            {"from_": from_, "to": to},
        )
    ).mappings()
    tasks: dict[str, TaskStats] = {}
    for r in rows:
        tasks[r["task"]] = TaskStats(
            calls=r["calls"],
            p50_ms=r["p50_ms"],
            p95_ms=r["p95_ms"],
            avg_tokens_out=_f(r["avg_tokens_out"]),
            avg_reasoning_tokens=_f(r["avg_reasoning_tokens"]),
            error_rate=_f(r["error_rate"]) or 0.0,
            json_retry_rate=_f(r["json_retry_rate"]) or 0.0,
            outcomes={k: int(v) for k, v in (r["outcomes"] or {}).items()},
        )
    return StatsResponse(from_=from_, to=to, tasks=tasks)


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


@router.get("/config")
async def llm_config() -> dict[str, Any]:
    s = get_settings()
    return {
        "base_url": s.llm_base_url,
        "api_key": "***" if s.llm_api_key else "",
        "llm_model": s.llm_model,
        "embedding_model": s.embedding_model,
        "embedding_dim": s.embedding_dim,
        "embedding_context_tokens": s.embedding_context_tokens,
        "context_tokens": s.llm_context_tokens,
        "max_concurrency": s.llm_max_concurrency,
        "embed_max_concurrency": s.embed_max_concurrency,
        "chat_thinking": s.chat_thinking,
        "thinking_mode": s.thinking_mode,
        "json_mode": s.llm_json_mode,
        "json_max_attempts": s.llm_json_max_attempts,
        "reasoning_budget": s.llm_reasoning_budget,
        "chars_per_token": s.llm_chars_per_token,
        "log_content": s.llm_log_content,
        "trace_thinking": s.trace_thinking,
        "tasks": {t: get_profile(t, s).model_dump(exclude={"name"}) for t in task_names()},
    }
