"""LLMGateway với mock LM Studio (tiêu chí chấp nhận F17 §7)."""

from __future__ import annotations

import asyncio
import contextlib
import time

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.busy_flag import MemoryBusyFlag
from app.llm.call_log import MemorySink
from app.llm.errors import ContextTooLong, LLMError, LLMOutputError, LLMTimeout, LLMUnavailable
from app.llm.gateway import LLMGateway
from tests.mocks.lmstudio_mock import EMB, LLM, MockLMStudio, Script


class Relation(BaseModel):
    loai: str
    dieu_khoan_dich: str


def make_settings(**kw) -> Settings:
    base = {
        "llm_base_url": "http://localhost:1235/v1",
        "llm_model": LLM,
        "embedding_model": EMB,
        "embedding_dim": 768,
        "llm_context_tokens": 8192,
        "llm_reasoning_budget": 600,
        "thinking_mode": "none",
    }
    return Settings(_env_file=None, **{**base, **kw})


@pytest.fixture
def mock() -> MockLMStudio:
    return MockLMStudio()


@pytest.fixture
def sink() -> MemorySink:
    return MemorySink()


@pytest.fixture
async def gw(mock: MockLMStudio, sink: MemorySink):
    g = LLMGateway(
        make_settings(),
        transport=mock.transport(),
        call_log=sink,
        busy_flag=MemoryBusyFlag(),
        retry_backoff_s=(0, 0),
    )
    yield g
    await g.aclose()


MSG = [{"role": "user", "content": "Bãi bỏ khoản 10 Điều 3 Nghị định số 123/2020/NĐ-CP."}]


# ---------------------------------------------------------------- complete_text
async def test_complete_text_separates_reasoning(gw, mock, sink) -> None:
    mock.script(Script(content="Hóa đơn điện tử là…", reasoning="Người dùng hỏi về HĐĐT"))
    res = await gw.complete_text("chat_answer", MSG, return_thinking=True)
    assert res.text == "Hóa đơn điện tử là…"
    assert res.thinking == "Người dùng hỏi về HĐĐT"
    assert res.usage.reasoning_tokens is not None
    body = mock.chat_requests[0]["body"]
    assert body["model"] == LLM
    assert body["max_tokens"] == 1024 + 600  # cộng ngân sách suy nghĩ (M01 §2b)
    assert "chat_template_kwargs" not in body  # thinking_mode=none
    assert "/no_think" not in body["messages"][-1]["content"]
    rec = sink.records[-1]
    assert (rec.task, rec.outcome, rec.attempts, rec.priority) == ("chat_answer", "ok", 1, 1)


async def test_inline_think_in_content_is_stripped(gw, mock) -> None:
    mock.script(Script(content="<think>nghĩ</think>Kết quả", reasoning=""))
    res = await gw.complete_text("chat_answer", MSG)
    assert res.text == "Kết quả" and res.thinking is None


async def test_reasoning_truncated(gw, mock, sink) -> None:
    mock.script(Script(content="", reasoning="nghĩ mãi…", finish="length"))
    with pytest.raises(LLMOutputError) as ei:
        await gw.complete_text("chat_answer", MSG)
    assert ei.value.code == "REASONING_TRUNCATED"
    assert sink.records[-1].outcome == "error"


@pytest.mark.parametrize(
    ("mode", "check"),
    [
        ("soft_switch", lambda b: b["messages"][-1]["content"].endswith("/no_think")),
        ("template", lambda b: b["chat_template_kwargs"] == {"enable_thinking": False}),
    ],
)
async def test_thinking_modes(mock, mode, check) -> None:
    g = LLMGateway(make_settings(thinking_mode=mode), transport=mock.transport())
    await g.complete_text("extract_relations", MSG)  # tác vụ batch: thinking tắt
    assert check(mock.chat_requests[-1]["body"])
    await g.aclose()


