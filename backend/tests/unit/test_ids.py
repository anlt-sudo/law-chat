from datetime import date

import pytest

from app.legal.ids import (
    UnitKind,
    chuong_id,
    diem_id,
    dieu_id,
    khoan_id,
    normalize_so_hieu,
    parent_id,
    parse_unit_id,
    slugify,
    split_version_id,
    version_id,
)


@pytest.mark.parametrize(
    ("so_hieu", "slug"),
    [
        ("123/2020/NĐ-CP", "123-2020-nd-cp"),
        ("70/2025/NĐ-CP", "70-2025-nd-cp"),
        ("78/2021/TT-BTC", "78-2021-tt-btc"),
        ("198/2025/QH15", "198-2025-qh15"),
        ("12/2024/QĐ-TTg", "12-2024-qd-ttg"),
    ],
)
def test_slugify(so_hieu: str, slug: str) -> None:
    assert slugify(so_hieu) == slug


def test_slugify_nfd_input_same_as_nfc() -> None:
    nfd = "123/2020/NĐ-CP"  # Đ là ký tự riêng, nhưng thử thêm chữ có dấu tổ hợp
    assert slugify(nfd) == "123-2020-nd-cp"
    assert slugify("Nghị định") == slugify("Nghị định") == "nghi-dinh"


def test_normalize_so_hieu() -> None:
    assert normalize_so_hieu(" 123/2020/nđ-cp ") == "123/2020/NĐ-CP"
    with pytest.raises(ValueError):
        normalize_so_hieu("NĐ 123")


def test_build_ids() -> None:
    d = dieu_id("123/2020/NĐ-CP", "3")
    k = khoan_id(d, "10")
    assert d == "123/2020/NĐ-CP:Đ3"
    assert k == "123/2020/NĐ-CP:Đ3:K10"
    assert diem_id(khoan_id(dieu_id("123/2020/NĐ-CP", "9"), "4"), "a") == "123/2020/NĐ-CP:Đ9:K4:a"
    assert dieu_id("123/2020/NĐ-CP", "9a") == "123/2020/NĐ-CP:Đ9a"
    assert diem_id(k, "đ") == "123/2020/NĐ-CP:Đ3:K10:đ"
    assert diem_id(k, "d1") == "123/2020/NĐ-CP:Đ3:K10:d1"
    assert chuong_id("123/2020/NĐ-CP", "ii") == "123/2020/NĐ-CP:CII"


@pytest.mark.parametrize(
    "bad",
    [
        lambda: dieu_id("123/2020/NĐ-CP", "3.1"),
        lambda: khoan_id("123/2020/NĐ-CP", "1"),  # cha không phải Điều
        lambda: diem_id("123/2020/NĐ-CP:Đ3", "a"),  # cha không phải Khoản
        lambda: diem_id("123/2020/NĐ-CP:Đ3:K1", "aa"),
        lambda: chuong_id("123/2020/NĐ-CP", "2"),
    ],
)
def test_build_ids_invalid(bad) -> None:
    with pytest.raises(ValueError):
        bad()


@pytest.mark.parametrize(
    ("uid", "kind"),
    [
        ("123/2020/NĐ-CP", UnitKind.VAN_BAN),
        ("123/2020/NĐ-CP:CII", UnitKind.CHUONG),
        ("123/2020/NĐ-CP:Đ9a", UnitKind.DIEU),
        ("123/2020/NĐ-CP:Đ3:K10", UnitKind.KHOAN),
        ("123/2020/NĐ-CP:Đ9:K4:đ", UnitKind.DIEM),
        ("198/2025/QH15:Đ1:K2", UnitKind.KHOAN),
    ],
)
def test_parse_roundtrip(uid: str, kind: UnitKind) -> None:
    ref = parse_unit_id(uid)
    assert ref.kind is kind
    assert ref.id == uid


@pytest.mark.parametrize(
    "bad",
    [
        "NĐ123",
        "123/2020/NĐ-CP:K10",
        "123/2020/NĐ-CP:Đ3:10",
        "123/2020/NĐ-CP:Đ3:K10:a:b",
        "123/2020/NĐ-CP:Đ3:K10@2022-07-01",
    ],
)
def test_parse_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_unit_id(bad)


def test_parent_id() -> None:
    assert parent_id("123/2020/NĐ-CP:Đ9:K4:a") == "123/2020/NĐ-CP:Đ9:K4"
    assert parent_id("123/2020/NĐ-CP:Đ9:K4") == "123/2020/NĐ-CP:Đ9"
    assert parent_id("123/2020/NĐ-CP:Đ9") == "123/2020/NĐ-CP"
    assert parent_id("123/2020/NĐ-CP:CII") == "123/2020/NĐ-CP"
    assert parent_id("123/2020/NĐ-CP") is None


def test_version_id() -> None:
    vid = version_id("123/2020/NĐ-CP:Đ19:K1", date(2025, 6, 1))
    assert vid == "123/2020/NĐ-CP:Đ19:K1@2025-06-01"
    assert split_version_id(vid) == ("123/2020/NĐ-CP:Đ19:K1", date(2025, 6, 1))
    unknown = version_id("123/2020/NĐ-CP:Đ5", None)
    assert unknown == "123/2020/NĐ-CP:Đ5@unknown"
    assert split_version_id(unknown) == ("123/2020/NĐ-CP:Đ5", None)
    with pytest.raises(ValueError):
        version_id("123/2020/NĐ-CP:Đ9:K4:a", date(2025, 6, 1))  # Điểm không có phiên bản riêng
