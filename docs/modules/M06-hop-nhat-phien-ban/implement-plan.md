# M06 – Hợp nhất phiên bản (cơ bản) · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F06 – Hợp nhất phiên bản](../../features/F06-hop-nhat-phien-ban.md) – phần PoC + `THAY_THE` cấp văn bản |
| Giai đoạn | PoC – tuần 3 |
| Ước lượng | 3–4 ngày |
| Phụ thuộc | M03, M05 |
| Module dùng kết quả | M07, M08, M11 (cấp điểm), M12, M16 |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Áp các cạnh đã duyệt theo thời gian để mỗi Khoản (hoặc Điều không khoản) có chuỗi `PhienBan` liên tiếp, không chồng lấn, kèm `hieu_luc_tu` / `hieu_luc_den`; cập nhật `VanBan.hieu_luc_den` và `trang_thai`. Kết quả xác định: chạy lại bao nhiêu lần cũng như nhau.

## 2. Phạm vi

| Trong M06 | Để M11 |
|---|---|
| `SUA_DOI` cả Khoản / Điều không khoản | `SUA_DOI` một Điểm |
| `BAI_BO` Khoản, `BAI_BO` Điều (đóng mọi Khoản) | `BO_SUNG` Điểm / Khoản / Điều (tạo node mới) |
| `THAY_THE` cấp văn bản (cần cho F13 thứ tự 1, Q4, TT 78) | `BAI_BO` một Điểm |
| BR-06.1 → BR-06.8, BR-06.10, BR-06.11 | BR-06.9 (`DIEM_NOT_FOUND`) |
| Văn bản không có sửa đổi: chỉ phiên bản GOC, vẫn `CONSOLIDATED` | |

Sự kiện thuộc phần M11 gặp trong PoC → bỏ qua, cảnh báo `NOT_SUPPORTED_YET`.

## 3. Thiết kế

### 3.1. Cấu trúc file

```text
backend/app/consolidation/
├── models.py        # ORM consolidation_run, index_outbox; dataclass Event, Version
├── scope.py         # unit_ids / so_hieu / all → danh sách owner (Khoản, Điều không khoản)
├── events.py        # đọc cạnh đã duyệt tới owner + Điều cha + Điểm con; ghép noi_dung_moi, thu_tu từ PG
├── rebuild.py       # rebuild_versions(goc, events) – hàm thuần, không I/O
├── apply.py         # apply_event(content, ev) – PoC: thay cả khoản
├── diff_write.py    # so chuỗi mới với chuỗi trong Neo4j theo id + content_hash; ghi transaction
├── doc_status.py    # THAY_THE cấp văn bản; trang_thai văn bản (BR-06.10)
├── invariants.py    # truy vấn kiểm tra chồng lấn / đứt quãng
├── runner.py        # handler job "consolidate"
└── router.py        # /consolidation/runs, /units/versions
```

### 3.2. Phạm vi owner

| Đầu vào | Owner được dựng lại |
|---|---|
| `unit_id` là Khoản | Khoản đó |
| `unit_id` là Điểm | Khoản cha |
| `unit_id` là Điều có khoản | Mọi Khoản của Điều |
| `unit_id` là Điều không khoản | Điều đó |
| `so_hieu` | Mọi owner của văn bản đó **và** mọi owner là đích của cạnh đi ra từ văn bản đó |
| `all: true` | Mọi owner trong đồ thị (chạy theo lô 200) |

### 3.3. Dựng lại chuỗi phiên bản

Hàm thuần theo giả mã F06 §6.3:

