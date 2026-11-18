"""Định danh văn bản / điều khoản / phiên bản theo 00-common §2.

| Đối tượng | Định dạng                    | Ví dụ                                  |
|-----------|------------------------------|----------------------------------------|
| Văn bản   | số hiệu (NFC)                | 123/2020/NĐ-CP                         |
| slug      | không dấu, `/` → `-`         | 123-2020-nd-cp                         |
| Chương    | <so_hieu>:C<La Mã>           | 123/2020/NĐ-CP:CII                     |
| Điều      | <so_hieu>:Đ<số>[a-z]?        | 123/2020/NĐ-CP:Đ9a                     |
| Khoản     | <id điều>:K<số>              | 123/2020/NĐ-CP:Đ3:K10                  |
| Điểm      | <id khoản>:<chữ cái>         | 123/2020/NĐ-CP:Đ9:K4:a                 |
| Phiên bản | <id khoản|điều>@<YYYY-MM-DD> | 123/2020/NĐ-CP:Đ19:K1@2025-06-01       |

ID là xác định: cùng đầu vào luôn ra cùng chuỗi. Không bao giờ đổi khi điều khoản bị sửa đổi.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

SO_HIEU_RE = re.compile(r"^\d+/\d{4}/[A-ZĐ0-9]+(?:-[A-ZĐ0-9]+)*$")
_CHUONG_RE = re.compile(r"^[IVXLC]+$")
_DIEU_RE = re.compile(r"^\d+[a-z]?$")
_KHOAN_RE = re.compile(r"^\d+[a-z]?$")
_DIEM_RE = re.compile(r"^[a-zđ]\d?$")

UNKNOWN_VERSION = "unknown"  # phiên bản chưa xác định được ngày hiệu lực (M03 BR-03.7)


class UnitKind(StrEnum):
    VAN_BAN = "VanBan"
    CHUONG = "Chuong"
    DIEU = "Dieu"
    KHOAN = "Khoan"
    DIEM = "Diem"


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def normalize_so_hieu(so_hieu: str) -> str:
    """Chuẩn NFC, bỏ khoảng trắng, chữ hoa. Ném ValueError nếu sai định dạng."""
    s = re.sub(r"\s+", "", nfc(so_hieu)).upper()
    if not SO_HIEU_RE.match(s):
        raise ValueError(f"Số hiệu không hợp lệ: {so_hieu!r}")
    return s


def slugify(so_hieu: str) -> str:
    s = nfc(so_hieu).replace("Đ", "D").replace("đ", "d")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return s.strip("-")


def _check(pattern: re.Pattern[str], value: str, what: str) -> str:
    if not pattern.match(value):
        raise ValueError(f"{what} không hợp lệ: {value!r}")
    return value


def chuong_id(so_hieu: str, so: str) -> str:
    return f"{normalize_so_hieu(so_hieu)}:C{_check(_CHUONG_RE, so.upper(), 'Số chương')}"


def dieu_id(so_hieu: str, so: str) -> str:
    return f"{normalize_so_hieu(so_hieu)}:Đ{_check(_DIEU_RE, so.lower(), 'Số điều')}"


def khoan_id(dieu: str, so: str) -> str:
    if parse_unit_id(dieu).kind is not UnitKind.DIEU:
        raise ValueError(f"Không phải ID Điều: {dieu!r}")
    return f"{dieu}:K{_check(_KHOAN_RE, so.lower(), 'Số khoản')}"


def diem_id(khoan: str, chu: str) -> str:
    if parse_unit_id(khoan).kind is not UnitKind.KHOAN:
        raise ValueError(f"Không phải ID Khoản: {khoan!r}")
    return f"{khoan}:{_check(_DIEM_RE, nfc(chu).lower(), 'Chữ cái điểm')}"


def version_id(unit_id: str, hieu_luc_tu: date | None) -> str:
    kind = parse_unit_id(unit_id).kind
    if kind not in (UnitKind.DIEU, UnitKind.KHOAN):
        raise ValueError(f"Phiên bản chỉ gắn với Khoản hoặc Điều: {unit_id!r}")
    suffix = hieu_luc_tu.isoformat() if hieu_luc_tu else UNKNOWN_VERSION
    return f"{unit_id}@{suffix}"


def split_version_id(vid: str) -> tuple[str, date | None]:
    unit_id, sep, suffix = vid.rpartition("@")
    if not sep:
        raise ValueError(f"Không phải ID phiên bản: {vid!r}")
    parse_unit_id(unit_id)
    return unit_id, (None if suffix == UNKNOWN_VERSION else date.fromisoformat(suffix))


@dataclass(frozen=True)
class UnitRef:
    so_hieu: str
    chuong: str | None = None
    dieu: str | None = None
    khoan: str | None = None
    diem: str | None = None

    @property
    def kind(self) -> UnitKind:
        if self.chuong:
            return UnitKind.CHUONG
        if self.diem:
            return UnitKind.DIEM
        if self.khoan:
            return UnitKind.KHOAN
        if self.dieu:
            return UnitKind.DIEU
        return UnitKind.VAN_BAN

    @property
    def id(self) -> str:
        if self.chuong:
            return f"{self.so_hieu}:C{self.chuong}"
        parts = [self.so_hieu]
        if self.dieu:
            parts.append(f"Đ{self.dieu}")
        if self.khoan:
            parts.append(f"K{self.khoan}")
        if self.diem:
            parts.append(self.diem)
        return ":".join(parts)


def parse_unit_id(unit_id: str) -> UnitRef:
    """Tách ID thành các thành phần. Ném ValueError nếu sai định dạng."""
    if "@" in unit_id:
        raise ValueError(f"ID phiên bản, không phải ID điều khoản: {unit_id!r}")
    so_hieu, *rest = nfc(unit_id).split(":")
    if not SO_HIEU_RE.match(so_hieu):
        raise ValueError(f"Số hiệu không hợp lệ trong ID: {unit_id!r}")
    if not rest:
        return UnitRef(so_hieu)
    first = rest[0]
    if first.startswith("C") and len(rest) == 1:
        return UnitRef(so_hieu, chuong=_check(_CHUONG_RE, first[1:], "Số chương"))
    if not first.startswith("Đ") or len(rest) > 3:
        raise ValueError(f"ID điều khoản không hợp lệ: {unit_id!r}")
    dieu = _check(_DIEU_RE, first[1:], "Số điều")
    khoan = diem = None
    if len(rest) >= 2:
        if not rest[1].startswith("K"):
            raise ValueError(f"ID điều khoản không hợp lệ: {unit_id!r}")
        khoan = _check(_KHOAN_RE, rest[1][1:], "Số khoản")
    if len(rest) == 3:
        diem = _check(_DIEM_RE, rest[2], "Chữ cái điểm")
    return UnitRef(so_hieu, dieu=dieu, khoan=khoan, diem=diem)


def parent_id(unit_id: str) -> str | None:
    """Điểm → Khoản → Điều → Văn bản; Chương → Văn bản; Văn bản → None.

    Lưu ý: ID Điều không chứa Chương nên cha của Điều (theo ID) là Văn bản.
    """
    ref = parse_unit_id(unit_id)
    match ref.kind:
        case UnitKind.DIEM:
            return UnitRef(ref.so_hieu, dieu=ref.dieu, khoan=ref.khoan).id
        case UnitKind.KHOAN:
            return UnitRef(ref.so_hieu, dieu=ref.dieu).id
        case UnitKind.DIEU | UnitKind.CHUONG:
            return ref.so_hieu
        case UnitKind.VAN_BAN:
            return None
