"""Thành phần thuần của LLM Gateway: lọc think, hàng đợi ưu tiên, circuit breaker, JSON, profile."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.circuit import CircuitBreaker
from app.llm.errors import LLMUnavailable
from app.llm.gateway import parse_json_output, security_warnings
from app.llm.priority import PrioritySemaphore
from app.llm.profiles import get_profile, task_names
from app.llm.think_filter import ThinkStreamFilter, split_think, strip_think


# ---------------------------------------------------------------- strip_think (BR-17.4)
@pytest.mark.parametrize(
    ("raw", "visible", "thinking"),
    [
        ("Trả lời", "Trả lời", ""),
        ("<think>suy nghĩ</think>Trả lời", "Trả lời", "suy nghĩ"),
        ("<think>a</think>X<think>b</think>Y", "XY", "ab"),
        ("Trả lời<think>chưa đóng ở cuối", "Trả lời", "chưa đóng ở cuối"),
        ("chỉ có thẻ đóng</think>Trả lời", "Trả lời", "chỉ có thẻ đóng"),
        ('<think>\n</think>\n\n{"a": 1}', '{"a": 1}', ""),
    ],
)
def test_split_think(raw: str, visible: str, thinking: str) -> None:
    assert split_think(raw) == (visible, thinking)
    assert strip_think(raw) == visible


def _run_stream(deltas: list[str]) -> tuple[str, str]:
    f = ThinkStreamFilter()
    vis, think = [], []
    for d in deltas:
        v, t = f.feed(d)
        vis.append(v)
        think.append(t)
    v, t = f.flush()
    return "".join(vis) + v, "".join(think) + t


@pytest.mark.parametrize(
    "deltas",
    [
        ["<think>abc</think>Xin chào"],
        ["<thi", "nk>abc</th", "ink>Xin", " chào"],          # thẻ cắt ngang delta
        ["<", "t", "h", "i", "n", "k", ">", "abc", "</", "think", ">", "Xin chào"],  # từng ký tự
        ["<think>a", "bc</think", ">Xin chào"],
    ],
)  # fmt: skip
def test_stream_filter_cut_tags(deltas: list[str]) -> None:
    assert _run_stream(deltas) == ("Xin chào", "abc")


def test_stream_filter_lone_angle_bracket_emitted() -> None:
    assert _run_stream(["a < b", " và 3 <", "4"]) == ("a < b và 3 <4", "")
    assert _run_stream(["kết thúc bằng <th"]) == ("kết thúc bằng <th", "")  # đệm không thành thẻ


def test_stream_filter_unclosed_block_dropped() -> None:
    assert _run_stream(["Trả lời <think>đang nghĩ dở"]) == ("Trả lời ", "đang nghĩ dở")


# ---------------------------------------------------------------- PrioritySemaphore (BR-17.6)
async def test_priority_semaphore_order() -> None:
    sem = PrioritySemaphore(1)
    order: list[str] = []
    await sem.acquire(3)  # giữ slot

    async def worker(name: str, prio: int) -> None:
        async with sem.slot(prio):
            order.append(name)

    tasks = [asyncio.create_task(worker(f"batch{i}", 3)) for i in range(3)]
    await asyncio.sleep(0)
    tasks.append(asyncio.create_task(worker("chat", 1)))  # đến sau nhưng ưu tiên cao
    await asyncio.sleep(0)
    assert sem.queue_sizes() == {"p1": 1, "p2": 0, "p3": 3}
    sem.release()
    await asyncio.gather(*tasks)
    assert order == ["chat", "batch0", "batch1", "batch2"]  # cùng ưu tiên → FIFO
    assert sem.available == 1


async def test_priority_semaphore_cancelled_waiter_does_not_leak() -> None:
    sem = PrioritySemaphore(1)
    await sem.acquire(1)
    waiter = asyncio.create_task(sem.acquire(3))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    sem.release()
    assert sem.available == 1
    await asyncio.wait_for(sem.acquire(1), timeout=1)


# ---------------------------------------------------------------- CircuitBreaker (BR-17.9)
def test_circuit_breaker_opens_and_half_opens() -> None:
    now = [0.0]
    cb = CircuitBreaker(threshold=5, window_s=60, open_s=30, clock=lambda: now[0])
    for _ in range(4):
        cb.before_call()
        cb.record_failure()
    assert cb.state == "closed"
    cb.before_call()
    cb.record_failure()
    assert cb.state == "open"
    with pytest.raises(LLMUnavailable):
        cb.before_call()
    now[0] = 31
    assert cb.state == "half_open"
    cb.before_call()  # 1 yêu cầu thử
    with pytest.raises(LLMUnavailable):
        cb.before_call()  # yêu cầu thứ 2 bị chặn khi đang thử
    cb.record_failure()  # thử thất bại → mở lại
    assert cb.state == "open"
    now[0] = 62
    cb.before_call()
    cb.record_success()
    assert cb.state == "closed"


def test_circuit_breaker_success_resets_and_window_expires() -> None:
    now = [0.0]
    cb = CircuitBreaker(threshold=3, window_s=60, clock=lambda: now[0])
    cb.record_failure()
    cb.record_failure()
    cb.record_success()  # liên tiếp bị ngắt
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"
    now[0] = 100  # 2 lỗi cũ ra khỏi cửa sổ 60 s
    cb.record_failure()
    assert cb.state == "closed"


# ---------------------------------------------------------------- JSON parse (BR-17.3)
class Rel(BaseModel):
    loai: str
    dich: str


@pytest.mark.parametrize(
    "raw",
    [
        '{"loai": "BAI_BO", "dich": "K10"}',
        '```json\n{"loai": "BAI_BO", "dich": "K10"}\n```',
        'Đây là kết quả:\n{"loai": "BAI_BO", "dich": "K10"}\nHết.',
    ],
)
def test_parse_json_output(raw: str) -> None:
    assert parse_json_output(raw, Rel) == Rel(loai="BAI_BO", dich="K10")


@pytest.mark.parametrize("raw", ["không có json", '{"loai": "BAI_BO"}', '{"loai": '])
def test_parse_json_output_invalid(raw: str) -> None:
    with pytest.raises(ValueError):  # ValidationError là lớp con của ValueError
        parse_json_output(raw, Rel)


# ---------------------------------------------------------------- bảo mật (BR-17.12)
@pytest.mark.parametrize(
    ("url", "warn"),
    [
        ("http://localhost:1235/v1", False),
        ("http://127.0.0.1:1234/v1", False),
        ("http://192.168.1.20:1234/v1", False),
        ("http://host.docker.internal:1235/v1", False),
        ("https://llm.example.com/v1", False),
        ("http://8.8.8.8:1234/v1", True),
        ("http://llm.example.com/v1", True),
    ],
)
def test_security_warnings(url: str, warn: bool) -> None:
    assert bool(security_warnings(url)) is warn


# ---------------------------------------------------------------- profiles
def test_profiles_and_overrides() -> None:
    s = Settings(_env_file=None, llm_timeouts={"chat_answer": 240}, chat_thinking=False)
    assert set(task_names()) >= {"chat_answer", "query_analysis", "extract_relations", "embed"}
    chat = get_profile("chat_answer", s)
    assert chat.timeout_s == 240 and chat.thinking is False and chat.priority == 1
    batch = get_profile("extract_relations", s)
    assert batch.priority == 3 and not batch.interactive
    with pytest.raises(ValueError):
        get_profile("khong_co", s)
