"""Đồng hồ hệ thống theo giờ Việt Nam, thay được bằng APP_FAKE_TODAY / APP_FAKE_NOW.

Mọi chỗ cần "hôm nay" (trạng thái hiệu lực, ngày áp dụng mặc định, lịch chạy) phải gọi
`today_vn()` / `now_vn()` thay vì `date.today()` – để test được kịch bản F15 (vd 01/01/2026).
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now_vn() -> datetime:
    s = get_settings()
    if s.app_fake_now is not None:
        fake = s.app_fake_now
        return fake.astimezone(VN_TZ) if fake.tzinfo else fake.replace(tzinfo=VN_TZ)
    real = datetime.now(VN_TZ)
    if s.app_fake_today is not None:
        return datetime.combine(s.app_fake_today, real.timetz())
    return real


def today_vn() -> date:
    return now_vn().date()
