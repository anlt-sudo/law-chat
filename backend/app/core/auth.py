"""Xác thực bản dev bằng header X-API-Key (00-common §6, README giả định 8)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_keys import ApiKeyRepo, PgApiKeyRepo, Role, hash_key
from app.core.errors import AppError
from app.db.pg import get_session


@dataclass(frozen=True)
class Principal:
    id: str
    role: Role


def get_api_key_repo(session: AsyncSession = Depends(get_session)) -> ApiKeyRepo:
    return PgApiKeyRepo(session)


async def get_principal(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    repo: ApiKeyRepo = Depends(get_api_key_repo),
) -> Principal:
    if not x_api_key:
        raise AppError("UNAUTHORIZED", "Thiếu header X-API-Key", status_code=401)
    record = await repo.find_by_hash(hash_key(x_api_key))
    if record is None or not record.enabled:
        raise AppError("UNAUTHORIZED", "API key không hợp lệ", status_code=401)
    return Principal(id=record.id, role=Role(record.role))


def require_role(min_role: Role) -> Callable[..., Awaitable[Principal]]:
    """Dependency: cho phép vai trò `min_role` và các vai trò cao hơn."""

    async def _check(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role.rank < min_role.rank:
            raise AppError(
                "FORBIDDEN",
                f"Cần vai trò {min_role.value} trở lên",
                status_code=403,
                details={"role": principal.role.value, "required": min_role.value},
            )
        return principal

    return _check
