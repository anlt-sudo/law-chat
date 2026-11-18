from datetime import date

import pytest

from app.legal.validity import intervals_overlap, is_active

TU = date(2022, 7, 1)
DEN = date(2025, 6, 1)


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2022, 6, 30), False),  # trước hiệu lực
        (date(2022, 7, 1), True),  # đúng ngày bắt đầu
        (date(2025, 3, 15), True),  # trong khoảng (Q4)
        (date(2025, 5, 31), True),
        (date(2025, 6, 1), False),  # đúng ngày hieu_luc_den → HẾT hiệu lực (nửa mở)
        (date(2026, 11, 18), False),  # sau
    ],
)
def test_is_active_closed_interval(d: date, expected: bool) -> None:
    assert is_active(TU, DEN, d) is expected


def test_is_active_open_ended() -> None:
    assert is_active(TU, None, date(2099, 1, 1))
    assert not is_active(TU, None, date(2022, 6, 30))


def test_is_active_missing_start_is_inactive() -> None:
    # F13 BR-13.4: thiếu ngày → không xác định → coi như không hiệu lực
    assert not is_active(None, None, date(2026, 11, 18))


def test_intervals_overlap() -> None:
    # Hai phiên bản liên tiếp không chồng lấn
    assert not intervals_overlap(TU, DEN, DEN, None)
    assert intervals_overlap(TU, DEN, date(2025, 5, 1), None)
    assert intervals_overlap(TU, None, date(2030, 1, 1), None)
