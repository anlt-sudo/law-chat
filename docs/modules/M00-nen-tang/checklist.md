# M00 – Nền tảng & hạ tầng dev · Checklist

Plan: [implement-plan.md](implement-plan.md)

> Trạng thái 18/11/2026: đã triển khai và kiểm tra trên máy dev (Windows + Docker Desktop). Còn mở: review công nghệ / bổ sung, chạy CI lần đầu trên GitHub, kiểm tra trên máy sạch.

## Chuẩn bị

- [ ] Chốt công nghệ ở plan §3.1 trong buổi review *(đã làm theo đề xuất, chưa được review)*
- [ ] Chốt danh sách bổ sung: bảng `api_key`, cột `priority` / `run_after` / `dedupe_key`, `APP_FAKE_TODAY` *(đã làm theo đề xuất, chưa được review)*
- [x] Máy dev có Docker Desktop, LM Studio cài sẵn *(Docker VM 8 GB; LM Studio chưa kiểm tra – cần từ M01)*

## Triển khai

- [x] M00-T1 Repo backend: `uv`, dependency, `ruff`, `mypy`, `pre-commit`, `.gitignore` có `data/` và `.env`
- [x] M00-T2 `docker-compose.yml` đủ `neo4j` (APOC + GDS), `postgres`, `elasticsearch` (ICU), `backend`, `worker`; có healthcheck
- [x] M00-T2 `.env.example` đủ biến LLM (inception 6.1, F17 §6.1), Neo4j, PG, ES, `DATA_DIR`, `APP_FAKE_TODAY`
- [x] M00-T3 `Settings` + log JSON + `request_id`
- [x] M00-T4 `AppError` + 4 exception handler (AppError, validate, HTTP, không bắt được) + `Page[T]`
- [x] M00-T5 Client PG / Neo4j / ES / FileStorage
- [x] M00-T6 Migration `0001_base` (`api_key`, `pipeline_run`, `pipeline_job`); `alembic check` không lệch ORM
- [x] M00-T6 `neo4j_schema.ensure()` tạo đủ constraint + index 00-common §4.3 (kể cả 2 vector index 1024 chiều)
- [x] M00-T7 Auth `X-API-Key` + `require_role` + script seed 3 key
- [x] M00-T8 `legal/ids.py`, `legal/validity.py`, `core/clock.py`, `models/common.py`
- [x] M00-T9 `enqueue` / `claim_next` (SKIP LOCKED) / retry backoff / hồi phục job quá hạn / worker dừng êm
- [x] M00-T10 `GET /api/v1/health` (+ `/health/live`) + Makefile + `scripts/dev.ps1` (Windows)
- [ ] M00-T11 Workflow CI xanh *(đã viết `.github/workflows/ci.yml`, chưa chạy trên GitHub)*
- [x] M00-T12 Spike: Leiden chạy trên GDS Community; ICU + `asciifolding` hoạt động → [docs/spikes/m00-ha-tang.md](../../spikes/m00-ha-tang.md)
- [x] M00-T13 README chạy dự án

## Kiểm thử

- [x] Unit `slugify`, build / parse ID (`Đ9a`, điểm `đ`, `d1`)
- [x] Unit `is_active`: ngày đúng bằng `hieu_luc_den` → không hiệu lực; `tu = None` → không hiệu lực
- [x] Unit `today_vn` có / không `APP_FAKE_TODAY` / `APP_FAKE_NOW`
- [x] Unit auth: 401 / 403 / vai trò cao hơn được phép
- [x] Tích hợp queue: 2 worker không chạy trùng job; retry 3 lần → `FAILED`; `dedupe_key` chặn job trùng
- [x] Tích hợp: `neo4j_schema.ensure()` chạy 2 lần không lỗi

Kết quả: 74 test qua, 0 skip (`REQUIRE_SERVICES=postgres,neo4j,elasticsearch`); `ruff`, `mypy` sạch.

## Tiêu chí chấp nhận

- [ ] Máy sạch: `docker compose up` + `migrate` + `seed` → `/api/v1/health` báo PG, Neo4j, ES đều `ok` *(đạt trên máy dev hiện tại – backend trong Docker trả HTTP 200; chưa thử trên máy sạch)*
- [x] Lỗi validate trả đúng format `{"error": {"code", "message", "details"}}`
- [ ] CI xanh trên nhánh chính *(chưa push)*

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module) *(còn CI)*
- [x] README mô tả cách trỏ `LLM_BASE_URL` từ container ra LM Studio trên host
