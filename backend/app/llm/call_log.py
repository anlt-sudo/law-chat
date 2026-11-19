"""Ghi llm_call_log (BR-17.11) bất đồng bộ – không cộng độ trễ, lỗi ghi log chỉ cảnh báo."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


@dataclass
class CallRecord:
    task: str
    model: str
    priority: int
    thinking: bool
    attempts: int
    outcome: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    reasoning_tokens: int | None = None
    queue_ms: int | None = None
    latency_ms: int | None = None
    error: str | None = None
    prompt: Any | None = None
    output: str | None = None
    caller_ref: str | None = None


class CallLogSink(Protocol):
    def submit(self, record: CallRecord) -> None: ...
    async def flush(self) -> None: ...


class MemorySink:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    def submit(self, record: CallRecord) -> None:
        self.records.append(record)

    async def flush(self) -> None:
        return None


class PgCallLogSink:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(self, record: CallRecord) -> None:
        task = asyncio.get_running_loop().create_task(self._write(record))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _write(self, record: CallRecord) -> None:
        row = asdict(record)
        row["prompt"] = (
            None if record.prompt is None else json.dumps(record.prompt, ensure_ascii=False)
        )
        if row["error"]:
            row["error"] = row["error"][:4000]
        try:
            async with self.engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        INSERT INTO llm_call_log
                          (task, model, priority, thinking, attempts, tokens_in, tokens_out,
                           reasoning_tokens, queue_ms, latency_ms, outcome, error, prompt,
                           output, caller_ref)
                        VALUES
                          (:task, :model, :priority, :thinking, :attempts, :tokens_in, :tokens_out,
                           :reasoning_tokens, :queue_ms, :latency_ms, :outcome, :error,
                           CAST(:prompt AS jsonb), :output, :caller_ref)
                        """
                    ),
                    row,
                )
        except Exception:
            logger.warning("Không ghi được llm_call_log", exc_info=True)

    async def flush(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