# ---------------------------------------------------------------- complete_json (BR-17.3)
async def test_json_invalid_twice_then_valid(gw, mock, sink) -> None:
    mock.script(
        Script(content="không phải json"),
        Script(content='{"loai": "BAI_BO"}'),  # thiếu trường
        Script(content='{"loai": "BAI_BO", "dieu_khoan_dich": "khoản 10 Điều 3"}'),
    )
    res = await gw.complete_json_full("extract_relations", MSG, Relation)
    assert res.value == Relation(loai="BAI_BO", dieu_khoan_dich="khoản 10 Điều 3")
    assert res.attempts == 3
    # lần 2, 3 có kèm thông báo lỗi lần trước
    second = mock.chat_requests[1]["body"]["messages"]
    assert second[-1]["role"] == "user" and "JSON trước không hợp lệ" in second[-1]["content"]
    assert "dieu_khoan_dich" in mock.chat_requests[2]["body"]["messages"][-1]["content"]
    fmt = mock.chat_requests[0]["body"]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["name"] == "Relation"
    rec = sink.records[-1]
    assert (rec.outcome, rec.attempts) == ("ok", 3)


async def test_json_invalid_three_times(gw, mock, sink) -> None:
    mock.script(*[Script(content="sai") for _ in range(3)])
    with pytest.raises(LLMOutputError) as ei:
        await gw.complete_json("extract_relations", MSG, Relation)
    assert ei.value.code == "JSON_INVALID"
    assert len(mock.chat_requests) == 3
    assert (sink.records[-1].outcome, sink.records[-1].attempts) == ("json_error", 3)


async def test_json_prompt_mode(mock) -> None:
    g = LLMGateway(make_settings(llm_json_mode="prompt"), transport=mock.transport())
    mock.script(Script(content='{"loai": "BAI_BO", "dieu_khoan_dich": "K10"}'))
    await g.complete_json("extract_relations", MSG, Relation)
    body = mock.chat_requests[0]["body"]
    assert "response_format" not in body
    assert (
        body["messages"][0]["role"] == "system" and "JSON Schema" in body["messages"][0]["content"]
    )
    await g.aclose()


# ---------------------------------------------------------------- context (BR-17.13)
async def test_context_too_long_no_http(gw, mock, sink) -> None:
    huge = [{"role": "user", "content": "x" * 30_000}]  # ~12 000 token > 8 192
    with pytest.raises(ContextTooLong):
        await gw.complete_text("chat_answer", huge)
    assert mock.chat_requests == []
    assert sink.records == []  # lỗi trước khi gọi → chưa vào lượt, không log


async def test_lmstudio_context_error_mapped(gw, mock) -> None:
    mock.script(Script(status=400, body='{"error": "context length exceeded (n_ctx 4096)"}'))
    with pytest.raises(ContextTooLong):
        await gw.complete_text("chat_answer", MSG)


async def test_bad_request_not_retried(gw, mock) -> None:
    mock.script(Script(status=400, body="model not found"))
    with pytest.raises(LLMError) as ei:
        await gw.complete_text("chat_answer", MSG)
    assert ei.value.code == "LLM_BAD_REQUEST"
    assert len(mock.chat_requests) == 1


# ---------------------------------------------------------------- retry / circuit (BR-17.8, 17.9)
async def test_5xx_retried_then_success(gw, mock) -> None:
    mock.script(Script(status=503), Script(status=500), Script(content="OK sau retry"))
    res = await gw.complete_text("extract_relations", MSG)
    assert res.text == "OK sau retry"
    assert len(mock.chat_requests) == 3


async def test_timeout_not_retried(gw, mock, sink) -> None:
    mock.script(Script(exc=httpx.ReadTimeout))
    with pytest.raises(LLMTimeout):
        await gw.complete_text("chat_answer", MSG)
    assert len(mock.chat_requests) == 1
    assert sink.records[-1].outcome == "timeout"
    assert gw.breaker.state == "closed"  # model chậm không làm mở mạch


