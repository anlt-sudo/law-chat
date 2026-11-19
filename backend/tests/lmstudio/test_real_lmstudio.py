"""Gọi LM Studio THẬT (chậm: vài phút). Chỉ chạy khi đặt RUN_LMSTUDIO=1:

$env:RUN_LMSTUDIO=1; uv run pytest tests/lmstudio -s
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from app.core.config import get_settings
from app.llm.gateway import LLMGateway

pytestmark = [
    pytest.mark.lmstudio,
    pytest.mark.skipif(os.environ.get("RUN_LMSTUDIO") != "1", reason="đặt RUN_LMSTUDIO=1 để chạy"),
]


@pytest.fixture(scope="module")
async def gw() -> AsyncIterator[LLMGateway]:
    g = LLMGateway(get_settings())
    health = await g.check_health()
    if health.status == "down":
        pytest.skip(f"LM Studio không chạy: {health.error}")
    yield g
    await g.aclose()


async def test_health_reports_both_models(gw: LLMGateway) -> None:
    h = await gw.check_health()
    print("\nhealth:", h.model_dump_json(indent=2))
    assert h.llm_model_ok and h.embedding_model_ok


class Relation(BaseModel):
    loai: str
    dieu_khoan_dich: str
    van_ban_dich: str


async def test_extract_relations_json_no_think(gw: LLMGateway) -> None:
    msgs = [
        {
            "role": "system",
            "content": (
                "Bạn trích xuất quan hệ giữa các văn bản pháp luật. loai ∈ "
                "SUA_DOI|BAI_BO|THAY_THE|HUONG_DAN. dieu_khoan_dich: tham chiếu dạng chữ ngắn "
                "(vd 'khoản 10 Điều 3'). van_ban_dich: chỉ số hiệu (vd '123/2020/NĐ-CP')."
            ),
        },
        {"role": "user", "content": "Bãi bỏ khoản 10 Điều 3 Nghị định số 123/2020/NĐ-CP."},
    ]
    res = await gw.complete_json_full("extract_relations", msgs, Relation)
    print("\nrelation:", res.value, "attempts:", res.attempts, "usage:", res.usage)
    assert "<think>" not in res.value.model_dump_json()


async def test_chat_stream_has_no_think(gw: LLMGateway) -> None:
    text = []
    async with contextlib.aclosing(
        gw.stream_text(
            "chat_answer", [{"role": "user", "content": "1 + 1 bằng mấy? Trả lời ngắn."}]
        )
    ) as stream:
        async for d in stream:
            text.append(d.text)
    out = "".join(text)
    print("\nstream:", out)
    assert out.strip() and "<think>" not in out


async def test_embed_nomic(gw: LLMGateway) -> None:
    v = await gw.embed(["hủy hóa đơn điện tử"], kind="query")
    assert len(v[0]) == get_settings().embedding_dim
