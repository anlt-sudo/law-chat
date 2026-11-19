"""LLM Gateway (F17). Dùng: `from app.llm import get_gateway`."""

from __future__ import annotations

from app.core.config import get_settings
from app.llm.errors import ContextTooLong, LLMError, LLMOutputError, LLMTimeout, LLMUnavailable
from app.llm.gateway import HealthStatus, JsonResult, LLMGateway, StreamDelta, TextResult

__all__ = [
    "ContextTooLong",
    "HealthStatus",
    "JsonResult",
    "LLMError",
    "LLMGateway",
    "LLMOutputError",
    "LLMTimeout",
    "LLMUnavailable",
    "StreamDelta",
    "TextResult",
    "close_gateway",
    "get_gateway",
]

_gateway: LLMGateway | None = None


def get_gateway() -> LLMGateway:
    """Singleton theo process, ghi log và cờ interactive_busy vào PostgreSQL."""
    global _gateway
    if _gateway is None:
        from app.db.pg import get_engine
        from app.llm.busy_flag import PgBusyFlag
        from app.llm.call_log import PgCallLogSink

        engine = get_engine()
        _gateway = LLMGateway(
            get_settings(), busy_flag=PgBusyFlag(engine), call_log=PgCallLogSink(engine)
        )
    return _gateway


def set_gateway(gateway: LLMGateway | None) -> None:
    """Thay gateway (test)."""
    global _gateway
    _gateway = gateway


async def close_gateway() -> None:
    global _gateway
    if _gateway is not None:
        await _gateway.aclose()
    _gateway = None
