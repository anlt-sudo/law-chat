"""Neo4j schema idempotent (M00-T6)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.core.config import get_settings
from app.db import neo4j
from app.db.neo4j_schema import CONSTRAINTS, ensure_schema
from tests.conftest import skip_or_fail

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
async def neo4j_ready() -> AsyncIterator[None]:
    try:
        await neo4j.get_driver().verify_connectivity()
    except Exception as exc:
        await neo4j.close_driver()
        skip_or_fail("neo4j", f"{type(exc).__name__}: {exc}")
    yield
    await neo4j.close_driver()


async def _vector_dims() -> dict[str, int]:
    rows = await neo4j.read("SHOW VECTOR INDEXES YIELD name, options RETURN name, options")
    return {r["name"]: int(r["options"]["indexConfig"]["vector.dimensions"]) for r in rows}


async def test_vector_index_recreated_when_dim_changes(neo4j_ready: None, settings_env) -> None:
    """Đổi EMBEDDING_DIM (vd bge-m3 1024 → nomic 768) → vector index được tạo lại đúng chiều."""
    configured = get_settings().embedding_dim
    other = 1024 if configured != 1024 else 768
    try:
        settings_env.setenv("EMBEDDING_DIM", str(other))
        get_settings.cache_clear()
        await ensure_schema()
        assert set((await _vector_dims()).values()) == {other}
    finally:
        settings_env.setenv("EMBEDDING_DIM", str(configured))
        get_settings.cache_clear()
        await ensure_schema()
    dims = await _vector_dims()
    assert dims["phienban_embedding"] == dims["cum_embedding"] == configured


async def test_ensure_schema_twice(neo4j_ready: None) -> None:
    n1 = await ensure_schema()
    n2 = await ensure_schema()  # lần 2 không lỗi
    assert n1 == n2 == 12

    names = {r["name"] for r in await neo4j.read("SHOW CONSTRAINTS YIELD name RETURN name")}
    assert {c[0] for c in CONSTRAINTS} <= names

    indexes = {
        r["name"]: r["type"]
        for r in await neo4j.read("SHOW INDEXES YIELD name, type RETURN name, type")
    }
    assert indexes.get("phienban_embedding") == "VECTOR"
    assert indexes.get("cum_embedding") == "VECTOR"
    assert indexes.get("vanban_alias") == "FULLTEXT"
    assert "phienban_hieu_luc" in indexes


async def test_plugins_available(neo4j_ready: None) -> None:
    """Spike M00-T12: APOC + GDS có trong image; Leiden chạy được trên đồ thị nhỏ."""
    try:
        gds = await neo4j.read("RETURN gds.version() AS v")
    except Exception as exc:
        pytest.skip(f"GDS chưa cài (CI dùng Neo4j không plugin): {exc}")
    assert gds[0]["v"]

    await neo4j.write("MATCH (n:_LeidenSpike) DETACH DELETE n")
    await neo4j.write(
        """
        UNWIND range(0, 9) AS i CREATE (:_LeidenSpike {i: i, g: i / 5})
        WITH count(*) AS _
        MATCH (a:_LeidenSpike), (b:_LeidenSpike) WHERE a.g = b.g AND a.i < b.i
        CREATE (a)-[:_R]->(b)
        """
    )
    try:
        await neo4j.write("CALL gds.graph.drop('_leiden_spike', false) YIELD graphName")
        await neo4j.write(
            """
            MATCH (a:_LeidenSpike)
            OPTIONAL MATCH (a)-[:_R]->(b:_LeidenSpike)
            WITH gds.graph.project(
                '_leiden_spike', a, b, {}, {undirectedRelationshipTypes: ['*']}
            ) AS g
            RETURN g.graphName
            """
        )
        rows = await neo4j.read(
            "CALL gds.leiden.stream('_leiden_spike', {randomSeed: 42}) "
            "YIELD nodeId, communityId RETURN gds.util.asNode(nodeId).g AS g, communityId"
        )
        communities_by_group: dict[int, set[int]] = {}
        for r in rows:
            communities_by_group.setdefault(r["g"], set()).add(r["communityId"])
        # 2 nhóm tách biệt → mỗi nhóm đúng 1 cụm, hai cụm khác nhau
        assert all(len(c) == 1 for c in communities_by_group.values())
        assert len({next(iter(c)) for c in communities_by_group.values()}) == 2
    finally:
        await neo4j.write("CALL gds.graph.drop('_leiden_spike', false) YIELD graphName")
        await neo4j.write("MATCH (n:_LeidenSpike) DETACH DELETE n")
