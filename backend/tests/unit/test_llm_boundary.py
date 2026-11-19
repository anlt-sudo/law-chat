"""BR-17.1: chỉ app/llm được gọi LM Studio / OpenAI SDK."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
FORBIDDEN = re.compile(r"^\s*(import openai|from openai)|/chat/completions|/v1/embeddings", re.M)


def test_only_llm_package_talks_to_lmstudio() -> None:
    offenders = [
        str(p.relative_to(APP))
        for p in APP.rglob("*.py")
        if "llm" not in p.relative_to(APP).parts and FORBIDDEN.search(p.read_text("utf-8"))
    ]
    assert offenders == [], f"Gọi LM Studio ngoài app/llm: {offenders}"
