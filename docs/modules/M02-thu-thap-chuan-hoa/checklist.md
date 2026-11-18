# M02 – Thu thập & chuẩn hóa (không OCR) · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F01](../../features/F01-thu-thap-van-ban.md), [F02](../../features/F02-chuan-hoa-ocr.md)

## Chuẩn bị

- [ ] M02-T1 Khảo sát `vanban.chinhphu.vn`: trang tìm kiếm, trang chi tiết, file đính kèm, `robots.txt` – ghi vào `docs/spikes/nguon-vanban.md`
- [ ] M02-T1 Tải tay 5 văn bản inception (NĐ 123/2020, NĐ 70/2025, TT 78/2021, TT 32/2025, NQ 198/2025)
- [ ] M02-T1 Chọn thêm 5–15 văn bản (hóa đơn điện tử + thuế hộ kinh doanh), ưu tiên DOCX / PDF có text
- [ ] M02-T1 `tests/fixtures/documents/manifest.yaml` có số hiệu, loại, ngày ban hành, ngày hiệu lực kỳ vọng

## Triển khai – thu thập (F01)

- [ ] M02-T2 Migration `0003_ingest` (F01 §6, F02 §6, `source_document_event`, FK `pipeline_job`)
- [ ] M02-T2 `status.transition()` chặn chuyển trạng thái sai 00-common §5 và ghi event
- [ ] M02-T2 Seed `crawl_source` `vanban.chinhphu.vn`
- [ ] M02-T3 `PoliteClient`: ≤ 1 req/s, `robots.txt`, retry 2/4/8 s, User-Agent định danh
- [ ] M02-T4 Adapter: tìm theo số hiệu seed và từ khóa; đọc metadata nguồn vào `metadata_nguon`
- [ ] M02-T4 Lọc phạm vi theo loại văn bản (BR-01.3) và từ khóa / seed (BR-01.2)
- [ ] M02-T4 Chọn file ưu tiên DOCX > PDF text > PDF scan > ảnh; lưu URL file khác
- [ ] M02-T5 Chống trùng SHA-256 (`last_seen_at`); cùng số hiệu khác hash → `revision_of` + `NEEDS_ATTENTION`
- [ ] M02-T5 Lưu `raw/{yyyy}/{sha256}.{ext}` ghi atomic, không ghi đè
- [ ] M02-T5 `crawl_job.stats` (pages, found, new, duplicate, skipped, failed) + `crawl_job_item`
- [ ] M02-T5 > 10 lỗi 429/5xx liên tiếp → `PAUSED`; hủy job hoạt động
- [ ] M02-T5 Văn bản mới → `enqueue("normalize")`
- [ ] M02-T6 Upload: PDF / DOCX / PNG / JPG, ≤ 50 MB (kiểm tra theo stream + magic bytes); trùng → `duplicate: true`

## Triển khai – chuẩn hóa (F02, không OCR)

- [ ] M02-T7 Trích DOCX (python-docx) và PDF (PyMuPDF), trang < 50 ký tự đánh dấu scan
- [ ] M02-T8 Phát hiện + chuyển TCVN3 / VNI → Unicode
- [ ] M02-T8 NFC toàn văn bản
- [ ] M02-T8 Bỏ quốc hiệu, tiêu ngữ, header / footer lặp, số trang, "Nơi nhận", khối chữ ký, "(Đã ký)"; ghi `removed_sections`
- [ ] M02-T8 Giữ số hiệu, ngày, trích yếu, "Căn cứ…", thân văn bản, phụ lục (`is_phu_luc`)
- [ ] M02-T8 Nối dòng ngắt giữa câu, không nối trước Chương / Điều / Khoản / Điểm; giữ `“ ”`
- [ ] M02-T9 Đọc số hiệu từ nội dung, lệch metadata → `NEEDS_ATTENTION` (`SO_HIEU_MISMATCH`)
- [ ] M02-T9 Trang scan / ảnh → warning `OCR_REQUIRED`, `NEEDS_ATTENTION`
- [ ] M02-T9 Ghi `.txt` + `.blocks.json` + `normalized_document`, lưu `normalizer_version`, `enqueue("parse")`
- [ ] M02-T10 Đủ 10 endpoint ở plan §3.5

## Kiểm thử

- [ ] Unit cleanup (quốc hiệu, nơi nhận, chữ ký bị bỏ; "Căn cứ" giữ lại)
- [ ] Unit whitespace (không nối trước `Điều`, `2.`, `a)`)
- [ ] Unit bảng mã cũ
- [ ] Unit rate limit + retry (respx)
- [ ] Tích hợp crawl seed trên HTML fixture (không gọi mạng trong CI)
- [ ] Tích hợp chuẩn hóa toàn bộ fixture, NFC, chạy 2 lần cho cùng kết quả

## Tiêu chí chấp nhận (F01 §7, F02 §7 trừ OCR)

- [ ] Seed 5 số hiệu inception → đủ 5 `source_document` `FETCHED`
- [ ] Chạy lại cùng job → 0 bản ghi mới, `duplicate = 5`
- [ ] Rate limit đo được ≤ 1 request/giây
- [ ] Upload PDF 60 MB → 422
- [ ] DOCX và PDF có text của NĐ 123/2020, NĐ 70/2025 → không còn quốc hiệu, nơi nhận, chữ ký
- [ ] Toàn bộ văn bản đầu ra ở dạng NFC
- [ ] Chạy lại 2 lần trên cùng file → văn bản đầu ra giống hệt nhau
- [ ] *(Hoãn sang M11)* PDF scan mẫu có OCR, ghi `ocr_confidence_avg`

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Toàn bộ fixture ở trạng thái `NORMALIZED` (hoặc `NEEDS_ATTENTION` có lý do ghi rõ)
