# M00 – Nền tảng & hạ tầng dev · Checklist

Plan: [implement-plan.md](implement-plan.md)

## Chuẩn bị

- [ ] Chốt công nghệ ở plan §3.1 trong buổi review
- [ ] Chốt danh sách bổ sung: bảng `api_key`, cột `priority` / `run_after` / `dedupe_key`, `APP_FAKE_TODAY`
- [ ] Máy dev có Docker Desktop, ≥ 16 GB RAM (khuyến nghị), LM Studio cài sẵn

## Triển khai

- [ ] M00-T1 Repo backend: `uv`, dependency, `ruff`, `mypy`, `pre-commit`, `.gitignore` có `data/` và `.env`
- [ ] M00-T2 `docker-compose.yml` đủ `neo4j` (APOC + GDS), `postgres`, `elasticsearch` (ICU), `backend`, `worker`; có healthcheck
- [ ] M00-T2 `.env.example` đủ biến LLM (inception 6.1, F17 §6.1), Neo4j, PG, ES, `DATA_DIR`, `APP_FAKE_TODAY`
- [ ] M00-T3 `Settings` + log JSON + `request_id`
- [ ] M00-T4 `AppError` + 3 exception handler + `Page[T]`
- [ ] M00-T5 Client PG / Neo4j / ES / FileStorage
- [ ] M00-T6 Migration `0001_base` (`api_key`, `pipeline_run`, `pipeline_job`)
- [ ] M00-T6 `neo4j_schema.ensure()` tạo đủ constraint + index 00-common §4.3 (kể cả 2 vector index 1024 chiều)
- [ ] M00-T7 Auth `X-API-Key` + `require_role` + script seed 3 key
- [ ] M00-T8 `legal/ids.py`, `legal/validity.py`, `core/clock.py`, `models/common.py`
- [ ] M00-T9 `enqueue` / `claim_next` (SKIP LOCKED) / retry backoff / hồi phục job quá hạn / worker dừng êm
- [ ] M00-T10 `GET /api/v1/health` + Makefile
- [ ] M00-T11 Workflow CI xanh
- [ ] M00-T12 Spike: Leiden chạy trên GDS Community; ICU + `asciifolding` hoạt động (ghi kết quả vào README hoặc `docs/spikes/`)
- [ ] M00-T13 README chạy dự án

## Kiểm thử

- [ ] Unit `slugify`, build / parse ID (`Đ9a`, điểm `đ`)
- [ ] Unit `is_active`: ngày đúng bằng `hieu_luc_den` → **không** hiệu lực; `tu = None` → không hiệu lực
- [ ] Unit `today_vn` có / không `APP_FAKE_TODAY`
- [ ] Unit auth: 401 / 403 / vai trò cao hơn được phép
- [ ] Tích hợp queue: 2 worker không chạy trùng job; retry 3 lần → `FAILED`; `dedupe_key` chặn job trùng
- [ ] Tích hợp: `neo4j_schema.ensure()` chạy 2 lần không lỗi

## Tiêu chí chấp nhận

- [ ] Máy sạch: `docker compose up` + `make migrate` + `make seed` → `/api/v1/health` báo PG, Neo4j, ES đều `ok`
- [ ] Lỗi validate trả đúng format `{"error": {"code", "message", "details"}}`
- [ ] CI xanh trên nhánh chính

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] README mô tả cách trỏ `LLM_BASE_URL` từ container ra LM Studio trên host
