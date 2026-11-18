# M04 – Trích xuất quan hệ (luật mẫu) & danh mục · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F04](../../features/F04-trich-xuat-quan-he.md)

## Chuẩn bị

- [ ] NĐ 123, NĐ 70, TT 78, TT 32, NQ 198 đã `PARSED`, `quoted_blocks` của NĐ 70 có dữ liệu
- [ ] M04-T1 `tests/fixtures/relation_sentences.yaml` ≥ 60 câu thật kèm kỳ vọng
- [ ] Chốt cách xử lý R-BB-02 (văn bản khác hết hiệu lực) – plan §3.3

## Triển khai

- [ ] M04-T2 Migration `0005_relations` (`relation_candidate` F04 §6.1)
- [ ] M04-T3 Tách câu theo Khoản; không chạy luật trong khối trích dẫn
- [ ] M04-T3 Ngữ cảnh văn bản đích từ tiêu đề Điều; ngữ cảnh lồng 2 tầng; "Nghị định này" / "Điều này"
- [ ] M04-T3 `thu_tu_trong_nguon` tăng dần theo vị trí trong văn bản
- [ ] M04-T4 R-SD-01, R-SD-02 (`BO_SUNG` với đích ID mới)
- [ ] M04-T4 R-BB-01, R-BB-02
- [ ] M04-T4 R-TT-01, R-HD-01, R-VD-01
- [ ] M04-T4 Câu có từ khóa kích hoạt nhưng luật không khớp đủ → `manual_required`
- [ ] M04-T5 Liệt kê / khoảng đích khai triển đủ (BR-04.6)
- [ ] M04-T5 Văn bản đích chưa có → `cho_van_ban_dich`; điều khoản không có → `dich_khong_ton_tai` conf ≤ 0.5
- [ ] M04-T5 `noi_dung_moi` từ quoted block liền sau; thiếu → `THIEU_NOI_DUNG`
- [ ] M04-T5 `tu_ngay` = hiệu lực văn bản nguồn hoặc hiệu lực riêng
- [ ] M04-T5 Độ tin cậy 0.95 / 0.85 / ≤ 0.5 theo BR-04.11
- [ ] M04-T5 `SUA_DOI`/`BAI_BO`/`THAY_THE` → `cho_duyet`, **không** ghi Neo4j
- [ ] M04-T6 `taxonomy/seed.yaml` 4 chủ đề, 5 đối tượng + từ khóa; nạp Neo4j bằng `MERGE`
- [ ] M04-T6 Gán `THUOC_CHU_DE` / `AP_DUNG_CHO` cấp Điều bằng từ khóa; văn bản nhận chủ đề ≥ 20% Điều
- [ ] M04-T7 Cạnh `HUONG_DAN`, `VIEN_DAN`, `THUOC_CHU_DE`, `AP_DUNG_CHO` → `tu_dong_duyet` + `MERGE` vào Neo4j kèm `candidate_id`
- [ ] M04-T7 Chạy lại: giữ ứng viên đã duyệt / từ chối; xóa ứng viên `cho_duyet` không còn sinh ra
- [ ] M04-T7 Kết thúc: `IN_REVIEW` hoặc `REVIEWED` + `enqueue("consolidate")`; `stats` có tỷ lệ câu cần LLM
- [ ] M04-T8 `POST /ingest/documents/{slug}/extract-relations`
- [ ] M04-T8 `GET /relation-candidates` (lọc `document`, `loai`, `trang_thai`, `phuong_phap`, `min_conf`, `max_conf`), `GET /relation-candidates/{id}`
- [ ] M04-T8 `GET/POST /taxonomy/chu-de`, `/taxonomy/doi-tuong`; `GET /documents?chu_de=`

## Kiểm thử

- [ ] Unit bộ câu mẫu: precision luật `SUA_DOI` / `BAI_BO` ≥ 0.95
- [ ] Unit kế thừa ngữ cảnh, liệt kê, khoảng
- [ ] Tích hợp NĐ 70 → ứng viên `BAI_BO` khoản 10 Điều 3 NĐ 123
- [ ] Tích hợp nạp NĐ 70 trước NĐ 123 → `cho_van_ban_dich`
- [ ] Tích hợp chạy lại không trùng ứng viên / cạnh

## Tiêu chí chấp nhận (F04 §7, phần PoC)

- [ ] "Bãi bỏ khoản 10 Điều 3 Nghị định số 123/2020/NĐ-CP." → 1 ứng viên `BAI_BO`, đích `123/2020/NĐ-CP:Đ3:K10`, conf 0.95, `tu_ngay = 2025-06-01`
- [ ] Khoản trong Điều "Sửa đổi, bổ sung một số điều của NĐ 123" chỉ ghi "Sửa đổi khoản 4 Điều 9" → đích kế thừa `123/2020/NĐ-CP:Đ9:K4`
- [ ] TT 32/2025 → ứng viên `THAY_THE` → TT 78/2021 và `HUONG_DAN` → NĐ 123, NĐ 70
- [ ] Tỷ lệ câu cần LLM (`manual_required`) trên bộ PoC ≤ 20%

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Báo cáo số ứng viên chờ duyệt của bộ PoC, ước lượng thời gian duyệt so với ngân sách 2 giờ/tuần