```python
@dataclass(frozen=True)
class Event:
    loai: Literal["SUA_DOI", "BAI_BO"]; kieu: str | None
    target_id: str; target_label: str      # Khoan | Dieu | Diem
    tu_ngay: date; nguon_id: str; nguon_ban_hanh: date; nguon_so_hieu: str
    thu_tu: int; noi_dung_moi: str | None; candidate_id: int

def rebuild_versions(owner_id, goc: Version, events: list[Event]) -> RebuildResult:
    # sắp (tu_ngay, nguon_ban_hanh, thu_tu)            – BR-06.6
    # cùng tu_ngay, khác nguon_so_hieu → conflict, dừng owner   – BR-06.7
    # phiên bản cuối đã đóng → TARGET_ALREADY_REPEALED, bỏ qua – BR-06.8
    # BAI_BO (owner hoặc Điều cha) → đóng tại tu_ngay
    # SUA_DOI cả owner → đóng, mở phiên bản mới loai_thay_doi=SUA_DOI, nguon_sua_doi=nguon_id
    # tu_ngay <= goc.hieu_luc_tu (hồi tố trước cả GOC) → cảnh báo, áp như bình thường
```

- ID phiên bản = `<owner_id>@<hieu_luc_tu>`; `content_hash = sha256(NFC(noi_dung))`.
- Hai sự kiện cùng ngày, cùng nguồn (BR-06.7) → áp tuần tự, chỉ phiên bản cuối cùng của ngày đó được giữ (các phiên bản trung gian độ dài 0 bị bỏ).
- `tu_ngay` tương lai (BR-06.5) → phiên bản "sắp có hiệu lực", không đặc biệt gì thêm.

### 3.4. Ghi Neo4j (BR-06.2, BR-06.4)

Mỗi owner một write transaction:

1. Đọc chuỗi hiện có `(owner)-[:CO_PHIEN_BAN]->(pb)`.
2. So với chuỗi mới theo `id`:
   - Cùng `id`, cùng `content_hash` → chỉ `SET hieu_luc_den`, `loai_thay_doi`, `nguon_sua_doi` (giữ `embedding`).
   - Cùng `id`, khác hash → `SET noi_dung`, `content_hash`, `embedding_stale = true`.
   - Mới → `CREATE` + `embedding_stale = true`.
   - Thừa → `DETACH DELETE`.
3. **(bổ sung)** ghi `index_outbox` (PG) cho phiên bản `upsert` (mới / đổi nội dung / đổi khoảng hiệu lực) và `delete`, để M08 đồng bộ ES và M12 biết cụm dirty.

```sql
CREATE TABLE index_outbox (
    id            BIGSERIAL PRIMARY KEY,
    phien_ban_id  TEXT NOT NULL,
    owner_id      TEXT NOT NULL,
    op            TEXT NOT NULL CHECK (op IN ('upsert','delete')),
    run_id        UUID,                   -- consolidation_run
    processed_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON index_outbox (processed_at) WHERE processed_at IS NULL;
```

### 3.5. Cấp văn bản

- `THAY_THE` đã duyệt `A → B` với `tu_ngay = d`: `B.hieu_luc_den = d` (lấy nhỏ nhất nếu nhiều cạnh); đóng mọi phiên bản đang mở của B tại `d` (đi qua cùng `diff_write` để có outbox).
- `trang_thai` (BR-06.10) cho hôm nay (`today_vn()`): `het_hieu_luc` nếu `hieu_luc_den <= hôm nay`; `chua_co_hieu_luc` nếu `hieu_luc_tu > hôm nay`; `het_hieu_luc_mot_phan` nếu ≥ 1 owner không có phiên bản hiệu lực hôm nay; còn lại `con_hieu_luc`. Hàm này dùng lại ở M16 (làm mới hằng ngày).

### 3.6. Trạng thái pipeline

- Văn bản nguồn của các cạnh trong phạm vi + văn bản đích → `CONSOLIDATED` (nếu đang `REVIEWED` hoặc `INDEXED`; `INDEXED` → `CONSOLIDATED` để M08 lập chỉ mục lại).
- Ghi `consolidation_run` (F06 §6.2) với `stats {units, versions_created, versions_updated, versions_deleted, versions_closed}`, `warnings`, `conflicts`.
- `enqueue("index", {"mode": "incremental"}, dedupe_key="index:incremental")`.

### 3.7. API

