"""Cờ "đang có người dùng chat" dùng chung giữa process API và worker (BR-17.7).

Semaphore ưu tiên chỉ có tác dụng trong một process. Process API ghi `interactive_busy_until`
khi phục vụ tác vụ ưu tiên 1; worker batch đợi cờ hết hạn trước mỗi lời gọi ưu tiên 3.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

FLAG_KEY = "interactive_busy_until"


class BusyFlag(Protocol):
    async def mark(self, seconds: float) -> None: ...
    async def busy_until(self) -> datetime | None: ...


class PgBusyFlag:
    def __init__(self, engine: AsyncEngine, *, min_write_interval_s: float = 2.0) -> None:
        self.engine = engine
        self.min_write_interval_s = min_write_interval_s
        self._last_write = 0.0
        self._last_until: datetime | None = None

    async def mark(self, seconds: float) -> None:
        until = datetime.now(UTC) + timedelta(seconds=seconds)
        # Giảm số lần ghi: bỏ qua nếu vừa ghi và hạn cũ còn đủ xa
        if (
            self._last_until is not None
            and time.monotonic() - self._last_write < self.min_write_interval_s
            and self._last_until >= until - timedelta(seconds=self.min_write_interval_s)
        ):
            return
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO runtime_flag (key, value_ts, updated_at)
                    VALUES (:key, :until, now())
                    ON CONFLICT (key) DO UPDATE
                       SET value_ts = GREATEST(runtime_flag.value_ts, EXCLUDED.value_ts),
                           updated_at = now()
                    """
                ),
                {"key": FLAG_KEY, "until": until},
            )
        self._last_write = time.monotonic()
        self._last_until = until

    async def busy_until(self) -> datetime | None:
        async with self.engine.connect() as conn:
            value = await conn.scalar(
                text("SELECT value_ts FROM runtime_flag WHERE key = :key"), {"key": FLAG_KEY}
            )
        return value


class MemoryBusyFlag:
    """Dùng trong test / khi không có PostgreSQL."""

    def __init__(self) -> None:
        self.until: datetime | None = None

    async def mark(self, seconds: float) -> None:
        until = datetime.now(UTC) + timedelta(seconds=seconds)
        self.until = max(self.until, until) if self.until else until

    async def busy_until(self) -> datetime | None:
        return self.until


async def wait_until_idle(
    flag: BusyFlag, *, max_wait_s: float = 300.0, poll_s: float = 1.0
) -> float:
    """Đợi tới khi không còn tác vụ tương tác (tối đa `max_wait_s`). Trả số giây đã đợi.

    Lỗi đọc cờ không được chặn batch: log rồi chạy tiếp.
    """
    start = time.monotonic()
    while time.monotonic() - start < max_wait_s:
        try:
            until = await flag.busy_until()
        except Exception:
            logger.warning("Không đọc được cờ interactive_busy", exc_info=True)
            break
        if until is None or until <= datetime.now(UTC):
            break
        await asyncio.sleep(poll_s)
    return time.monotonic() - start
