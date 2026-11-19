"""Ước lượng token (BR-17.13). Không có tokenizer offline → heuristic theo số ký tự, chỉnh qua
LLM_CHARS_PER_TOKEN (đo bằng usage.prompt_tokens thực tế)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

PER_MESSAGE_OVERHEAD = 10


def estimate_text_tokens(text: str, chars_per_token: float) -> int:
    return math.ceil(len(text) / chars_per_token) if text else 0


def estimate_messages_tokens(messages: Sequence[dict[str, Any]], chars_per_token: float) -> int:
    total = 0
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, list):  # định dạng nhiều phần
            content = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        total += estimate_text_tokens(str(content), chars_per_token) + PER_MESSAGE_OVERHEAD
    return total
