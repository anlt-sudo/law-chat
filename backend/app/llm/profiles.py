"""Hồ sơ tác vụ (F17 §1.1, timeout điều chỉnh cho model chậm – M01 §2b)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.core.config import Settings

TaskName = Literal[
    "chat_answer",
    "query_analysis",
    "global_map",
    "extract_relations",
    "classify_topics",
    "summarize_cluster",
    "judge",
    "embed",
]
Priority = Literal[1, 2, 3]


class TaskProfile(BaseModel):
    name: str
    thinking: bool | Literal["config"]  # "config" → CHAT_THINKING
    temperature: float
    timeout_s: float
    priority: Priority
    interactive: bool  # True → không retry, trả lỗi ngay để caller dùng phương án dự phòng
    max_tokens: int


_BASE: dict[str, TaskProfile] = {
    p.name: p
    for p in [
        TaskProfile(name="chat_answer", thinking="config", temperature=0.1, timeout_s=180,
                    priority=1, interactive=True, max_tokens=1024),
        TaskProfile(name="query_analysis", thinking=False, temperature=0.0, timeout_s=1.5,
                    priority=1, interactive=True, max_tokens=512),
        TaskProfile(name="global_map", thinking=False, temperature=0.1, timeout_s=120,
                    priority=2, interactive=True, max_tokens=1024),
        TaskProfile(name="extract_relations", thinking=False, temperature=0.1, timeout_s=300,
                    priority=3, interactive=False, max_tokens=1024),
        TaskProfile(name="classify_topics", thinking=False, temperature=0.0, timeout_s=180,
                    priority=3, interactive=False, max_tokens=256),
        TaskProfile(name="summarize_cluster", thinking=False, temperature=0.2, timeout_s=300,
                    priority=3, interactive=False, max_tokens=1024),
        TaskProfile(name="judge", thinking=False, temperature=0.0, timeout_s=180,
                    priority=3, interactive=False, max_tokens=512),
        TaskProfile(name="embed", thinking=False, temperature=0.0, timeout_s=30,
                    priority=1, interactive=True, max_tokens=0),
    ]
}  # fmt: skip


def get_profile(task: str, settings: Settings) -> TaskProfile:
    try:
        base = _BASE[task]
    except KeyError:
        raise ValueError(f"Tác vụ LLM chưa khai báo: {task!r}") from None
    updates: dict[str, object] = {}
    if task in settings.llm_timeouts:
        updates["timeout_s"] = float(settings.llm_timeouts[task])
    if base.thinking == "config":
        updates["thinking"] = settings.chat_thinking
    return base.model_copy(update=updates) if updates else base


def task_names() -> list[str]:
    return list(_BASE)
