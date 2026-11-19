"""ORM llm_call_log (F17 §6.2) và runtime_flag (bổ sung – cờ dùng chung giữa process)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

OUTCOMES = ("ok", "json_error", "timeout", "unavailable", "context_too_long", "error")


class LlmCallLog(Base):
    __tablename__ = "llm_call_log"
    __table_args__ = (
        CheckConstraint(f"outcome IN ({', '.join(repr(o) for o in OUTCOMES)})", name="outcome"),
        Index("ix_llm_call_log_task_created_at", "task", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    thinking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)  # bổ sung: model luôn suy nghĩ
    queue_ms: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    prompt: Mapped[Any | None] = mapped_column(JSONB)
    output: Mapped[str | None] = mapped_column(Text)
    caller_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RuntimeFlag(Base):
    __tablename__ = "runtime_flag"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
