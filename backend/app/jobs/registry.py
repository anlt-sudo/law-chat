"""Đăng ký handler theo bước: `@handler("parse")`. Handler phải idempotent (F15 BR-15.6)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.jobs.queue import Job

Handler = Callable[[Job], Awaitable[None]]

_HANDLERS: dict[str, Handler] = {}


class PermanentJobError(Exception):
    """Lỗi không nên retry (dữ liệu sai, file hỏng…) → job FAILED ngay."""


def register(step: str, fn: Handler, *, replace: bool = False) -> Handler:
    if step in _HANDLERS and not replace:
        raise ValueError(f"Bước {step!r} đã có handler")
    _HANDLERS[step] = fn
    return fn


def handler(step: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        return register(step, fn)

    return deco


def get_handler(step: str) -> Handler | None:
    return _HANDLERS.get(step)


def registered_steps() -> list[str]:
    return sorted(_HANDLERS)


def unregister(step: str) -> None:
    _HANDLERS.pop(step, None)
