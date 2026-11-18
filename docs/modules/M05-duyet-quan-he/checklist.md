# M05 – Duyệt quan hệ · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F05](../../features/F05-duyet-quan-he.md)

## Chuẩn bị

- [ ] Có ứng viên `cho_duyet` của NĐ 70 và TT 32 từ M04
- [ ] Làm rõ lịch chuyên gia (2 giờ/tuần, ý nghĩa "0.5 tuần" ở inception §10)
- [ ] Duyệt bổ sung: khung frontend tạo ở M05; cột `nguon_hieu_luc_tu` (nếu dùng)

## Triển khai – API

- [ ] M05-T1 Migration `review_action` (F05 §6)
- [ ] M05-T2 `GET /review/queue` sắp: conf tăng dần → hiệu lực văn bản nguồn → thứ tự trong văn bản; lọc `document`, `loai`, `max_conf`
- [ ] M05-T2 `GET /review/candidates/{id}` có phiên bản hiện hành của đích, `noi_dung_moi`, diff, link nguồn
- [ ] M05-T3 Kiểm tra: đích tồn tại (trừ `BO_SUNG`), có `tu_ngay`, `SUA_DOI` có nội dung, cảnh báo hồi tố cần xác nhận
- [ ] M05-T3 Xung đột cùng đích, cùng ngày, khác nguồn → 409 `EDGE_CONFLICT`
- [ ] M05-T4 Approve / sửa rồi duyệt (lưu before/after) / từ chối (bắt buộc lý do)
- [ ] M05-T4 Khóa `FOR UPDATE`; ghi Neo4j `MERGE … {candidate_id}` trước, rồi PG
- [ ] M05-T4 Hết ứng viên bắt buộc → `REVIEWED` + `enqueue("consolidate")` với các đích bị ảnh hưởng
- [ ] M05-T5 Bulk-approve chỉ `rule` + conf ≥ 0.95; trả `approved` / `failed`
- [ ] M05-T5 Thêm thủ công: `phuong_phap = manual`, conf 1.0, duyệt ngay qua cùng kiểm tra
- [ ] M05-T5 Thu hồi: xóa cạnh, ứng viên về `cho_duyet`, enqueue hợp nhất lại
- [ ] M05-T5 Job đối soát `reconcile_edges` (cạnh có `candidate_id` không `da_duyet`)
- [ ] M05-T6 `GET /review/stats`: còn lại, đã duyệt, tỷ lệ sửa / từ chối theo `rule_id`, thời gian theo tuần
- [ ] Mọi hành động ghi `review_action` có `actor`, `elapsed_ms`

## Triển khai – giao diện

- [ ] M05-T7 Khởi tạo `frontend/` (Vite + React + TS), API client gắn `X-API-Key`
- [ ] M05-T7 Trang hàng đợi + nút duyệt hàng loạt có bước xác nhận danh sách
- [ ] M05-T7 Trang ứng viên: câu gốc tô sáng, diff hai cột, 3 nút hành động, form sửa
- [ ] M05-T7 Phím tắt duyệt nhanh; đo `elapsed_ms`

## Kiểm thử

- [ ] Unit validate từng mã lỗi
- [ ] Tích hợp duyệt → có cạnh; thu hồi → mất cạnh + job hợp nhất
- [ ] Tích hợp xung đột → 409
- [ ] Tích hợp bulk có 1 ứng viên lỗi
- [ ] Tích hợp đối soát cạnh mồ côi
- [ ] Thủ công: duyệt toàn bộ NĐ 70 trên giao diện, ghi tổng thời gian

## Tiêu chí chấp nhận (F05 §7)

- [ ] Ứng viên chưa duyệt không xuất hiện trong đồ thị và không ảnh hưởng câu trả lời
- [ ] Duyệt xong toàn bộ ứng viên NĐ 70/2025 → tự tạo job F06
- [ ] Xung đột cùng đích, cùng ngày → 409
- [ ] `/review/stats` báo tổng thời gian duyệt theo tuần

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Toàn bộ ứng viên bắt buộc của 5 văn bản inception đã `da_duyet` / `tu_choi`
