# M08 – Chỉ mục BM25 · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F07 – Lập chỉ mục](../../features/F07-lap-chi-muc.md) – phần BM25 (BR-07.5 → BR-07.7) |
| Giai đoạn | PoC – tuần 4 (làm song song M07 được) |
| Ước lượng | 2 ngày |
| Phụ thuộc | M06 (`index_outbox`), M00 (ES có ICU) |
| Module dùng kết quả | M07 (BR-10.4), M09 (fallback LOCAL ở PoC), M12, M13 |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Mỗi `PhienBan` là một document Elasticsearch, đồng bộ tăng dần từ `index_outbox`, tìm được cả khi gõ không dấu, lọc hiệu lực bằng range query. Văn bản chuyển `INDEXED` để dùng cho hỏi đáp.

## 2. Phạm vi

| Trong M08 | Để M12 |
|---|---|
| Index `phien_ban` (mapping F07 §6.1) | Embedding (`parts: embedding`) |
| Đồng bộ `incremental` (outbox) và `full` (toàn bộ Neo4j) | Phân cụm, tóm tắt (`parts: communities`) |
| Hàm tìm `bm25_search` dùng chung | |
| `index_run`, `/index/runs`, `/index/status` | `/topics` |

## 3. Thiết kế

### 3.1. Cấu trúc file

```text
backend/app/indexing/
├── models.py          # ORM index_run
├── es_mapping.py      # settings + mappings (F07 §6.1), tên index qua alias
├── docs.py            # build_es_doc(phien_ban, owner, van_ban) → dict
├── bm25_sync.py       # consume outbox → _bulk; full rebuild
├── bm25_search.py     # bm25_search(query, ngay, so_hieu=[], tu_khoa=[], k=30) → list[Hit]
├── runner.py          # handler job "index" – điều phối parts
└── router.py          # /index/runs, /index/status
```

### 3.2. Index và alias

- Index vật lý `phien_ban_v1`, alias `phien_ban` → đổi mapping sau này bằng cách tạo `phien_ban_v2`, reindex, chuyển alias (không downtime).
- `ensure_index()` khi khởi động: tạo nếu chưa có.

### 3.3. Document

| Trường | Nguồn |
|---|---|
| `_id`, `phien_ban_id` | `PhienBan.id` |
| `unit_id` | owner id |
| `so_hieu`, `loai_van_ban` | `VanBan` |
| `label` | `legal/labels.label(owner_id)` |
| `noi_dung` (+ `.folded`) | `PhienBan.noi_dung` – tiền tố tiêu đề Điều để BM25 có ngữ cảnh: `"Điều {so}. {tieu_de}\n{noi_dung}"` |
| `hieu_luc_tu` | `PhienBan.hieu_luc_tu` |
| `hieu_luc_den` | `PhienBan.hieu_luc_den` hoặc `9999-12-31` (BR-07.7) |
| `chu_de`, `doi_tuong` | `THUOC_CHU_DE` / `AP_DUNG_CHO` của Điều cha |
| `cum_id` | trống ở PoC (M12) |

Lưu ý: điều kiện "văn bản chứa còn hiệu lực" (BR-13.1b) **không** mã hóa trong ES; kết quả ES luôn đi qua `EffectivityService.filter()`. Khi `THAY_THE` đóng phiên bản (M06 §3.5), outbox đã có `upsert` nên `hieu_luc_den` trong ES được cập nhật.

### 3.4. Đồng bộ

```text
incremental:
  rows = SELECT … FROM index_outbox WHERE processed_at IS NULL ORDER BY id LIMIT 500 FOR UPDATE SKIP LOCKED
  upsert → đọc PhienBan + owner + VanBan từ Neo4j theo lô (UNWIND), build_es_doc
  delete → _bulk delete (404 bỏ qua)
  _bulk, kiểm tra lỗi từng item; item lỗi → giữ processed_at NULL, ghi stats.failed
  UPDATE index_outbox SET processed_at = now() cho item thành công
full:
  duyệt mọi PhienBan trong Neo4j theo lô 500 → upsert; xóa doc ES không còn trong Neo4j
```

