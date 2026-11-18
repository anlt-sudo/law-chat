"""Model dùng chung giữa các feature (00-common §7)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class TrangThaiHieuLuc(StrEnum):
    CON_HIEU_LUC = "con_hieu_luc"
    HET_HIEU_LUC = "het_hieu_luc"
    CHUA_CO_HIEU_LUC = "chua_co_hieu_luc"
    KHONG_XAC_DINH = "khong_xac_dinh"


class TrangThaiVanBan(StrEnum):
    """Trạng thái văn bản (F06 BR-06.10)."""

    CON_HIEU_LUC = "con_hieu_luc"
    HET_HIEU_LUC_MOT_PHAN = "het_hieu_luc_mot_phan"
    HET_HIEU_LUC = "het_hieu_luc"
    CHUA_CO_HIEU_LUC = "chua_co_hieu_luc"


LoaiThayDoi = Literal[
    "BAI_BO", "SUA_DOI", "THAY_THE", "VAN_BAN_HET_HIEU_LUC", "CHUA_CO_HIEU_LUC", "KHONG_XAC_DINH"
]


class ThayDoi(BaseModel):
    loai: LoaiThayDoi
    boi_unit_id: str | None = None  # điều khoản / văn bản gây ra thay đổi
    boi_label: str | None = None  # "khoản 4 Điều 2 NĐ 70/2025/NĐ-CP"
    tu_ngay: date | None = None


class Citation(BaseModel):
    ref: str  # "C1"
    unit_id: str
    label: str  # "khoản 10 Điều 3 Nghị định 123/2020/NĐ-CP"
    so_hieu: str
    phien_ban_id: str | None = None
    hieu_luc_tu: date | None = None
    hieu_luc_den: date | None = None
    trang_thai: TrangThaiHieuLuc
    thay_doi: ThayDoi | None = None  # có khi điều khoản đã bị sửa / bãi bỏ
    trich_doan: str
    url_nguon: str | None = None
