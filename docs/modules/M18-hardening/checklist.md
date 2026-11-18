# M18 – Hoàn thiện bản dev (hardening) · Checklist

Plan: [implement-plan.md](implement-plan.md)

## Đóng gói & khởi tạo

- [ ] M18-T1 Image `backend`, `worker`, `worker-ocr`, `frontend`
- [ ] M18-T1 Compose profile `dev` và `demo`
- [ ] M18-T1 `make bootstrap`: migrate, Neo4j schema, ES index, seed key / taxonomy / lịch
- [ ] M18-T2 `scripts/snapshot.sh` và `scripts/restore.sh` (Neo4j, PG, `data/`)
- [ ] M18-T7 Một người chưa từng chạy dự án dựng được hệ thống trên máy khác theo README

## Bảo mật

- [ ] M18-T3 LM Studio chỉ bind LAN; hướng dẫn tường lửa; tùy chọn Caddy HTTPS + auth
- [ ] M18-T3 Cảnh báo `LLM_BASE_URL` public / không https hiển thị trên trang quản trị
- [ ] M18-T3 API key sinh ngẫu nhiên khi bootstrap, lưu hash, không log header
- [ ] M18-T3 CORS chỉ origin frontend
- [ ] M18-T3 `gitleaks` / `detect-secrets` trong pre-commit; `.env` không trong git
- [ ] M18-T3 `pip-audit`, `npm audit` trong CI
- [ ] M18-T3 Disclaimer và nguồn hiển thị trên mọi câu trả lời, trang văn bản

## Quan sát

- [ ] M18-T4 Log JSON có `request_id`, `message_id`, `run_id`, `job_id`
- [ ] M18-T4 `/api/v1/health` gồm LM Studio, job `FAILED`, outbox tồn
- [ ] M18-T4 Trang quản trị đủ: LLM, job, freshness, index, KPI
- [ ] M18-T4 Gỡ được 3 phản hồi 👎 thật bằng trace

## Hiệu năng

- [ ] M18-T5 `scripts/bench.py`: `/units/lookup` p95 ≤ 200 ms; F13 50 unit ≤ 100 ms; Local p95 ≤ 1.5 s
- [ ] M18-T5 P95 hỏi đáp ≤ 10 s (trừ Global); Global ≤ 20 s hoặc `partial`
- [ ] M18-T5 Ghi lại tối ưu đã áp dụng và đánh đổi (nếu tắt thinking)

## Độ bền

- [ ] M18-T6 Tắt LM Studio khi chat → dự phòng / 503
- [ ] M18-T6 Tắt LM Studio khi batch → job hoãn, không mất dữ liệu
- [ ] M18-T6 Tắt ES → Local `degraded`; index chạy lại được
- [ ] M18-T6 Tắt Neo4j → 503, không treo
- [ ] M18-T6 Khởi động lại worker giữa job → job được chạy lại
- [ ] M18-T6 Restore snapshot → golden Q1–Q5 đạt

## Tài liệu & bàn giao

- [ ] M18-T7 `README.md` đầy đủ
- [ ] M18-T7 `docs/runbook.md`
- [ ] M18-T7 `docs/demo-script.md`
- [ ] M18-T7 `docs/reports/mvp-kpi.md` (lượt đánh giá cuối, so mục tiêu, hạn chế)
- [ ] M18-T7 `docs/api/openapi.json`
- [ ] M18-T7 Cập nhật `features/README.md §6` với giả định đã xác nhận / thay đổi

## Tiêu chí chấp nhận mốc MVP

- [ ] Demo Q1–Q5 trên web (stream) với 2 lĩnh vực: hóa đơn điện tử + thuế hộ kinh doanh
- [ ] Báo cáo KPI inception §7 từ lượt đánh giá ≥ 50 câu
- [ ] Hệ thống dựng lại được từ máy trắng + snapshot trong ≤ 1 giờ (không tính tải model LM Studio)

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Mọi checklist M00–M17 đã tick hoặc ghi rõ mục hoãn kèm lý do