Theo F06 §5. `GET /units/versions` dùng chung với M07: phiên bản sắp theo `hieu_luc_tu`, `events` lấy từ cạnh đến owner / Điều cha / Điểm con, có `boi_label` (từ `legal/labels.py`).

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M06-T1 | Migration | `consolidation_run`, `index_outbox` | – | 0.25 ngày |
| M06-T2 | `scope.py` + `events.py` | 3.2; truy vấn F06 §6.1 dùng label `:DonVi` | 06.1 | 0.5 ngày |
| M06-T3 | `rebuild.py` + `apply.py` | 3.3 – hàm thuần, test kỹ nhất module | 06.2, 06.3, 06.5–06.8 | 1 ngày |
| M06-T4 | `diff_write.py` + outbox | 3.4 | 06.4 | 0.5 ngày |
| M06-T5 | `doc_status.py` | 3.5 | 06.10, 06.11 | 0.5 ngày |
| M06-T6 | Runner + trạng thái pipeline | 3.6 | – | 0.25 ngày |
| M06-T7 | `invariants.py` | Truy vấn: hai phiên bản giao nhau; `pb[i].den != pb[i+1].tu`; phiên bản `tu >= den` | 06.3 | 0.25 ngày |
| M06-T8 | API | `/consolidation/runs`, `/units/versions` | – | 0.25 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit `rebuild` | Không sự kiện; 1 bãi bỏ; 2 sửa đổi khác ngày; bãi bỏ rồi sửa (bỏ qua + cảnh báo); 2 sự kiện cùng ngày cùng nguồn; cùng ngày khác nguồn (conflict); bãi bỏ Điều cha; ngày tương lai |
| Unit (property-based, `hypothesis`) | Sinh ngẫu nhiên chuỗi sự kiện → chuỗi phiên bản luôn liên tiếp, không chồng lấn, `rebuild` hai lần cho cùng kết quả |
| Tích hợp | Sau duyệt NĐ 70: `…:Đ3:K10` có đúng 1 phiên bản `[2022-07-01, 2025-06-01)`; `…:Đ19:K1` có 2 phiên bản |
| Tích hợp | TT 78/2021 `hieu_luc_den = 2025-06-01`, `trang_thai = het_hieu_luc` |
| Tích hợp | Chạy 2 lần liên tiếp → lần 2 `versions_created = 0`, `versions_deleted = 0`, không có outbox mới |
| Tích hợp | Thu hồi cạnh (M05) → phiên bản sửa đổi biến mất, outbox có `delete` |
| Tích hợp | `invariants` trên toàn đồ thị PoC trả 0 dòng |
| Đồng hồ | `APP_FAKE_TODAY=2025-03-15` → NĐ 70 `chua_co_hieu_luc`, TT 78 `con_hieu_luc` |

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| `noi_dung_moi` là cả Điều (sửa đổi cả Điều có nhiều khoản) trong khi phiên bản gắn ở Khoản | PoC: tách `noi_dung_moi` của Điều thành các Khoản bằng `parsing/structure.py`, khớp theo số khoản; khoản thừa / thiếu → cảnh báo `ARTICLE_SPLIT_MISMATCH`, khoản mới để M11 (`BO_SUNG`) |
| Xung đột chỉ phát hiện ở đây (F05 sót) | Ghi `conflicts`, không ghi owner đó, hiển thị trên `/consolidation/runs/{id}` |
| `hieu_luc_tu` GOC = NULL | Không dựng được chuỗi → bỏ qua owner, cảnh báo `MISSING_EFFECTIVE_DATE` |
| `all: true` chậm | Chạy theo lô, transaction theo owner |

## 7. Bàn giao

- `index_outbox` là nguồn sự kiện cho M08 (ES) và M12 (embedding, cụm dirty).
- `doc_status.compute_trang_thai(so_hieu, today)` dùng lại ở M16.
- `rebuild.py` được thiết kế để M11 thêm các nhánh cấp Điểm và `BO_SUNG` mà không đổi interface.
