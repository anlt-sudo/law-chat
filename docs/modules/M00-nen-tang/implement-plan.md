# M00 – Nền tảng & hạ tầng dev · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [00-common](../../features/00-common.md) |
| Giai đoạn | PoC – tuần 1 |
| Ước lượng | 3–4 ngày (1 người) |
| Phụ thuộc | – |
| Module dùng kết quả | Tất cả |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

`docker compose up` + `make migrate` là có đủ Neo4j, PostgreSQL, Elasticsearch, một FastAPI rỗng và một worker rỗng chạy được, cùng mọi quy ước dùng chung (ID, ngày hiệu lực, lỗi, xác thực, phân trang, hàng đợi job). Các module sau chỉ thêm code nghiệp vụ.

## 2. Phạm vi

| Trong M00 | Để module sau |
|---|---|
| Khung repo, tooling, CI | Bảng nghiệp vụ của từng feature (mỗi module tự thêm migration) |
| Docker Compose 3 kho + backend + worker | Image production, reverse proxy (M18) |
| Cấu hình, logging, lỗi chuẩn, xác thực `X-API-Key` | Giao diện (M05, M10) |
| Hàng đợi job trên PostgreSQL + worker loop | Scheduler theo cron (M16) |
| Tiện ích ID, slug, khoảng hiệu lực, đồng hồ | Parser tham chiếu dạng chữ (M03) |
| Constraint / index Neo4j theo 00-common §4.3 | Mapping index ES `phien_ban` (M08) |

## 3. Thiết kế

### 3.1. Công nghệ (đề xuất – chốt trong buổi review plan)

| Nhóm | Lựa chọn |
|---|---|
| Ngôn ngữ / quản lý gói | Python 3.12, `uv` |
| Web | FastAPI, Uvicorn, Pydantic v2, `pydantic-settings` |
| PostgreSQL | SQLAlchemy 2 (async) + `asyncpg`, Alembic |
| Neo4j | `neo4j` Python driver (async), Neo4j 5.x Community + plugin APOC + Graph Data Science |
| Elasticsearch | `elasticsearch[async]` 8.x, image ES 8 tự build thêm plugin `analysis-icu` |
| HTTP client | `httpx` |
| Test | `pytest`, `pytest-asyncio`, `respx` (mock HTTP) |
| Chất lượng | `ruff` (lint + format), `mypy`, `pre-commit` |
| CI | GitHub Actions, service container PG / Neo4j / ES |

### 3.2. Cấu trúc thư mục tạo trong M00

```text
law-chat/
├── docker-compose.yml
├── docker/
│   ├── elasticsearch/Dockerfile        # FROM elasticsearch:8.x + analysis-icu
│   └── backend/Dockerfile
├── .env.example
├── Makefile                            # chạy bằng Git Bash / WSL trên Windows
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini, alembic/versions/0001_base.py
│   ├── app/
│   │   ├── main.py                     # create_app(), include routers, exception handlers
│   │   ├── worker.py                   # entrypoint worker: python -m app.worker
│   │   ├── core/
│   │   │   ├── config.py               # Settings (pydantic-settings)
│   │   │   ├── logging.py              # JSON log, request_id
│   │   │   ├── errors.py               # AppError + handler → format lỗi chuẩn
│   │   │   ├── auth.py                 # X-API-Key → Principal(role), require_role()
│   │   │   ├── pagination.py           # Page[T], PageParams
│   │   │   └── clock.py                # today_vn(), now_vn(); APP_FAKE_TODAY
│   │   ├── db/
│   │   │   ├── pg.py                   # engine, session dependency
│   │   │   ├── neo4j.py                # driver, run_read / run_write helpers
│   │   │   ├── neo4j_schema.py         # constraint + index idempotent (00-common §4.3)
│   │   │   ├── es.py                   # client
│   │   │   └── storage.py              # FileStorage: raw/, normalized/ theo DATA_DIR
│   │   ├── legal/
│   │   │   ├── ids.py                  # build/parse ID, slugify
│   │   │   └── validity.py             # is_active(tu, den, d) – khoảng nửa mở
│   │   ├── models/common.py            # TrangThaiHieuLuc, ThayDoi, Citation (00-common §7)
│   │   ├── jobs/
│   │   │   ├── models.py               # ORM pipeline_run, pipeline_job
│   │   │   ├── queue.py                # enqueue(), claim_next(), complete(), fail()
│   │   │   └── registry.py             # @handler("parse") → hàm xử lý
│   │   └── api/health.py               # GET /api/v1/health
│   ├── scripts/seed_api_keys.py
│   └── tests/
│       ├── conftest.py                 # fixture app, pg, neo4j, es, clock
│       └── unit/ (test_ids.py, test_validity.py, test_queue.py, test_auth.py)
└── data/                               # volume file storage (gitignore)
```

