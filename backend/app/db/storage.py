"""Lưu file local cho bản dev: raw/ (bản gốc bất biến – F01 BR-01.7) và normalized/ (F02)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.core.config import get_settings


class StorageError(Exception):
    pass


class FileStorage:
    def __init__(self, base_dir: Path) -> None:
        self.base = base_dir.resolve()

    def path(self, rel: str) -> Path:
        """Đường dẫn tuyệt đối của `rel`; chặn thoát khỏi thư mục gốc (path traversal)."""
        p = (self.base / rel).resolve()
        if not p.is_relative_to(self.base):
            raise StorageError(f"Đường dẫn nằm ngoài storage: {rel!r}")
        return p

    def exists(self, rel: str) -> bool:
        return self.path(rel).exists()

    def read_bytes(self, rel: str) -> bytes:
        return self.path(rel).read_bytes()

    def write_bytes(self, rel: str, data: bytes, *, overwrite: bool = True) -> Path:
        """Ghi atomic (file tạm + rename). `overwrite=False` → file đã có thì giữ nguyên."""
        target = self.path(rel)
        if not overwrite and target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return target

    def write_text(self, rel: str, text: str, *, overwrite: bool = True) -> Path:
        return self.write_bytes(rel, text.encode("utf-8"), overwrite=overwrite)


def get_storage() -> FileStorage:
    return FileStorage(get_settings().data_dir)
