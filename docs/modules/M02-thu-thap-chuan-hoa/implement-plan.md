# M02 – Thu thập & chuẩn hóa văn bản (không OCR) · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F01 – Thu thập](../../features/F01-thu-thap-van-ban.md), [F02 – Chuẩn hóa](../../features/F02-chuan-hoa-ocr.md) (trừ OCR) |
| Giai đoạn | PoC – tuần 1–2 |
| Ước lượng | 4–5 ngày |
| Phụ thuộc | M00 |
| Module dùng kết quả | M03, M11 (OCR), M16 (crawl tăng dần) |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Đưa 10–20 văn bản mảng hóa đơn điện tử (và vài văn bản thuế hộ kinh doanh) vào hệ thống: file gốc lưu bất biến, `source_document` qua `FETCHED` → `NORMALIZED`, văn bản thuần sạch + `blocks.json` sẵn sàng cho M03.

## 2. Phạm vi

| Trong M02 | Để sau |
|---|---|
| Crawler `vanban.chinhphu.vn` chế độ `seed` (danh sách số hiệu) | Chế độ `incremental` + watermark (M16) – nhưng code crawler phải nhận `from_date` ngay từ đầu |
| Import thủ công PDF / DOCX (ảnh nhận file nhưng đánh dấu cần OCR) | OCR PaddleOCR / Tesseract (M11) |
| Chuẩn hóa DOCX, PDF có text: NFC, bỏ quốc hiệu / header / footer / số trang / nơi nhận / chữ ký, nối dòng | |
| Phát hiện bảng mã cũ TCVN3 / VNI và chuyển đổi | |
| Đối chiếu số hiệu đọc được với metadata nguồn | |
| Bộ fixture văn bản mẫu cho toàn dự án | |

## 3. Thiết kế

### 3.1. Cấu trúc file

```text
backend/app/ingest/
├── models.py              # ORM crawl_source, crawl_job, crawl_job_item, source_document,
│                          #     source_document_event, normalized_document
├── status.py              # DocStatus enum + transition(doc, to, reason) – kiểm tra hợp lệ theo 00-common §5
├── crawler/
│   ├── base.py            # SourceAdapter Protocol: search(seed|keywords, from_date) → DocRef; detail(ref) → DocMeta
│   ├── chinhphu.py        # adapter vanban.chinhphu.vn (selector trong crawl_source.config)
│   ├── http.py            # PoliteClient: rate limit 1 req/s, robots.txt, retry 2/4/8 s, User-Agent
│   ├── scope.py           # in_scope(meta) – BR-01.2, BR-01.3
│   └── runner.py          # handler job "crawl": vòng lặp UC-01.1, thống kê
├── upload.py              # UC-01.2
├── dedupe.py              # sha256, kiểm tra trùng hash / cùng số hiệu (BR-01.5, BR-01.6)
├── normalize/
│   ├── extract_docx.py    # python-docx: đoạn + style (bold / căn giữa)
│   ├── extract_pdf.py     # PyMuPDF: block theo trang; đánh dấu trang < 50 ký tự là scan
│   ├── legacy_encoding.py # phát hiện + chuyển TCVN3 / VNI → Unicode
│   ├── cleanup.py         # bỏ quốc hiệu, header/footer lặp, số trang, nơi nhận, chữ ký
│   ├── whitespace.py      # gộp khoảng trắng, nối dòng ngắt giữa câu (BR-02.4)
│   ├── so_hieu.py         # đọc số hiệu từ nội dung (regex BR-03.1)
│   └── runner.py          # handler job "normalize"
└── router.py              # /api/v1/ingest/...
backend/tests/fixtures/documents/
├── manifest.yaml          # so_hieu, file, nguồn, ghi chú, kỳ vọng
└── *.docx | *.pdf
```

### 3.2. Schema PostgreSQL (migration `0003_ingest`)

