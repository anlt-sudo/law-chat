"""Log JSON một dòng, gắn request_id / job_id từ contextvar."""

from __future__ import annotations

import io
import json
import logging
import re
import sys
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime

from fastapi import Request, Response

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if rid := request_id_var.get():
            payload["request_id"] = rid
        if jid := job_id_var.get():
            payload["job_id"] = jid
        # Trường bổ sung truyền qua logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def force_utf8_stdio() -> None:
    """Ép stdout / stderr dùng UTF-8.

    Console Windows có thể dùng bảng mã cũ (cp932, cp1252…) → in tiếng Việt bị UnicodeEncodeError.
    """
    for stream in (sys.stdout, sys.stderr):
        is_utf8 = getattr(stream, "encoding", "").lower() in ("utf-8", "utf8")
        if isinstance(stream, io.TextIOWrapper) and not is_utf8:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def setup_logging(level: str = "INFO") -> None:
    force_utf8_stdio()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Log truy cập của uvicorn đã có middleware lo; giảm nhiễu từ driver
    for noisy in ("neo4j", "elastic_transport", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    incoming = request.headers.get("X-Request-ID")
    rid = incoming if incoming and _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    return response