Sau khi đồng bộ: văn bản `CONSOLIDATED` mà mọi phiên bản đã có trong ES → `INDEXED`, cập nhật `source_document.indexed_at` **(cột của F15, thêm sớm ở M08)**. Ở MVP, điều kiện `INDEXED` thêm "không còn phiên bản `embedding_stale`" (M12).

Retry ES lỗi 3 lần (F07 UC-07.1 ngoại lệ 3a), sau đó `index_run.status = FAILED`.

### 3.5. Tìm kiếm

```python
async def bm25_search(query: str, ngay: date, *, so_hieu: list[str] = [], tu_khoa: list[str] = [],
                      chu_de: list[str] = [], doi_tuong: list[str] = [], k: int = 30) -> list[Hit]:
    # multi_match trên noi_dung, noi_dung.folded, label^0.5
    # tu_khoa → should match_phrase boost 2 (BR-11.1)
    # chu_de / doi_tuong → should terms boost nhỏ (BR-11.4: boost, không lọc cứng)
    # filter range hieu_luc_tu <= d < hieu_luc_den; terms so_hieu nếu có
```

Trả `Hit(phien_ban_id, unit_id, so_hieu, score, highlight)`. Dùng ở M07 (`RelatedSearch`), M09 (fallback LOCAL PoC), M13 (một nhánh hybrid).

### 3.6. Schema & API

- Migration `0007_index`: `index_run` (F07 §6.3); `ALTER TABLE source_document ADD COLUMN indexed_at TIMESTAMPTZ`.
- `POST /index/runs {"mode": "incremental"|"full", "parts": ["bm25"]}`; `GET /index/runs/{id}`; `GET /index/status` (PoC: `phien_ban_total`, `es_documents`, `outbox_pending`; MVP thêm stale / cụm).

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M08-T1 | Mapping + alias + `ensure_index` | 3.2; kiểm tra analyzer bằng `_analyze` | 07.6 | 0.25 ngày |
| M08-T2 | `build_es_doc` | 3.3 | 07.5, 07.7 | 0.25 ngày |
| M08-T3 | Sync incremental + full | 3.4 | 07.5 | 0.5 ngày |
| M08-T4 | Runner + `INDEXED` | 3.4 | – | 0.25 ngày |
| M08-T5 | `bm25_search` | 3.5 | 11.1, 11.3, 11.4 | 0.5 ngày |
| M08-T6 | Migration + API | 3.6 | – | 0.25 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Tích hợp | `_analyze` với `vi_folded`: "hủy hóa đơn" và "huy hoa don" ra cùng token |
| Tích hợp | Sau M06 trên bộ PoC + `index` → số doc ES = số `PhienBan`; `outbox_pending = 0` |
| Tích hợp | Tìm "huy hoa don" ngày 2025-03-15 → top có `123/2020/NĐ-CP:Đ3:K10`; ngày 2026-11-18 → không có (đã hết hiệu lực) |
| Tích hợp | Thu hồi cạnh → outbox `delete` → doc ES bị xóa |
| Tích hợp | Chạy `full` 2 lần → số doc không đổi |
| Tích hợp | ES tắt → retry rồi `FAILED`, outbox giữ nguyên |

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| ICU tokenizer tách từ ghép tiếng Việt theo âm tiết | Chấp nhận ở PoC (BM25 theo âm tiết vẫn hoạt động); thêm `match_phrase` cho `tu_khoa`; có thể thử `shingle` ở MVP |
| Outbox phình nếu ES tắt lâu | `outbox_pending` hiển thị trên `/index/status`; chạy `full` khi cần |

## 7. Bàn giao

- `bm25_search` là API dùng chung; M13 không gọi ES trực tiếp.
- M12 mở rộng runner với `parts: embedding, communities` và điều kiện `INDEXED` mới.
