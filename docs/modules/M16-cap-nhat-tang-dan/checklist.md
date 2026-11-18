# M16 – Cập nhật tăng dần & scheduler · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F15](../../features/F15-cap-nhat-tang-dan.md)

## Chuẩn bị

- [ ] Handler `crawl`, `normalize`, `parse`, `extract`, `consolidate`, `index` đã idempotent và truyền được `run_id`
- [ ] Crawler M02 hỗ trợ `mode = incremental` + `from_date`
- [ ] Duyệt bổ sung: bảng `notification`, API `confirm-revision`

## Triển khai

- [ ] M16-T1 Migration `schedule`, `watermark`, `notification`; seed 3 lịch (`enabled = false` ở dev)
- [ ] M16-T2 Scheduler trong worker: `croniter` theo `Asia/Ho_Chi_Minh`, advisory lock, chạy bù 1 lần
- [ ] M16-T2 Dùng `now_vn()` (hỗ trợ đồng hồ giả)
- [ ] M16-T3 `daily_ingest`: crawl từ `watermark − 3 ngày` → normalize → parse → relink → extract
- [ ] M16-T3 Không có ứng viên bắt buộc → consolidate → index → evaluate
- [ ] M16-T3 Cập nhật watermark chỉ khi crawl `DONE`
- [ ] M16-T3 Tổng hợp `pipeline_run` (`DONE` / `PARTIAL` / `FAILED`) + thông báo biên tập viên
- [ ] M16-T4 `relink`: ứng viên `cho_van_ban_dich` → liên kết lại → `cho_duyet` / `dich_khong_ton_tai`; văn bản nguồn về `IN_REVIEW`
- [ ] M16-T5 Bản đính chính: xác nhận → tách lại → chỉ owner đổi `content_hash` được hợp nhất / index lại
- [ ] M16-T6 `daily_status_refresh`: phiên bản / văn bản bắt đầu hoặc kết thúc hôm nay → `trang_thai` + cụm dirty
- [ ] M16-T6 `weekly_recluster` → `index {"mode":"full","parts":["communities"]}`
- [ ] M16-T7 Độ trễ theo ngày làm việc (trừ ngày lễ cấu hình); `overdue` > 2 ngày kèm bước tắc
- [ ] M16-T7 `GET /admin/schedules`, `PUT /admin/schedules/{id}`
- [ ] M16-T7 `POST/GET /admin/pipeline/runs`, `GET /admin/pipeline/runs/{id}`, `POST /admin/pipeline/jobs/{job_id}/retry`
- [ ] M16-T7 `GET /admin/freshness`
- [ ] M16-T8 `FakeSourceAdapter` đọc `tests/fixtures/fake_source/<ngày>/`
- [ ] M16-T9 Nối `evaluate` sau khi M17 xong; hồi quy → cảnh báo quản trị (BR-15.8)

## Kiểm thử

- [ ] Kịch bản văn bản mới → `IN_REVIEW` tự động
- [ ] Kịch bản nạp NĐ 70 trước NĐ 123
- [ ] Kịch bản chạy `daily_ingest` 2 lần
- [ ] Kịch bản đồng hồ 01/01/2026 với NQ 198
- [ ] Job lỗi → `FAILED`, run `PARTIAL`, retry qua API
- [ ] Chạy bù sau khi worker tắt; 2 worker chỉ 1 scheduler

## Tiêu chí chấp nhận (F15 §7)

- [ ] Thêm văn bản mới vào nguồn giả lập → lần chạy kế tiếp đưa văn bản tới `IN_REVIEW` không cần thao tác tay
- [ ] Nạp NĐ 70/2025 trước NĐ 123/2020 → ứng viên `cho_van_ban_dich`; nạp NĐ 123 sau → ứng viên `cho_duyet` với đích đúng
- [ ] Chạy `daily_ingest` 2 lần liền → lần 2 không tạo job mới
- [ ] Ngày 01/01/2026 (giả lập) → trạng thái các điều khoản thuế khoán đổi theo NQ 198/2025

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Runbook: bật / tắt lịch, chạy lại job lỗi, xử lý văn bản trễ hạn