async def test_lmstudio_down_opens_circuit_fast_fail(gw, mock, sink) -> None:
    mock.down = True
    with pytest.raises(LLMUnavailable):
        await gw.complete_text("chat_answer", MSG)  # 3 lần thử → 3 lỗi
    with pytest.raises(LLMUnavailable):
        await gw.complete_text("chat_answer", MSG)  # lỗi thứ 5 → mở mạch
    assert gw.breaker.state == "open"
    t0 = time.perf_counter()
    with pytest.raises(LLMUnavailable) as ei:
        await gw.complete_text("chat_answer", MSG)
    assert (time.perf_counter() - t0) * 1000 < 50  # F17 §7
    assert ei.value.code == "CIRCUIT_OPEN"
    assert sink.records[-1].outcome == "unavailable"


# ---------------------------------------------------------------- stream (UC-17.2)
async def _collect(gen):
    out = []
    async with contextlib.aclosing(gen) as g:
        async for d in g:
            out.append(d)
    return out


async def test_stream_hides_reasoning(gw, mock) -> None:
    mock.script(Script(content="Khoản 10 Điều 3 đã bị bãi bỏ.", reasoning="Suy nghĩ bí mật"))
    deltas = await _collect(gw.stream_text("chat_answer", MSG))
    text = "".join(d.text for d in deltas)
    assert text == "Khoản 10 Điều 3 đã bị bãi bỏ."
    assert "bí mật" not in text and all(d.thinking == "" for d in deltas)
    assert deltas[-1].done and deltas[-1].finish_reason == "stop"
    assert deltas[-1].usage is not None and deltas[-1].usage.reasoning_tokens


async def test_stream_inline_think_cut_across_deltas(gw, mock) -> None:
    mock.script(
        Script(deltas=[{"content": "<thi"}, {"content": "nk>bí "}, {"content": "mật</th"},
                       {"content": "ink>Trả "}, {"content": "lời"}])
    )  # fmt: skip
    deltas = await _collect(gw.stream_text("chat_answer", MSG))
    assert "".join(d.text for d in deltas) == "Trả lời"


async def test_stream_return_thinking(gw, mock) -> None:
    mock.script(Script(content="Đáp", reasoning="Nghĩ"))
    deltas = await _collect(gw.stream_text("chat_answer", MSG, return_thinking=True))
    assert "".join(d.thinking for d in deltas) == "Nghĩ"
    assert "".join(d.text for d in deltas) == "Đáp"


async def test_stream_reasoning_truncated(gw, mock) -> None:
    mock.script(Script(content="", reasoning="nghĩ…", finish="length"))
    with pytest.raises(LLMOutputError):
        await _collect(gw.stream_text("chat_answer", MSG))


async def test_stream_releases_slot_when_consumer_stops_early(gw, mock) -> None:
    mock.script(Script(content="a" * 40))
    async with contextlib.aclosing(gw.stream_text("chat_answer", MSG)) as g:
        async for _ in g:
            break
    await asyncio.wait_for(gw.complete_text("chat_answer", MSG), timeout=2)  # slot đã trả


# ---------------------------------------------------------------- embed (UC-17.3)
async def test_embed_prefix_batch_and_dim(mock, sink) -> None:
    g = LLMGateway(make_settings(embedding_batch_size=2), transport=mock.transport(), call_log=sink)
    vecs = await g.embed(["a", "b", "c"], kind="document")
    assert len(vecs) == 3 and all(len(v) == 768 for v in vecs)
    emb = [r for r in mock.requests if r["path"].endswith("/embeddings")]
    assert [len(r["body"]["input"]) for r in emb] == [2, 1]
    assert emb[0]["body"]["input"][0] == "search_document: a"
    q = await g.embed(["hủy hóa đơn"])
    assert mock.requests[-1]["body"]["input"] == ["search_query: hủy hóa đơn"]
    assert q[0] == (await g.embed(["hủy hóa đơn"]))[0]  # xác định
    assert sink.records[-1].model == EMB
    await g.aclose()


