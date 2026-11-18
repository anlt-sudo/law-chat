# M11 – Mở rộng pipeline tri thức · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F02](../../features/F02-chuan-hoa-ocr.md), [F04](../../features/F04-trich-xuat-quan-he.md), [F06](../../features/F06-hop-nhat-phien-ban.md)

## Chuẩn bị

- [ ] Mốc PoC đạt; golden M09 xanh
- [ ] Ít nhất 1 PDF scan + 1 ảnh văn bản mẫu trong fixture
- [ ] Danh sách số hiệu + từ khóa mảng thuế hộ kinh doanh
- [ ] Danh sách câu `manual_required` từ M04 (đầu vào đo tầng LLM)

## Triển khai – OCR (F02)

- [ ] M11-T1 `OcrEngine` Paddle (vi) + Tesseract (`vie`), render trang 300 DPI
- [ ] M11-T1 Image `worker-ocr` riêng, chỉ nhận job `normalize` có `needs_ocr`
- [ ] M11-T2 Block OCR có `is_ocr`, `conf`; gộp vào luồng chuẩn hóa hiện có
- [ ] M11-T2 `ocr_pages`, `ocr_confidence_avg`; < 0.85 → `NEEDS_ATTENTION`
- [ ] M11-T2 Kiểm tra chéo số hiệu + số Điều liên tục; ghim phiên bản model trong `normalizer_version`

## Triển khai – F04 LLM

- [ ] M11-T3 Prompt `extract_relations` (no-think, JSON schema `RelationLLMResponse`)
- [ ] M11-T3 Chỉ gọi cho câu có trigger mà luật không khớp đủ; batch ≤ 5 câu; nhường chat
- [ ] M11-T3 Tham chiếu chữ → ID bằng `legal/refs` (LLM không sinh ID)
- [ ] M11-T3 Số hiệu không có trong câu / ngữ cảnh → bỏ (`LLM_HALLUCINATED_DOC`)
- [ ] M11-T3 conf = min(tự đánh giá, 0.8); JSON lỗi 3 lần → `manual_required`; lưu `llm_call_id`
- [ ] M11-T3 LM Studio lỗi → job hoãn 10 phút, ứng viên tầng 1 vẫn lưu
- [ ] M11-T4 `classify_topics` cho Điều không khớp từ khóa, chỉ mã trong danh mục, `nguon: 'llm'`
- [ ] M11-T4 Không ghi đè cạnh `nguon: 'bien_tap'`

## Triển khai – F06 nâng cao

- [ ] M11-T5 `SUA_DOI` Điểm → phiên bản mới của Khoản cha
- [ ] M11-T5 `BO_SUNG` Điểm (thứ tự chữ cái tiếng Việt, `đ1`), cập nhật `diem[]`, tạo node `Diem`
- [ ] M11-T5 `BAI_BO` Điểm → phiên bản mới đã xóa điểm
- [ ] M11-T5 `BO_SUNG` Khoản / Điều (`Đ9a`) → node mới + phiên bản đầu `BO_SUNG`
- [ ] M11-T5 `DIEM_NOT_FOUND` không tạo phiên bản
- [ ] M11-T5 Sửa cả Điều nhiều khoản: khoản sửa / bổ sung / đóng + cảnh báo
- [ ] M11-T5 Chạy `consolidate {"all": true}` cho ứng viên `NOT_SUPPORTED_YET` của PoC

## Dữ liệu

- [ ] M11-T6 Nạp 10–20 văn bản thuế hộ kinh doanh tới `INDEXED`
- [ ] M11-T6 Duyệt ứng viên mới (ghi thời gian so với ngân sách)

## Kiểm thử

- [ ] OCR PDF scan mẫu; ảnh kém → `NEEDS_ATTENTION`
- [ ] Mock LLM: kết quả hợp lệ, số hiệu bịa bị bỏ, JSON sai 3 lần
- [ ] Đo precision / recall tầng LLM trên tập câu khó (ghi vào báo cáo)
- [ ] Unit `apply` cấp Điểm (5 ca) + property-based
- [ ] F13: Điểm đã bãi bỏ → `het_hieu_luc`
- [ ] Golden M09 xanh sau khi chạy lại toàn pipeline

## Tiêu chí chấp nhận (phần còn lại của F02 §7, F04 §7, F06 §7)

- [ ] Một PDF scan mẫu → có OCR, `ocr_confidence_avg` được ghi
- [ ] Tỷ lệ câu phải gọi LLM trên bộ dữ liệu MVP ≤ 20%
- [ ] Không điều khoản nào có hai phiên bản chồng lấn sau khi thêm hợp nhất cấp Điểm
- [ ] Chạy hợp nhất 2 lần liên tiếp → lần 2 không tạo / xóa phiên bản

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Mọi văn bản MVP `INDEXED`; cạnh `THUOC_CHU_DE` / `AP_DUNG_CHO` phủ ≥ 90% Điều trong phạm vi
