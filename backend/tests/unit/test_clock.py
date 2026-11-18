from datetime import date, datetime

from app.core.clock import VN_TZ, now_vn, today_vn


def test_real_clock_is_vietnam_time(settings_env) -> None:
    settings_env.delenv("APP_FAKE_TODAY", raising=False)
    settings_env.delenv("APP_FAKE_NOW", raising=False)
    now = now_vn()
    assert now.utcoffset() == datetime.now(VN_TZ).utcoffset()
    assert today_vn() == datetime.now(VN_TZ).date()


def test_fake_today(settings_env) -> None:
    settings_env.setenv("APP_FAKE_TODAY", "2026-01-01")
    settings_env.delenv("APP_FAKE_NOW", raising=False)
    assert today_vn() == date(2026, 1, 1)
    assert now_vn().tzinfo is not None


def test_fake_now_overrides_fake_today(settings_env) -> None:
    settings_env.setenv("APP_FAKE_TODAY", "2026-01-01")
    settings_env.setenv("APP_FAKE_NOW", "2026-11-20T02:00:00")
    assert now_vn() == datetime(2026, 11, 20, 2, 0, tzinfo=VN_TZ)


def test_fake_now_with_utc_offset_converted(settings_env) -> None:
    settings_env.setenv(
        "APP_FAKE_NOW", "2025-12-31T18:30:00+00:00"
    )  # = 01:30 ngày 01/01/2026 giờ VN
    assert today_vn() == date(2026, 1, 1)


def test_empty_env_means_no_fake(settings_env) -> None:
    settings_env.setenv("APP_FAKE_TODAY", "")
    settings_env.setenv("APP_FAKE_NOW", "")
    assert today_vn() == datetime.now(VN_TZ).date()
