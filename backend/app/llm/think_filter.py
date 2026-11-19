"""Lọc khối <think>…</think> (F17 BR-17.4).

LM Studio hiện tách suy nghĩ ra `reasoning_content`, nhưng vẫn lọc `content` để an toàn khi đổi
model / cấu hình (một số bản trả suy nghĩ lẫn trong `content`).
"""

from __future__ import annotations

import re

OPEN = "<think>"
CLOSE = "</think>"

_BLOCK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL)
_STRAY_CLOSE_RE = re.compile(r"^.*?</think>", re.DOTALL)


def split_think(text: str) -> tuple[str, str]:
    """Trả (văn bản hiển thị, nội dung suy nghĩ). Khối chưa đóng ở cuối bị coi là suy nghĩ."""
    thinking: list[str] = []

    def _take(m: re.Match[str]) -> str:
        thinking.append(m.group(0).removeprefix(OPEN).removesuffix(CLOSE))
        return ""

    visible = _BLOCK_RE.sub(_take, text)
    # Một số template bỏ thẻ mở, chỉ có thẻ đóng: "…suy nghĩ…</think>trả lời"
    if CLOSE in visible:
        m = _STRAY_CLOSE_RE.match(visible)
        if m:
            thinking.insert(0, m.group(0).removesuffix(CLOSE))
            visible = visible[m.end() :]
    return visible.strip(), "".join(thinking).strip()


def strip_think(text: str) -> str:
    return split_think(text)[0]


def _partial_suffix(text: str, tag: str) -> int:
    """Độ dài phần cuối của `text` trùng với tiền tố của `tag` (thẻ bị cắt giữa 2 delta)."""
    for n in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:n]):
            return n
    return 0


class ThinkStreamFilter:
    """Máy trạng thái Outside / Inside cho stream, chịu được thẻ bị cắt qua nhiều delta."""

    def __init__(self) -> None:
        self.inside = False
        self._pending = ""

    def feed(self, delta: str) -> tuple[str, str]:
        """Nhận một delta, trả (phần hiển thị, phần suy nghĩ) phát ra được ngay."""
        buf = self._pending + delta
        self._pending = ""
        visible: list[str] = []
        thinking: list[str] = []
        while buf:
            tag = CLOSE if self.inside else OPEN
            idx = buf.find(tag)
            out = thinking if self.inside else visible
            if idx >= 0:
                out.append(buf[:idx])
                buf = buf[idx + len(tag) :]
                self.inside = not self.inside
                continue
            keep = _partial_suffix(buf, tag)
            out.append(buf[: len(buf) - keep])
            self._pending = buf[len(buf) - keep :]
            break
        return "".join(visible), "".join(thinking)

    def flush(self) -> tuple[str, str]:
        """Kết thúc stream: phần đệm không thành thẻ được phát ra; khối chưa đóng bị bỏ."""
        rest, self._pending = self._pending, ""
        return ("", rest) if self.inside else (rest, "")
