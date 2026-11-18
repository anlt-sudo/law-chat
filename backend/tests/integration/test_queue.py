"""Hàng đợi job trên PostgreSQL (M00-T9)."""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.jobs import queue, registry
from app.jobs.queue import Job
from app.jobs.worker import Worker

pytestmark = pytest.mark.integration


async def _status(engine: AsyncEngine, job_id: uuid.UUID) -> tuple[str, int, str | None]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT status, attempts, error FROM pipeline_job WHERE id = :id"),
                {"id": job_id},
            )
        ).one()
    return row.status, row.attempts, row.error


async def _make_ready(engine: AsyncEngine) -> None:
    """Bỏ qua thời gian backoff để test chạy nhanh."""
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE pipeline_job SET run_after = now() WHERE status = 'QUEUED'")
        )


@pytest.fixture
def step_name():
    name = f"t_{uuid.uuid4().hex[:8]}"
    yield name
    registry.unregister(name)


async def test_enqueue_claim_complete(clean_jobs: AsyncEngine) -> None:
    async with clean_jobs.begin() as conn:
        job_id = await queue.enqueue(conn, "noop", {"so_hieu": "123/2020/NĐ-CP"})
    assert job_id is not None
    async with clean_jobs.begin() as conn:
        job = await queue.claim_next(conn)
        assert job is not None and job.id == job_id
        assert job.status == "RUNNING" and job.attempts == 1
        assert job.payload == {"so_hieu": "123/2020/NĐ-CP"}
        await queue.complete(conn, job.id)
    assert (await _status(clean_jobs, job_id))[0] == "DONE"


async def test_priority_and_step_filter(clean_jobs: AsyncEngine) -> None:
    async with clean_jobs.begin() as conn:
        low = await queue.enqueue(conn, "extract", priority=3)
        high = await queue.enqueue(conn, "extract", priority=1)
        other = await queue.enqueue(conn, "parse", priority=1)
    async with clean_jobs.begin() as conn:
        first = await queue.claim_next(conn, ["extract"])
        second = await queue.claim_next(conn, ["extract"])
        third = await queue.claim_next(conn, ["extract"])
    assert first is not None and first.id == high
    assert second is not None and second.id == low
    assert third is None  # job "parse" không thuộc bước được nhận
    assert (await _status(clean_jobs, other))[0] == "QUEUED"


async def test_delayed_job_not_claimed(clean_jobs: AsyncEngine) -> None:
    async with clean_jobs.begin() as conn:
        await queue.enqueue(conn, "noop", delay_s=60)
        assert await queue.claim_next(conn) is None


async def test_dedupe_key(clean_jobs: AsyncEngine) -> None:
    async with clean_jobs.begin() as conn:
        a = await queue.enqueue(conn, "parse", dedupe_key="parse:doc-1")
        b = await queue.enqueue(conn, "parse", dedupe_key="parse:doc-1")
    assert a is not None and b is None  # đang QUEUED → không tạo trùng
    async with clean_jobs.begin() as conn:
        job = await queue.claim_next(conn)
        assert job is not None
        assert await queue.enqueue(conn, "parse", dedupe_key="parse:doc-1") is None  # đang RUNNING
        await queue.complete(conn, job.id)
        c = await queue.enqueue(conn, "parse", dedupe_key="parse:doc-1")  # đã DONE → được tạo lại
    assert c is not None and c != a


async def test_two_workers_never_run_same_job(clean_jobs: AsyncEngine, step_name: str) -> None:
    runs: Counter[uuid.UUID] = Counter()

    async def count(job: Job) -> None:
        runs[job.id] += 1
        await asyncio.sleep(0.01)

    registry.register(step_name, count)
    async with clean_jobs.begin() as conn:
        ids = [await queue.enqueue(conn, step_name, {"i": i}) for i in range(10)]

    async def drain(w: Worker) -> None:
        while await w.run_once():
            pass

    w1, w2 = Worker(clean_jobs, steps=[step_name]), Worker(clean_jobs, steps=[step_name])
    await asyncio.gather(drain(w1), drain(w2))

    assert set(runs) == set(ids)
    assert all(n == 1 for n in runs.values())
    for job_id in ids:
        assert job_id is not None
        assert (await _status(clean_jobs, job_id))[0] == "DONE"


async def test_retry_then_failed_after_3_attempts(clean_jobs: AsyncEngine, step_name: str) -> None:
    calls = 0

    async def flaky(job: Job) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("tạm thời")

    registry.register(step_name, flaky)
    async with clean_jobs.begin() as conn:
        job_id = await queue.enqueue(conn, step_name)
    assert job_id is not None
    w = Worker(clean_jobs, steps=[step_name])

    for expected_attempts in (1, 2):
        assert await w.run_once()
        status, attempts, error = await _status(clean_jobs, job_id)
        assert (status, attempts) == ("QUEUED", expected_attempts)
        assert error is not None and "tạm thời" in error
        assert not await w.run_once()  # đang trong thời gian backoff
        await _make_ready(clean_jobs)

    assert await w.run_once()
    assert (await _status(clean_jobs, job_id))[:2] == ("FAILED", 3)
    assert calls == 3


async def test_permanent_error_fails_immediately(clean_jobs: AsyncEngine) -> None:
    import app.jobs.builtin  # noqa: F401 – đăng ký handler noop

    async with clean_jobs.begin() as conn:
        job_id = await queue.enqueue(conn, "noop", {"fail": "permanent"})
    assert job_id is not None
    assert await Worker(clean_jobs, steps=["noop"]).run_once()
    status, attempts, error = await _status(clean_jobs, job_id)
    assert (status, attempts) == ("FAILED", 1)
    assert error is not None and "PermanentJobError" in error


async def test_job_without_handler_fails(clean_jobs: AsyncEngine) -> None:
    async with clean_jobs.begin() as conn:
        job_id = await queue.enqueue(conn, "khong_co_handler")
    assert job_id is not None
    assert await Worker(clean_jobs, steps=["khong_co_handler"]).run_once()
    assert (await _status(clean_jobs, job_id))[0] == "FAILED"


async def test_recover_stale_running_jobs(clean_jobs: AsyncEngine) -> None:
    async with clean_jobs.begin() as conn:
        job_id = await queue.enqueue(conn, "noop")
        await queue.claim_next(conn)
        await conn.execute(
            text("UPDATE pipeline_job SET started_at = now() - interval '2 hours' WHERE id = :id"),
            {"id": job_id},
        )
        fresh = await queue.enqueue(conn, "noop")
        await queue.claim_next(conn)  # vừa chạy, chưa quá hạn
        recovered = await queue.recover_stale(conn, older_than_minutes=30)
    assert recovered == 1
    assert job_id is not None and fresh is not None
    assert (await _status(clean_jobs, job_id))[0] == "QUEUED"
    assert (await _status(clean_jobs, fresh))[0] == "RUNNING"
