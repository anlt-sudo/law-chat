from pathlib import Path

import pytest

from app.db.neo4j_schema import CONSTRAINTS, schema_statements
from app.db.storage import FileStorage, StorageError
from app.jobs import registry
from app.jobs.queue import backoff_seconds


# ---------- FileStorage ----------
def test_storage_write_read(tmp_path: Path) -> None:
    fs = FileStorage(tmp_path)
    fs.write_bytes("raw/2026/abc.pdf", b"%PDF-1.7")
    assert fs.read_bytes("raw/2026/abc.pdf") == b"%PDF-1.7"
    assert not list((tmp_path / "raw/2026").glob(".tmp-*"))  # không còn file tạm


def test_storage_no_overwrite(tmp_path: Path) -> None:
    fs = FileStorage(tmp_path)
    fs.write_bytes("raw/x.bin", b"first")
    fs.write_bytes("raw/x.bin", b"second", overwrite=False)  # bản gốc bất biến (BR-01.7)
    assert fs.read_bytes("raw/x.bin") == b"first"


@pytest.mark.parametrize("rel", ["../outside.txt", "raw/../../outside.txt"])
def test_storage_blocks_traversal(tmp_path: Path, rel: str) -> None:
    with pytest.raises(StorageError):
        FileStorage(tmp_path / "data").path(rel)


# ---------- registry ----------
def test_registry_register_and_duplicate() -> None:
    async def fn(job) -> None: ...

    registry.register("unit_test_step", fn)
    try:
        assert registry.get_handler("unit_test_step") is fn
        assert "unit_test_step" in registry.registered_steps()
        with pytest.raises(ValueError):
            registry.register("unit_test_step", fn)
    finally:
        registry.unregister("unit_test_step")


def test_backoff() -> None:
    assert [backoff_seconds(n) for n in (1, 2, 3)] == [2, 4, 8]


# ---------- Neo4j schema ----------
def test_schema_statements() -> None:
    stmts = schema_statements(1024)
    assert len(CONSTRAINTS) == 8
    assert len(stmts) == 12
    assert all("IF NOT EXISTS" in s for s in stmts)
    vector = [s for s in stmts if "VECTOR INDEX" in s]
    assert len(vector) == 2 and all("`vector.dimensions`: 1024" in s for s in vector)
