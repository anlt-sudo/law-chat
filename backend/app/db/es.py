"""Kết nối Elasticsearch."""

from __future__ import annotations

from typing import Any, cast

from elasticsearch import AsyncElasticsearch

from app.core.config import get_settings

_client: AsyncElasticsearch | None = None


def get_es() -> AsyncElasticsearch:
    global _client
    if _client is None:
        _client = AsyncElasticsearch(get_settings().es_url, request_timeout=10)
    return _client


async def installed_plugins() -> set[str]:
    resp = await get_es().cat.plugins(format="json")
    rows = cast(list[dict[str, Any]], resp.body)  # format=json → list, stub khai báo là str
    return {str(r["component"]) for r in rows}


async def close_es() -> None:
    global _client
    if _client is not None:
        await _client.close()
    _client = None
