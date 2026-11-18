"""Constraint + index Neo4j theo 00-common §4.3. Idempotent (IF NOT EXISTS), chạy khi khởi động."""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.db import neo4j

logger = logging.getLogger(__name__)

CONSTRAINTS: list[tuple[str, str, str]] = [
    # (tên, label, thuộc tính)
    ("vanban_so_hieu", "VanBan", "so_hieu"),
    ("vanban_slug", "VanBan", "slug"),
    ("chuong_id", "Chuong", "id"),
    ("dieu_id", "Dieu", "id"),
    ("khoan_id", "Khoan", "id"),
    ("diem_id", "Diem", "id"),
    ("phienban_id", "PhienBan", "id"),
    ("cum_id", "Cum", "id"),
]


def schema_statements(embedding_dim: int) -> list[str]:
    stmts = [
        f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
        for name, label, prop in CONSTRAINTS
    ]
    stmts += [
        "CREATE INDEX phienban_hieu_luc IF NOT EXISTS "
        "FOR (p:PhienBan) ON (p.hieu_luc_tu, p.hieu_luc_den)",
        "CREATE FULLTEXT INDEX vanban_alias IF NOT EXISTS "
        "FOR (v:VanBan) ON EACH [v.so_hieu, v.trich_yeu]",
    ]
    vector_cfg = (
        "OPTIONS {indexConfig: {`vector.dimensions`: "
        f"{embedding_dim}"
        ", `vector.similarity_function`: 'cosine'}}"
    )
    stmts += [
        f"CREATE VECTOR INDEX phienban_embedding IF NOT EXISTS "
        f"FOR (p:PhienBan) ON p.embedding {vector_cfg}",
        f"CREATE VECTOR INDEX cum_embedding IF NOT EXISTS "
        f"FOR (c:Cum) ON c.tom_tat_embedding {vector_cfg}",
    ]
    return stmts


VECTOR_INDEXES = ("phienban_embedding", "cum_embedding")


async def drop_mismatched_vector_indexes(embedding_dim: int) -> list[str]:
    """Xóa vector index có số chiều khác EMBEDDING_DIM (đổi model embedding – F07 BR-07.4).

    `CREATE … IF NOT EXISTS` không sửa index đã có, nên phải xóa để tạo lại đúng số chiều.
    Vector cũ trên node vẫn còn nhưng không được đánh chỉ mục; M12 phải đánh dấu
    `embedding_stale = true` và tạo lại embedding.
    """
    rows = await neo4j.read("SHOW VECTOR INDEXES YIELD name, options RETURN name, options")
    dropped: list[str] = []
    for row in rows:
        if row["name"] not in VECTOR_INDEXES:
            continue
        current = (row["options"] or {}).get("indexConfig", {}).get("vector.dimensions")
        if current is not None and int(current) != embedding_dim:
            await neo4j.write(f"DROP INDEX {row['name']} IF EXISTS")
            dropped.append(row["name"])
            logger.warning(
                "Xóa vector index lệch số chiều để tạo lại",
                extra={"index": row["name"], "from_dim": current, "to_dim": embedding_dim},
            )
    return dropped


async def ensure_schema() -> int:
    """Tạo constraint / index còn thiếu. Trả về số câu lệnh đã chạy."""
    dim = get_settings().embedding_dim
    await drop_mismatched_vector_indexes(dim)
    stmts = schema_statements(dim)
    for stmt in stmts:
        await neo4j.write(stmt)
    logger.info("Neo4j schema ensured", extra={"statements": len(stmts)})
    return len(stmts)
