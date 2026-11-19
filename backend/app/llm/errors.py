"""Lỗi có kiểu rõ ràng của LLM Gateway (F17 §5.1)."""

from __future__ import annotations


class LLMError(Exception):
    """Gốc của mọi lỗi gateway."""

    code = "LLM_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class LLMUnavailable(LLMError):
    """LM Studio không kết nối được hoặc mạch đang mở (BR-17.8, BR-17.9)."""

    code = "LLM_UNAVAILABLE"


class LLMTimeout(LLMError):
    code = "LLM_TIMEOUT"


class LLMOutputError(LLMError):
    """Output không dùng được: JSON lỗi sau N lần (BR-17.3), hết token khi đang suy nghĩ…"""

    code = "LLM_OUTPUT_ERROR"


class ContextTooLong(LLMError):
    """Prompt + max_tokens vượt context (BR-17.13) – caller phải cắt ngữ cảnh."""

    code = "CONTEXT_TOO_LONG"
