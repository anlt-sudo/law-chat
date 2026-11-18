"""ORM pipeline_run / pipeline_job (F15 §6, tạo sớm ở M00; thêm priority, run_after, dedupe_key)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RUN_STATUSES = ("QUEUED", "RUNNING", "DONE", "PARTIAL", "FAILED")
JOB_STATUSES = ("QUEUED", "RUNNING", "DONE", "FAILED", "CANCELLED")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class PipelineRun(Base):
    __tablename__ = "pipeline_run"
    __table_args__ = (
        CheckConstraint("trigger IN ('schedule','manual','event')", name="trigger"),
        CheckConstraint(_in("status", RUN_STATUSES), name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineJob(Base):
    __tablename__ = "pipeline_job"
    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUSES), name="status"),
        Index("ix_pipeline_job_claim", "status", "priority", "run_after"),
        Index(
            "uq_pipeline_job_dedupe_active",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('QUEUED','RUNNING')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_run.id")
    )
    step: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="3")
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    dedupe_key: Mapped[str | None] = mapped_column(String)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
