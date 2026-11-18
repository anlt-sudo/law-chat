"""Kết nối Neo4j. Dùng `driver.execute_query` – đã có retry cho lỗi tạm thời."""

from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, RoutingControl

from app.core.config import get_settings

_driver: AsyncDriver | None = None


def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        s = get_settings()
        _driver = AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
    return _driver


async def read(query: str, **params: Any) -> list[dict[str, Any]]:
    result = await get_driver().execute_query(
        query, params, routing_=RoutingControl.READ, database_=get_settings().neo4j_database
    )
    return [r.data() for r in result.records]


async def write(query: str, **params: Any) -> list[dict[str, Any]]:
    result = await get_driver().execute_query(
        query, params, routing_=RoutingControl.WRITE, database_=get_settings().neo4j_database
    )
    return [r.data() for r in result.records]


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
    _driver = None
