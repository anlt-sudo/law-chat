"""Hàng đợi job trên PostgreSQL – `SELECT … FOR UPDATE SKIP LOCKED` (README giả định 10).

Mọi hàm nhận `AsyncConnection` để có thể enqueue trong cùng transaction với dữ liệu nghiệp vụ
(vd M02 tạo source_document + job normalize cùng lúc).
Session ORM dùng `await session.connection()`.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncConnection

MAX_ATTEMPTS = 3


def backoff_seconds(attempts: int) -> int:
    """Sau lần thử thứ n thất bại: 2, 4, 8 giây…"""
    return int(2 ** max(attempts, 1))


@dataclass(frozen=True)
class Job:
    id: uuid.UUID
    step: str
    status: str
    attempts: int
    priority: int
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: uuid.UUID | None = None
    source_document_id: uuid.UUID | None = None
    dedupe_key: str | None = None
    error: str | None = None

    @classmethod
    def from_row(cls, row: Any) -> Job:
        m = row._mapping
        return cls(
            id=m["id"],
            step=m["step"],
            status=m["status"],
            attempts=m["attempts"],
            priority=m["priority"],
            payload=dict(m["payload"] or {}),
            run_id=m["run_id"],
            source_document_id=m["source_document_id"],
            dedupe_key=m["dedupe_key"],
            error=m["error"],
        )


_COLUMNS = (
    "id, step, status, attempts, priority, payload, run_id, source_document_id, dedupe_key, error"
)


async def enqueue(
    conn: AsyncConnection,
    step: str,
    payload: dict[str, Any] | None = None,
    *,
    source_document_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    priority: int = 3,
    dedupe_key: str | None = None,
    delay_s: float = 0,
) -> uuid.UUID | None:
    """Tạo job. Trả None nếu đã có job cùng `dedupe_key` đang QUEUED / RUNNING."""
    job_id = uuid.uuid4()
    result = await conn.execute(
        text(
            """
            INSERT INTO pipeline_job
                (id, run_id, step, source_document_id, payload, status, priority,
                 run_after, dedupe_key)
            VALUES
                (:id, :run_id, :step, :source_document_id, CAST(:payload AS jsonb), 'QUEUED',
                 :priority, now() + make_interval(secs => :delay_s), :dedupe_key)
            ON CONFLICT (dedupe_key) WHERE status IN ('QUEUED','RUNNING') DO NOTHING
            RETURNING id
            """
        ),
        {
            "id": job_id,
            "run_id": run_id,
            "step": step,
            "source_document_id": source_document_id,
            "payload": json.dumps(payload or {}, ensure_ascii=False, default=str),
            "priority": priority,
            "delay_s": float(delay_s),
            "dedupe_key": dedupe_key,
        },
    )
    row = result.first()
    return row[0] if row else None


async def claim_next(conn: AsyncConnection, steps: Sequence[str] | None = None) -> Job | None:
    """Lấy job sẵn sàng có ưu tiên cao nhất, chuyển RUNNING.

    `SKIP LOCKED` bảo đảm hai worker không bao giờ nhận cùng một job.
    """
    step_filter = "AND step = ANY(:steps)" if steps else ""
    stmt = text(
        f"""
        UPDATE pipeline_job
           SET status = 'RUNNING', started_at = now(), attempts = attempts + 1, error = NULL
         WHERE id = (
               SELECT id FROM pipeline_job
                WHERE status = 'QUEUED' AND run_after <= now() {step_filter}
                ORDER BY priority, queued_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1)
        RETURNING {_COLUMNS}
        """
    )
    params: dict[str, Any] = {}
    if steps:
        stmt = stmt.bindparams(bindparam("steps", type_=ARRAY(Text)))
        params["steps"] = list(steps)
    row = (await conn.execute(stmt, params)).first()
    return Job.from_row(row) if row else None


async def complete(conn: AsyncConnection, job_id: uuid.UUID) -> None:
    await conn.execute(
        text(
            "UPDATE pipeline_job SET status = 'DONE', finished_at = now(), error = NULL "
            "WHERE id = :id"
        ),
        {"id": job_id},
    )


async def fail(
    conn: AsyncConnection,
    job: Job,
    error: str,
    *,
    permanent: bool = False,
    max_attempts: int = MAX_ATTEMPTS,
) -> str:
    """Ghi lỗi và trả trạng thái mới.

    Còn lượt → QUEUED với backoff; hết lượt hoặc `permanent` → FAILED.
    """
    if permanent or job.attempts >= max_attempts:
        await conn.execute(
            text(
                "UPDATE pipeline_job SET status = 'FAILED', finished_at = now(), error = :error "
                "WHERE id = :id"
            ),
            {"id": job.id, "error": error[:4000]},
        )
        return "FAILED"
    await conn.execute(
        text(
            """
            UPDATE pipeline_job
               SET status = 'QUEUED', error = :error,
                   run_after = now() + make_interval(secs => :delay)
             WHERE id = :id
            """
        ),
        {"id": job.id, "error": error[:4000], "delay": float(backoff_seconds(job.attempts))},
    )
    return "QUEUED"


async def recover_stale(conn: AsyncConnection, older_than_minutes: int) -> int:
    """Job RUNNING quá lâu (worker chết giữa chừng) → QUEUED lại. Trả số job được hồi phục."""
    result = await conn.execute(
        text(
            """
            UPDATE pipeline_job SET status = 'QUEUED', run_after = now(),
                   error = 'Hồi phục sau khi worker dừng đột ngột'
             WHERE status = 'RUNNING'
               AND started_at < now() - make_interval(mins => :mins)
            """
        ),
        {"mins": older_than_minutes},
    )
    return result.rowcount or 0


async def get_job(conn: AsyncConnection, job_id: uuid.UUID) -> Job | None:
    row = (
        await conn.execute(
            text(f"SELECT {_COLUMNS} FROM pipeline_job WHERE id = :id"), {"id": job_id}
        )
    ).first()
    return Job.from_row(row) if row else None
