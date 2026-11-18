"""Khoảng hiệu lực nửa mở [hieu_luc_tu, hieu_luc_den) – 00-common §3.

Đây là nơi DUY NHẤT định nghĩa phép so sánh ngày hiệu lực ở phía Python; các module khác
(F06, F13, F11…) gọi hàm này thay vì tự viết lại điều kiện.
"""

from __future__ import annotations

from datetime import date


def is_active(hieu_luc_tu: date | None, hieu_luc_den: date | None, d: date) -> bool:
    """Có hiệu lực tại ngày `d`.

    - `hieu_luc_tu is None` → không xác định → coi như KHÔNG hiệu lực (F13 BR-13.4).
    - `hieu_luc_den is None` → chưa hết hiệu lực.
    - Đúng ngày `hieu_luc_den` → đã HẾT hiệu lực (khoảng nửa mở).
    """
    if hieu_luc_tu is None:
        return False
    return hieu_luc_tu <= d and (hieu_luc_den is None or hieu_luc_den > d)


def intervals_overlap(a_tu: date, a_den: date | None, b_tu: date, b_den: date | None) -> bool:
    """Hai khoảng nửa mở có giao nhau không (dùng để kiểm tra bất biến phiên bản – F06 BR-06.3)."""
    a_end = a_den or date.max
    b_end = b_den or date.max
    return a_tu < b_end and b_tu < a_end
