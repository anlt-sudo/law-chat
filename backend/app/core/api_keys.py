"""Bảng api_key (bổ sung so với đặc tả – 00-common §6 chỉ nêu X-API-Key gắn vai trò)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role(StrEnum):
    NGUOI_DUNG = "nguoi_dung"
    BIEN_TAP_VIEN = "bien_tap_vien"
    QUAN_TRI = "quan_tri"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {Role.NGUOI_DUNG: 1, Role.BIEN_TAP_VIEN: 2, Role.QUAN_TRI: 3}


class ApiKey(Base):
    __tablename__ = "api_key"
    __table_args__ = (
        CheckConstraint("role IN ('nguoi_dung','bien_tap_vien','quan_tri')", name="role"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_key() -> str:
    return "lg_" + secrets.token_urlsafe(32)


class ApiKeyRecord(Protocol):
    id: str
    role: str
    enabled: bool


class ApiKeyRepo(Protocol):
    async def find_by_hash(self, key_hash: str) -> ApiKeyRecord | None: ...


class PgApiKeyRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_hash(self, key_hash: str) -> ApiKey | None:
        return await self.session.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))