### 3.3. Docker Compose

| Service | Image | Cổng | Ghi chú |
|---|---|---|---|
| `neo4j` | `neo4j:5` | 7474, 7687 | `NEO4J_PLUGINS='["apoc","graph-data-science"]'`, heap 1–2 GB, volume `neo4j_data` |
| `postgres` | `postgres:16` | host `PG_HOST_PORT` (mặc định 5433) → 5432 | volume `pg_data`; tránh đụng PostgreSQL cài sẵn trên máy ở 5432 |
| `elasticsearch` | build `docker/elasticsearch` | 9200 | `discovery.type=single-node`, `xpack.security.enabled=false` (chỉ dev), heap 1 GB |
| `backend` | build `docker/backend` | 8000 | `uvicorn app.main:app --reload`, mount source |
| `worker` | cùng image | – | `python -m app.worker` |

LM Studio **không** nằm trong compose – chạy trên máy host / máy GPU, backend trỏ qua `LLM_BASE_URL` (với Docker Desktop: `http://host.docker.internal:1234/v1`).

### 3.4. Schema PostgreSQL (migration `0001_base`)

```sql
-- (bổ sung) lưu API key cho bản dev
CREATE TABLE api_key (
    id          TEXT PRIMARY KEY,              -- 'dev-admin', 'dev-editor', 'dev-user'
    key_hash    CHAR(64) NOT NULL UNIQUE,      -- sha256(key)
    role        TEXT NOT NULL CHECK (role IN ('nguoi_dung','bien_tap_vien','quan_tri')),
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Theo F15 §6, tạo sớm để mọi module dùng chung; thêm 3 cột (bổ sung)
CREATE TABLE pipeline_run (
    id          UUID PRIMARY KEY,
    type        TEXT NOT NULL,
    trigger     TEXT NOT NULL CHECK (trigger IN ('schedule','manual','event')),
    params      JSONB NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','DONE','PARTIAL','FAILED')),
    summary     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE pipeline_job (
    id                 UUID PRIMARY KEY,
    run_id             UUID REFERENCES pipeline_run(id),
    step               TEXT NOT NULL,
    source_document_id UUID,                   -- FK thêm ở M02 khi có source_document
    payload            JSONB NOT NULL DEFAULT '{}',
    status             TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','DONE','FAILED','CANCELLED')),
    priority           SMALLINT NOT NULL DEFAULT 3,      -- (bổ sung) 1 cao nhất
    run_after          TIMESTAMPTZ NOT NULL DEFAULT now(), -- (bổ sung) backoff / hoãn
    dedupe_key         TEXT,                              -- (bổ sung) vd 'parse:<doc_id>'
    attempts           INT NOT NULL DEFAULT 0,
    error              TEXT,
    queued_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at         TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ
);
CREATE INDEX ON pipeline_job (status, priority, run_after);
CREATE UNIQUE INDEX pipeline_job_dedupe_active ON pipeline_job (dedupe_key)
    WHERE status IN ('QUEUED','RUNNING');
```

### 3.5. Hàng đợi job

