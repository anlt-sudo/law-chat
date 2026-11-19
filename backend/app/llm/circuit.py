"""Circuit breaker (BR-17.9): 5 lỗi kết nối liên tiếp trong 60 s → mở 30 s → thử 1 yêu cầu."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Literal

from app.llm.errors import LLMUnavailable

State = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    def __init__(
        self,
        *,
        threshold: int = 5,
        window_s: float = 60.0,
        open_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold = threshold
        self.window_s = window_s
        self.open_s = open_s
        self._clock = clock
        self._failures: deque[float] = deque()
        self._state: State = "closed"
        self._opened_at = 0.0
        self._trial_in_flight = False

    @property
    def state(self) -> State:
        if self._state == "open" and self._clock() - self._opened_at >= self.open_s:
            return "half_open"
        return self._state

    def before_call(self) -> None:
        """Ném LLMUnavailable ngay (không gọi mạng) khi mạch mở."""
        state = self.state
        if state == "open":
            raise LLMUnavailable("Mạch LLM đang mở do lỗi kết nối liên tiếp", code="CIRCUIT_OPEN")
        if state == "half_open":
            if self._trial_in_flight:
                raise LLMUnavailable("Đang thử kết nối lại LLM", code="CIRCUIT_OPEN")
            self._state = "half_open"
            self._trial_in_flight = True

    def record_success(self) -> None:
        self._failures.clear()
        self._state = "closed"
        self._trial_in_flight = False

    def record_failure(self) -> None:
        now = self._clock()
        if self._state == "half_open":
            self._open(now)
            return
        self._failures.append(now)
        while self._failures and now - self._failures[0] > self.window_s:
            self._failures.popleft()
        if len(self._failures) >= self.threshold:
            self._open(now)

    def release_trial(self) -> None:
        """Lời gọi thử kết thúc không phải do lỗi kết nối (vd timeout, 4xx) – cho thử lại sau."""
        self._trial_in_flight = False

    def _open(self, now: float) -> None:
        self._state = "open"
        self._opened_at = now
        self._trial_in_flight = False
        self._failures.clear()
