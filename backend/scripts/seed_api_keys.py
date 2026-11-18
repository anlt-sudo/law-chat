"""Tạo 3 API key dev (một cho mỗi vai trò) và in ra MỘT LẦN – DB chỉ lưu hash.

cd backend
uv run python -m scripts.seed_api_keys            # tạo key còn thiếu
uv run python -m scripts.seed_api_keys --rotate   # tạo lại cả 3 key
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.api_keys import ApiKey, Role, generate_key, hash_key
from app.core.logging import force_utf8_stdio
from app.db.pg import dispose_engine, get_sessionmaker

DEV_KEYS = {
    "dev-user": Role.NGUOI_DUNG,
    "dev-editor": Role.BIEN_TAP_VIEN,
    "dev-admin": Role.QUAN_TRI,
}


async def seed(rotate: bool) -> dict[str, str]:
    created: dict[str, str] = {}
    async with get_sessionmaker()() as session:
        existing = set((await session.scalars(select(ApiKey.id))).all())
        for key_id, role in DEV_KEYS.items():
            if key_id in existing and not rotate:
                continue
            raw = generate_key()
            stmt = insert(ApiKey).values(id=key_id, key_hash=hash_key(raw), role=role.value)
            stmt = stmt.on_conflict_do_update(
                index_elements=[ApiKey.id],
                set_={
                    "key_hash": stmt.excluded.key_hash,
                    "role": stmt.excluded.role,
                    "enabled": True,
                },
            )
            await session.execute(stmt)
            created[key_id] = raw
        await session.commit()
    await dispose_engine()
    return created


def main() -> None:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotate", action="store_true", help="tạo lại cả 3 key")
    args = parser.parse_args()
    created = asyncio.run(seed(args.rotate))
    if not created:
        print("Đã có đủ 3 key dev. Dùng --rotate để tạo lại.")
        return
    print("API key mới (chỉ hiện một lần, lưu lại ngay):")
    for key_id, raw in created.items():
        print(f"  {key_id:<11} {DEV_KEYS[key_id].value:<14} {raw}")


if __name__ == "__main__":
    main()