```python
# app/jobs/queue.py
async def enqueue(step: str, payload: dict, *, source_document_id=None, run_id=None,
                  priority: int = 3, dedupe_key: str | None = None, delay_s: int = 0) -> UUID | None:
    """INSERT ... ON CONFLICT (dedupe_key) WHERE active DO NOTHING → trả None nếu trùng."""

async def claim_next(steps: list[str] | None = None) -> Job | None:
    """
    UPDATE pipeline_job SET status='RUNNING', started_at=now(), attempts=attempts+1
    WHERE id = (SELECT id FROM pipeline_job
                WHERE status='QUEUED' AND run_after <= now() AND (steps filter)
                ORDER BY priority, queued_at
                FOR UPDATE SKIP LOCKED LIMIT 1)
    RETURNING *;
    """
```

- Worker loop: `claim_next` → tra `registry[step]` → chạy → `DONE`; lỗi → `attempts < 3` thì `QUEUED` với `run_after = now() + backoff(attempts)` (2 s, 4 s, 8 s), hết lượt → `FAILED` + `error`.
- Handler phải **idempotent** (F15 BR-15.6). Handler được đăng ký bằng decorator trong module nghiệp vụ; `app/worker.py` import các module để đăng ký.
- Job `RUNNING` quá `JOB_STALE_MINUTES` (mặc định 30) khi worker khởi động → trả về `QUEUED` (worker chết giữa chừng).

### 3.6. Tiện ích dùng chung

| Hàm | Hành vi | Ví dụ |
|---|---|---|
| `slugify(so_hieu)` | NFC → bỏ dấu (Đ/đ → d) → lowercase → `/` thành `-` | `123/2020/NĐ-CP` → `123-2020-nd-cp` |
| `chuong_id(so_hieu, la_ma)` | `<so_hieu>:C<La Mã>` | `123/2020/NĐ-CP:CII` |
| `dieu_id`, `khoan_id`, `diem_id` | Theo 00-common §2 | `123/2020/NĐ-CP:Đ9:K4:a` |
| `version_id(unit_id, tu)` | `<unit>@YYYY-MM-DD` | `…:Đ19:K1@2025-06-01` |
| `parse_unit_id(id)` | Tách thành `so_hieu, dieu, khoan, diem` | dùng ở F06, F13 |
| `parent_id(id)` | Điểm → Khoản → Điều → Văn bản | |
| `is_active(tu, den, d)` | `tu is not None and tu <= d and (den is None or den > d)` | `den == d` → **False** |
| `today_vn()` | Ngày theo `Asia/Ho_Chi_Minh`, trả `APP_FAKE_TODAY` nếu đặt | |

### 3.7. API

| Method | Endpoint | Vai trò | Mô tả |
|---|---|---|---|
| GET | `/api/v1/health` | – | Ping PG, Neo4j, ES; trả trạng thái từng kho, phiên bản app, `today` |

