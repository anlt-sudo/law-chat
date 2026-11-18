# M18 – Hoàn thiện bản dev (hardening) · Implement plan

| Mục | Nội dung |
|---|---|
| Tham chiếu | [Inception](../../inception.md) §7 (KPI), §8 (rủi ro), §6.1 (bảo mật LM Studio) |
| Giai đoạn | MVP cuối – tuần 11 |
| Ước lượng | 4–5 ngày |
| Phụ thuộc | Tất cả module |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Bản dev "production-like": dựng toàn bộ hệ thống từ máy trắng bằng một lệnh, có dữ liệu mẫu, an toàn ở mức mạng nội bộ, quan sát được, đo được KPI, có runbook vận hành – sẵn sàng demo mốc MVP và bàn giao.

**Ngoài phạm vi:** hạ tầng production thật (cluster, HA, autoscale, SSO), máy chủ GPU production (inception §10 câu 4: "hiện tại chỉ tập trung cho bản dev").

## 2. Hạng mục

### 2.1. Đóng gói & khởi tạo

| Việc | Chi tiết |
|---|---|
| Image | `backend` (không reload, `uvicorn --workers 1` vì LLM local một luồng), `worker`, `worker-ocr`, `frontend` (build tĩnh, phục vụ qua Caddy) |
| Compose profile | `dev` (mount source, reload) và `demo` (image build sẵn); `docker compose --profile demo up -d` |
| Khởi tạo | `make bootstrap`: migrate → `neo4j_schema.ensure` → `ensure_index` ES → seed API key, taxonomy, lịch → (tùy chọn) nạp snapshot dữ liệu |
| Snapshot dữ liệu demo | Script `scripts/snapshot.sh` dump Neo4j (`neo4j-admin database dump`), PG (`pg_dump`), thư mục `data/`; `scripts/restore.sh` khôi phục → người mới không cần chạy lại pipeline + duyệt |
| Kiểm tra máy trắng | Một thành viên chưa từng chạy dự án làm theo README trên máy khác; ghi thời gian và vướng mắc |

### 2.2. Bảo mật (mức bản dev nội bộ)

| Rủi ro (inception §8) | Việc |
|---|---|
| Lộ endpoint LM Studio (HTTP, không xác thực) | Chỉ bind LAN; tài liệu cấu hình tường lửa Windows; tùy chọn Caddy reverse proxy HTTPS + basic auth trước LM Studio; cảnh báo BR-17.12 hiển thị trên trang quản trị |
| API key | Key sinh ngẫu nhiên khi `bootstrap` (không dùng key mặc định trong repo); chỉ lưu hash; không log header `X-API-Key`; tách key theo người |
| CORS | Chỉ origin frontend cấu hình |
| Upload | Kiểm tra magic bytes (M02), giới hạn kích thước, lưu ngoài thư mục phục vụ tĩnh |
| Bí mật | `.env` không commit; `detect-secrets` / `gitleaks` trong pre-commit |
| Phụ thuộc | `pip-audit` + `npm audit` trong CI (cảnh báo, không chặn) |
| Người dùng coi là tư vấn pháp lý | Rà lại disclaimer trên mọi câu trả lời và trang văn bản |
| Bản quyền nguồn dữ liệu | Ghi nguồn + `url_nguon` trên mọi trích dẫn; README ghi điều khoản sử dụng nguồn |

### 2.3. Quan sát

| Việc | Chi tiết |
|---|---|
| Log | JSON có `request_id`, `message_id`, `run_id`, `job_id`; mức log cấu hình được |
| Trang quản trị | LLM health, hàng đợi job, job lỗi, freshness, index status, KPI lượt gần nhất (M10 đợt 2) – kiểm tra đủ |
| Health | `/api/v1/health` thêm LM Studio (qua gateway), số job `FAILED`, outbox tồn |
| Truy vết | `GET /chat/messages/{id}/trace` đủ để gỡ lỗi một câu trả lời sai (thử với 3 phản hồi 👎 thật) |

### 2.4. Hiệu năng

| Mục tiêu | Cách đo / tối ưu |
|---|---|
| P95 ≤ 10 s (trừ Global), Global ≤ 20 s | Từ lượt đánh giá M17; phân rã theo `latency_ms` từng bước |
| `/units/lookup` p95 ≤ 200 ms, F13 50 unit ≤ 100 ms, Local p95 ≤ 1.5 s | Benchmark script `scripts/bench.py` |
| Tối ưu khả dĩ | `PROFILE` các Cypher chậm; cache LRU ngắn hạn cho alias văn bản và label; giảm token ngữ cảnh; cân nhắc `CHAT_THINKING=false` nếu sinh quá chậm – ghi rõ đánh đổi chất lượng |

### 2.5. Độ bền

| Kịch bản | Kỳ vọng |
|---|---|
| Tắt LM Studio giữa lúc chat | Câu trả lời dự phòng / 503 rõ ràng (đã test M15) |
| Tắt LM Studio giữa batch trích xuất | Job hoãn, retry, không mất ứng viên tầng 1 |
| Tắt ES | Local Search chỉ vector (`degraded`); index job `FAILED` rồi chạy lại được |
| Tắt Neo4j | `/health` báo lỗi; API trả 503, không treo |
| Khởi động lại worker giữa job | Job `RUNNING` quá hạn được trả về hàng đợi (M00) |
| Restore snapshot | Hệ thống chạy đúng golden Q1–Q5 sau restore |

### 2.6. Tài liệu & bàn giao

- `README.md`: yêu cầu máy, cài đặt, LM Studio, bootstrap, demo, xử lý sự cố thường gặp.
- `docs/runbook.md`: chạy lại job lỗi, phân cụm lại, đổi model embedding (BR-07.4), thu hồi cạnh sai, khôi phục snapshot, xoay API key, bật / tắt lịch.
- `docs/demo-script.md`: kịch bản demo Q1–Q5 + câu nối tiếp + đổi ngày áp dụng + phản hồi 👎.
- `docs/reports/mvp-kpi.md`: kết quả lượt đánh giá cuối (M17), so với mục tiêu inception §7, các hạn chế đã biết.
- OpenAPI xuất tĩnh `docs/api/openapi.json`.
- Cập nhật [features/README.md §6](../../features/README.md) với các giả định đã được xác nhận / thay đổi trong quá trình làm.

## 3. Các bước triển khai

| Mã | Công việc | Ước lượng |
|---|---|---|
| M18-T1 | Image + compose profile + `make bootstrap` | 0.75 ngày |
| M18-T2 | Snapshot / restore dữ liệu demo | 0.5 ngày |
| M18-T3 | Bảo mật 2.2 | 0.75 ngày |
| M18-T4 | Quan sát 2.3 | 0.5 ngày |
| M18-T5 | Benchmark + tối ưu 2.4 | 0.75 ngày |
| M18-T6 | Kịch bản độ bền 2.5 | 0.5 ngày |
| M18-T7 | Tài liệu, báo cáo KPI, kiểm tra máy trắng | 0.75 ngày |

## 4. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| KPI chưa đạt ở mốc MVP | Báo cáo trung thực trong `mvp-kpi.md` kèm phân tích lỗi (từ `eval_result` + trace) và đề xuất cho giai đoạn Mở rộng; không chỉnh bộ đánh giá để đạt số |
| Máy demo khác máy dev (VRAM / RAM) | Ghi cấu hình tối thiểu; chạy thử trên máy demo trước ít nhất 2 ngày |
| Hết thời gian | Ưu tiên T1, T2, T7 (dựng được + demo được + có báo cáo) |
