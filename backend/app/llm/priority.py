"""Semaphore có hàng đợi ưu tiên (BR-17.5, BR-17.6): ưu tiên nhỏ chạy trước, cùng ưu tiên FIFO."""

from __future__ import annotations

import asyncio
import heapq
import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class PrioritySemaphore:
    def __init__(self, value: int) -> None:
        if value < 1:
            raise ValueError("value phải ≥ 1")
        self._value = value
        self._waiters: list[tuple[int, int, asyncio.Future[None]]] = []
        self._seq = itertools.count()

    async def acquire(self, priority: int) -> None:
        if self._value > 0 and not self._pending_waiters():
            self._value -= 1
            return
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiters, (priority, next(self._seq), fut))
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                # Đã được trao slot đúng lúc bị hủy → trả lại slot cho người kế tiếp
                self.release()
            raise

    def release(self) -> None:
        while self._waiters:
            _, _, fut = heapq.heappop(self._waiters)
            if not fut.done():
                fut.set_result(None)  # trao slot trực tiếp, không tăng _value
                return
        self._value += 1

    @asynccontextmanager
    async def slot(self, priority: int) -> AsyncIterator[None]:
        await self.acquire(priority)
        try:
            yield
        finally:
            self.release()

    def _pending_waiters(self) -> bool:
        return any(not f.done() for _, _, f in self._waiters)

    def queue_sizes(self) -> dict[str, int]:
        sizes = {"p1": 0, "p2": 0, "p3": 0}
        for p, _, fut in self._waiters:
            if not fut.done():
                sizes[f"p{p}"] = sizes.get(f"p{p}", 0) + 1
        return sizes

    @property
    def available(self) -> int:
        return self._value