Format lỗi chuẩn (00-common §6) áp cho cả lỗi validate của FastAPI (`422` → `code = VALIDATION_ERROR`) và lỗi không bắt được (`500` → `code = INTERNAL_ERROR`, không lộ stack trace).

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | Ước lượng |
|---|---|---|---|
| M00-T1 | Khởi tạo repo backend | `uv init`, thêm dependency, `ruff`/`mypy` config, `pre-commit`, `.gitignore` (`data/`, `.env`) | 0.25 ngày |
| M00-T2 | Docker Compose | 5 service như 3.3; Dockerfile ES có `analysis-icu`; healthcheck từng service; `.env.example` đủ biến của inception 6.1 + F17 §6.1 + kết nối kho | 0.5 ngày |
| M00-T3 | Config + logging | `Settings` đọc `.env`; log JSON, middleware gắn `request_id` vào log và header phản hồi | 0.25 ngày |
| M00-T4 | Lỗi chuẩn + phân trang | `AppError(code, message, details, http_status)`; handler cho `AppError`, `RequestValidationError`, `Exception`; `Page[T]` | 0.25 ngày |
| M00-T5 | Kết nối kho | `db/pg.py`, `db/neo4j.py` (helper `read`, `write`, transaction function có retry), `db/es.py`, `db/storage.py` | 0.5 ngày |
| M00-T6 | Migration nền + Neo4j schema | Alembic `0001_base` (3.4); `neo4j_schema.ensure()` chạy khi app khởi động, tạo constraint/index 00-common §4.3 | 0.25 ngày |
| M00-T7 | Xác thực | Dependency đọc `X-API-Key`, so `sha256`, trả `Principal(id, role)`; `require_role("bien_tap_vien")` cho phép vai trò cao hơn; thiếu key → 401, sai vai trò → 403; script `seed_api_keys.py` in ra 3 key dev | 0.25 ngày |
| M00-T8 | Tiện ích pháp lý | `legal/ids.py`, `legal/validity.py`, `core/clock.py`, `models/common.py` + unit test đầy đủ | 0.5 ngày |
| M00-T9 | Hàng đợi job + worker | `jobs/queue.py`, `jobs/registry.py`, `app/worker.py` (vòng lặp async, poll 1 s, dừng êm khi SIGTERM), hồi phục job `RUNNING` quá hạn; handler mẫu `noop` để test | 0.5 ngày |
| M00-T10 | Health + Makefile | `/api/v1/health`; Makefile: `up`, `down`, `migrate`, `seed`, `test`, `lint`, `fmt`, `logs` | 0.25 ngày |
| M00-T11 | CI | Workflow: `ruff check`, `ruff format --check`, `mypy`, `pytest` với service PG / Neo4j / ES | 0.25 ngày |
| M00-T12 | Spike hạ tầng | Kiểm tra GDS Leiden chạy được trên Neo4j Community trong Docker (`CALL gds.version()`, Leiden trên đồ thị mẫu); ICU analyzer có tách từ tiếng Việt + `asciifolding` | 0.25 ngày |
| M00-T13 | README chạy dự án | Hướng dẫn cài, chạy, key dev, kết nối LM Studio từ container | 0.1 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit | `slugify` (có `Đ`, `đ`, chữ hoa), build/parse ID (Điều `9a`, Điểm `đ`), `is_active` (trước, trong, đúng ngày `den`, sau, `tu = None`), `today_vn` với / không `APP_FAKE_TODAY` |
| Unit | Auth: không key → 401; key `nguoi_dung` gọi route `quan_tri` → 403; `quan_tri` gọi route `bien_tap_vien` → 200 |
| Tích hợp | Queue: 2 worker song song claim 10 job → mỗi job chạy đúng 1 lần; job lỗi retry 3 lần rồi `FAILED`; `dedupe_key` trùng khi job đang `QUEUED` → không tạo mới |
| Tích hợp | `neo4j_schema.ensure()` chạy 2 lần không lỗi; `SHOW CONSTRAINTS` có đủ 8 constraint |
| Smoke | `docker compose up` trên máy sạch → `/api/v1/health` trả cả 3 kho `ok` |

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| RAM máy dev không đủ cho Neo4j + ES + LM Studio (Qwen 9B cần ~7 GB) | Giới hạn heap Neo4j 1 GB, ES 1 GB; ghi yêu cầu RAM tối thiểu vào README; cho phép tắt ES khi chỉ làm pipeline |
| Plugin GDS không tương thích phiên bản Neo4j | Ghim phiên bản Neo4j theo bảng tương thích GDS; spike M00-T12 |
| Makefile không chạy trên Windows thuần | Dùng Git Bash / WSL, hoặc mỗi target có lệnh `uv run …` tương đương trong README |
| Vector index cần Neo4j ≥ 5.11 | Ghim `neo4j:5.2x` |

## 7. Bàn giao

- Module sau thêm bảng bằng migration mới (`0002_…`), thêm handler job bằng `@handler("<step>")`, thêm router vào `app/main.py`.
- Hằng số step job thống nhất: `crawl`, `normalize`, `parse`, `relink`, `extract`, `consolidate`, `index`, `evaluate` (theo F15 §6).