- `crawl_source`, `crawl_job`, `crawl_job_item`, `source_document` đúng F01 §6.
- `normalized_document` đúng F02 §6.
- Thêm FK `pipeline_job.source_document_id → source_document(id)`.
- **(bổ sung)** lịch sử trạng thái cho API "chi tiết + lịch sử trạng thái":

```sql
CREATE TABLE source_document_event (
    id                 BIGSERIAL PRIMARY KEY,
    source_document_id UUID NOT NULL REFERENCES source_document(id),
    from_status        TEXT,
    to_status          TEXT NOT NULL,
    reason             TEXT,
    actor              TEXT NOT NULL,          -- 'worker:normalize' | api_key id
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- Seed `crawl_source('vanban.chinhphu.vn', base_url, rate_limit_ms=1000, config={keywords, loai, selectors})`.

### 3.3. Crawler

| Vấn đề | Cách làm |
|---|---|
| Cấu trúc trang nguồn chưa biết | **Spike M02-T1** trước khi code adapter: xem trang tìm kiếm, trang chi tiết, link file đính kèm, metadata hiển thị; ghi selector vào `crawl_source.config` để sửa không cần deploy |
| Lịch sự với nguồn (BR-01.4) | `PoliteClient` dùng một `asyncio.Lock` + thời điểm request cuối, bảo đảm ≥ `rate_limit_ms` giữa 2 request; đọc `robots.txt` một lần mỗi job (`urllib.robotparser`); retry 3 lần backoff 2 / 4 / 8 s; > 10 lỗi 429/5xx liên tiếp → job `PAUSED` |
| Chọn file (BR-01.9) | Xếp hạng `docx > pdf (có text) > pdf scan > ảnh`; "PDF có text" chỉ biết sau khi tải → tải PDF trước, nếu toàn trang scan và có bản khác thì thử bản kế; ghi URL các file còn lại vào `metadata_nguon.other_files` |
| Trùng (BR-01.5, 01.6) | Trùng `sha256` → `last_seen_at = now()`, item `duplicate`. Cùng `so_hieu_nguon`, khác hash → bản mới `revision_of`, trạng thái `NEEDS_ATTENTION`, item `revision` |
| Lưu file (BR-01.7) | `raw/{yyyy}/{sha256}.{ext}`; ghi file tạm rồi `rename` (atomic); file đã tồn tại → không ghi lại |
| Hủy job | API `cancel` đặt `CANCELLED`; runner kiểm tra trạng thái giữa các văn bản |
| Phương án dự phòng | Nếu adapter mất > 1.5 ngày: PoC dùng **import thủ công** cho bộ fixture, crawler hoàn thiện song song (không chặn M03) |

### 3.4. Chuẩn hóa

Thứ tự xử lý (xác định, BR-02.9 – không phụ thuộc thời gian / ngẫu nhiên):

1. Trích block: DOCX → mỗi đoạn một block (`page = None`, giữ cờ `bold`, `center`); PDF → block PyMuPDF theo trang, sắp theo `(page, y, x)`.
2. Phát hiện bảng mã cũ trên toàn văn bản: tỷ lệ ký tự đặc trưng TCVN3 (`¸ µ ¶ · ¹ ¨ ©`…) hoặc VNI (`aù aø aû` dạng tổ hợp) vượt ngưỡng → chuyển bằng bảng ánh xạ.
3. `unicodedata.normalize("NFC", …)`.
4. Bỏ thành phần không mang nội dung (BR-02.6), ghi `removed_sections`:
   - Quốc hiệu, tiêu ngữ: dòng khớp `CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM`, `Độc lập - Tự do - Hạnh phúc`, gạch dưới.
   - Header / footer lặp: dòng (sau khi bỏ số) xuất hiện ở ≥ 50% số trang, vị trí đầu / cuối trang.
   - Số trang: dòng chỉ gồm số hoặc `Trang x/y`.
   - "Nơi nhận:" đến hết khối (thường sau Điều cuối).
   - Khối chữ ký: các dòng sau Điều cuối bắt đầu bằng `TM.`, `KT.`, `Q.`, `TL.`, chức danh in hoa (`THỦ TƯỚNG`, `BỘ TRƯỞNG`, `CHỦ TỊCH QUỐC HỘI`…) + họ tên; dấu `(Đã ký)`.
5. Giữ (BR-02.7): số hiệu, ngày, trích yếu, "Căn cứ…", thân văn bản, phụ lục (block sau dòng `PHỤ LỤC` → `is_phu_luc = true`).
6. Khoảng trắng (BR-02.4): gộp dấu cách; nối dòng khi dòng trước không kết thúc bằng `.`, `:`, `;` **và** dòng sau bắt đầu bằng chữ thường; **không** nối nếu dòng sau mở đầu Điều / Khoản / Điểm / Chương; giữ nguyên `“ ”` (BR-02.5).
7. Đọc số hiệu từ nội dung, so với `metadata_nguon.so_hieu` (bỏ khác biệt khoảng trắng / hoa thường) → lệch thì `NEEDS_ATTENTION` + warning `SO_HIEU_MISMATCH`.
8. Ghi `normalized/{source_document_id}.txt`, `normalized/{source_document_id}.blocks.json`, upsert `normalized_document`, chuyển trạng thái, `enqueue("parse", dedupe_key=f"parse:{id}")`.

Trang PDF scan / file ảnh ở PoC: không OCR, ghi warning `OCR_REQUIRED`, trạng thái `NEEDS_ATTENTION` (M11 sẽ xử lý).

### 3.5. API

Theo F01 §5 và F02 §5:

| Method | Endpoint | Vai trò |
|---|---|---|
| POST | `/api/v1/ingest/crawl-jobs` | quan_tri |
| GET | `/api/v1/ingest/crawl-jobs/{job_id}` | quan_tri |
| POST | `/api/v1/ingest/crawl-jobs/{job_id}/cancel` | quan_tri |
| POST | `/api/v1/ingest/uploads` | bien_tap_vien |
| GET | `/api/v1/ingest/source-documents` | bien_tap_vien |
| GET | `/api/v1/ingest/source-documents/{id}` | bien_tap_vien (kèm `events` từ `source_document_event`) |
| GET | `/api/v1/ingest/source-documents/{id}/raw` | bien_tap_vien |
| POST | `/api/v1/ingest/source-documents/{id}/normalize` | bien_tap_vien |
| GET | `/api/v1/ingest/source-documents/{id}/normalized` | bien_tap_vien |
| GET | `/api/v1/ingest/source-documents/{id}/normalized.txt` | bien_tap_vien |

Upload: kiểm tra đuôi + magic bytes (`%PDF`, `PK` cho DOCX, PNG/JPEG header), giới hạn 50 MB đọc theo stream (không nạp hết vào RAM trước khi kiểm tra kích thước).

### 3.6. Bộ fixture văn bản (dùng cho cả dự án)

| Số hiệu | Vai trò trong test |
|---|---|
| `123/2020/NĐ-CP` | Văn bản gốc; Q1, Q4, Q5 |
| `70/2025/NĐ-CP` | Sửa đổi / bãi bỏ NĐ 123; khối trích dẫn “…” |
| `78/2021/TT-BTC` | Bị thay thế; Q4 (ngày quá khứ) |
| `32/2025/TT-BTC` | Thay thế TT 78, hướng dẫn NĐ 123 / NĐ 70 |
| `198/2025/QH15` | Hiệu lực riêng từng phần (01/01/2026) |
| 5–15 văn bản khác | Hóa đơn điện tử + thuế hộ kinh doanh, do nhóm chọn trong M02-T1 |

`manifest.yaml` ghi kỳ vọng tối thiểu (số hiệu, loại, ngày ban hành, ngày hiệu lực) để test M02 / M03 so sánh tự động.

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M02-T1 | Spike nguồn + chọn fixture | Khảo sát `vanban.chinhphu.vn` (tìm kiếm, chi tiết, file đính kèm, robots.txt); tải tay 5 văn bản inception + chọn thêm văn bản; lập `manifest.yaml` | 01.1–01.3 | 0.5 ngày |
| M02-T2 | Migration + ORM + `status.transition` | 3.2; transition sai luồng → ném lỗi; mỗi transition ghi `source_document_event` | – | 0.5 ngày |
| M02-T3 | `PoliteClient` | Rate limit, robots, retry, User-Agent `LegalGraphBot/0.1 (+dev)` | 01.4 | 0.5 ngày |
| M02-T4 | Adapter `chinhphu` + scope | Search theo số hiệu seed / từ khóa, đọc chi tiết, chọn file ưu tiên | 01.2, 01.3, 01.8, 01.9 | 1 ngày |
| M02-T5 | Runner job `crawl` + dedupe + storage | UC-01.1 đủ luồng thay thế; thống kê `stats`; `PAUSED` khi lỗi liên tục | 01.5–01.7, 01.10 | 0.5 ngày |
| M02-T6 | Upload thủ công | UC-01.2; trả `duplicate: true` + ID cũ khi trùng | – | 0.25 ngày |
| M02-T7 | Trích DOCX / PDF | `extract_docx`, `extract_pdf`, phát hiện trang scan | 02.1 | 0.5 ngày |
| M02-T8 | Bảng mã cũ + NFC + cleanup + whitespace | 3.4 bước 2–6 | 02.3–02.7 | 1 ngày |
| M02-T9 | Đối chiếu số hiệu + runner `normalize` | 3.4 bước 7–8 | 02.8, 02.9 | 0.25 ngày |
| M02-T10 | API | 3.5 | – | 0.5 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit | `cleanup` trên đoạn mẫu: quốc hiệu, nơi nhận, chữ ký `TM. CHÍNH PHỦ / THỦ TƯỚNG / (Đã ký) / Họ tên` bị bỏ; "Căn cứ…" được giữ |
| Unit | `whitespace`: không nối dòng trước `Điều 5.` / `2.` / `a)`; nối dòng ngắt giữa câu |
| Unit | `legacy_encoding`: chuỗi TCVN3 / VNI mẫu → Unicode đúng; văn bản Unicode không bị đổi |
| Unit | `PoliteClient` với `respx`: 5 request liên tiếp cách nhau ≥ 1 s; 503 → retry 3 lần |
| Tích hợp | Crawl seed với adapter dùng HTML fixture lưu sẵn (không gọi mạng trong CI) → 5 `FETCHED`; chạy lại → `duplicate = 5` |
| Tích hợp | Cùng số hiệu, file khác hash → `revision_of` + `NEEDS_ATTENTION` |
| Tích hợp | Chuẩn hóa toàn bộ fixture: mọi output `is_normalized('NFC')`; chạy 2 lần → `sha256` text bằng nhau |
| Thủ công | Crawl thật 5 số hiệu inception (1 lần, ngoài CI) |

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Nguồn đổi giao diện / chặn bot | Selector trong DB; import thủ công là đường dự phòng; lưu HTML mẫu làm fixture |
| Văn bản chỉ có PDF scan | PoC chọn văn bản có DOCX / PDF text; scan để M11 |
| Bỏ nhầm nội dung khi cleanup | Ghi `removed_sections` (loại, trang, số ký tự) để biên tập viên kiểm tra; test trên mọi fixture |
| Bản đính chính trên nguồn có cùng số hiệu | BR-01.6 → `NEEDS_ATTENTION`; xác nhận ở M16 (BR-15.5) |

## 7. Bàn giao

- M03 đọc `normalized_document.text_path` + `blocks_path`; mỗi block có `seq`, `page`, `text`, `is_ocr`, `conf`, `is_phu_luc`.
- M16 dùng lại `runner.crawl` với `mode = incremental`, `from_date`.
- M11 thêm OCR vào `extract_pdf` (trang scan) và file ảnh mà không đổi interface.