async def test_embed_dim_mismatch(mock) -> None:
    g = LLMGateway(make_settings(embedding_dim=1024), transport=mock.transport())
    with pytest.raises(LLMOutputError) as ei:
        await g.embed(["x"])
    assert ei.value.code == "EMBEDDING_DIM_MISMATCH"
    await g.aclose()


async def test_embed_too_long(gw) -> None:
    with pytest.raises(ContextTooLong):
        await gw.embed(["x" * 6000])  # ~2 400 token > 2 048 của nomic


# ---------------------------------------------------------------- ưu tiên (BR-17.5 → 17.7)
async def test_chat_served_before_waiting_batch(mock) -> None:
    """F17 §7: batch đang chạy → câu hỏi chat mới được phục vụ trước các lời gọi batch đang chờ."""
    g = LLMGateway(make_settings(llm_max_concurrency=1), transport=mock.transport())
    mock.default_chat = Script(content="x", delay_s=0.05)
    batch = [
        asyncio.create_task(
            g.complete_text("extract_relations", [{"role": "user", "content": f"b{i}"}])
        )
        for i in range(3)
    ]
    await asyncio.sleep(0.01)  # b0 đang chạy, b1 b2 chờ
    chat = asyncio.create_task(
        g.complete_text("chat_answer", [{"role": "user", "content": "chat"}])
    )
    await asyncio.gather(*batch, chat)
    assert mock.chat_order[:2] == ["b0", "chat"]
    await g.aclose()


async def test_batch_waits_while_interactive_flag_set(mock) -> None:
    flag = MemoryBusyFlag()
    g = LLMGateway(make_settings(), transport=mock.transport(), busy_flag=flag)
    await flag.mark(0.3)  # process khác đang phục vụ người dùng
    t0 = time.monotonic()
    await g.complete_text("extract_relations", MSG)
    assert time.monotonic() - t0 >= 0.25
    await g.aclose()


async def test_interactive_call_sets_flag(gw) -> None:
    assert await gw.busy.busy_until() is None
    await gw.complete_text("chat_answer", MSG)
    assert await gw.busy.busy_until() is not None


# ---------------------------------------------------------------- health (BR-17.10)
async def test_health_ok(gw) -> None:
    h = await gw.check_health()
    assert h.status == "ok" and h.llm_model_ok and h.embedding_model_ok
    assert set(h.models_loaded or []) == {LLM, EMB}
    assert h.loaded_context_length == 16384
    assert h.warnings == [] and h.circuit == "closed"
    assert gw.last_health is h


async def test_health_degraded_missing_model(mock) -> None:
    mock.models = (LLM,)
    g = LLMGateway(make_settings(), transport=mock.transport())
    h = await g.check_health()
    assert h.status == "degraded" and not h.embedding_model_ok
    assert any("EMBEDDING_MODEL" in w for w in h.warnings)
    await g.aclose()


async def test_health_warns_single_loaded_model_and_small_context(mock) -> None:
    mock.loaded = (LLM,)
    mock.loaded_context_length = 4096
    g = LLMGateway(make_settings(), transport=mock.transport())
    h = await g.check_health()
    assert h.status == "ok"
    assert any("JIT" in w for w in h.warnings)
    assert any("Context đang nạp (4096)" in w for w in h.warnings)
    await g.aclose()


async def test_health_down(mock) -> None:
    mock.down = True
    g = LLMGateway(make_settings(), transport=mock.transport())
    h = await g.check_health()
    assert h.status == "down" and h.error
    await g.aclose()


async def test_health_without_v0_api(mock) -> None:
    mock.loaded = None
    g = LLMGateway(make_settings(), transport=mock.transport())
    h = await g.check_health()
    assert h.status == "ok" and h.models_loaded is None
    await g.aclose()
