# LegalGraph

Chatbot tra cứu văn bản pháp luật Việt Nam ứng dụng GraphRAG (đồ thị tri thức có yếu tố thời gian + RAG), LLM Qwen3.5 9B chạy local qua LM Studio.

- Tài liệu: [inception](docs/inception.md) · [đặc tả feature](docs/features/README.md) · [kế hoạch phát triển](docs/development-plan.md) · [plan & checklist từng module](docs/modules/README.md)
- Trạng thái: **M00 – nền tảng** ✔ · **M01 – LLM Gateway** ✔ (`app/llm`, API `/api/v1/admin/llm/*`).

## Yêu cầu máy

| Thành phần | Tối thiểu | Ghi chú |
|---|---|---|
| RAM | 16 GB | Neo4j ~1.5 GB, Elasticsearch ~1.3 GB, PostgreSQL, cộng LM Studio + Qwen3.5 9B Q4 (~7 GB) |
| Docker Desktop | 4.x, Compose ≥ 2.24 | Cấp cho Docker VM ≥ 6 GB |
| Python / uv | Python 3.12, [uv](https://docs.astral.sh/uv/) ≥ 0.13 | Chạy backend / test ngoài Docker |
| LM Studio | Bật Local Server cổng 1234 | Cần từ M01 (LLM Gateway) |

## Chạy nhanh

Windows PowerShell dùng `./scripts/dev.ps1 <lệnh>`, Linux / macOS / Git Bash có `make` dùng `make <lệnh>` – tên lệnh giống nhau.

```powershell
Copy-Item .env.example .env          # chỉnh nếu cần (mật khẩu, LLM_BASE_URL…)
./scripts/dev.ps1 up-deps            # Neo4j + PostgreSQL + Elasticsearch (lần đầu tải image vài phút)
cd backend; uv sync; cd ..           # cài dependency Python
./scripts/dev.ps1 migrate            # tạo bảng PostgreSQL
./scripts/dev.ps1 seed               # tạo 3 API key dev – in ra MỘT LẦN, lưu lại
./scripts/dev.ps1 api                # API ở http://localhost:8000  (docs: /docs)
./scripts/dev.ps1 worker             # (cửa sổ khác) worker xử lý job
```

Hoặc chạy cả backend + worker trong Docker: `./scripts/dev.ps1 up` (vẫn cần `migrate`, `seed` từ máy host – PostgreSQL của Docker mở ở cổng host `PG_HOST_PORT`, mặc định **5433**).

Kiểm tra:

```powershell
curl http://localhost:8000/api/v1/health      # cả 3 kho "ok" → HTTP 200; có kho lỗi → 503
```

| Dịch vụ | Địa chỉ | Tài khoản dev |
|---|---|---|
| API | http://localhost:8000/docs | header `X-API-Key` |
| Neo4j Browser | http://localhost:7474 | `neo4j` / `NEO4J_PASSWORD` |
| PostgreSQL | `localhost:5433` (`PG_HOST_PORT`) | `POSTGRES_USER` / `POSTGRES_PASSWORD` |
| Elasticsearch | http://localhost:9200 | không xác thực (chỉ dev) |

## Các lệnh

| Lệnh | Việc |
|---|---|
| `up` / `up-deps` / `down` / `logs` / `ps` | Docker Compose |
| `migrate` | `alembic upgrade head` |
| `seed` | Tạo API key dev (`--rotate` để tạo lại: `cd backend; uv run python -m scripts.seed_api_keys --rotate`) |
| `api` / `worker` | Chạy local bằng uv |
| `test` / `test-unit` / `test-int` | pytest |
| `lint` / `fmt` / `typecheck` / `check` | ruff, mypy, toàn bộ |

## API key và vai trò

Bản dev xác thực bằng header `X-API-Key` (00-common §6). `seed` tạo 3 key:

| Key id | Vai trò | Quyền |
|---|---|---|
| `dev-user` | `nguoi_dung` | Hỏi đáp, tra cứu |
| `dev-editor` | `bien_tap_vien` | + duyệt quan hệ, sửa metadata |
| `dev-admin` | `quan_tri` | + pipeline, cấu hình, đánh giá |

DB chỉ lưu hash SHA-256 của key. Mất key → `seed --rotate`.

## Kết nối LM Studio (từ M01)

1. LM Studio → nạp model chat (máy dev hiện dùng `deepseek-r1-0528-qwen3-8b`, đặc tả chọn `qwen3.5-9b`) và model embedding (khuyến nghị `bge-m3`) → tab **Developer** → **Start Server**. Máy dev dùng cổng **1235**. Kết quả thử model: [docs/spikes/lmstudio.md](docs/spikes/lmstudio.md).
2. Backend chạy **trên máy host**: `LLM_BASE_URL=http://localhost:1235/v1`.
3. Backend chạy **trong Docker**: compose tự dùng `LLM_BASE_URL_DOCKER` (mặc định `http://host.docker.internal:1235/v1`); trong LM Studio bật **Serve on Local Network**.
4. Kiểm tra: `curl $LLM_BASE_URL/models` phải liệt kê 2 model.

LM Studio mặc định HTTP không xác thực – **chỉ mở trong mạng nội bộ** (inception §6.1, §8).

## Test

```powershell
./scripts/dev.ps1 test-unit     # không cần dịch vụ
./scripts/dev.ps1 test-int      # cần up-deps; dùng DB riêng legalgraph_test (tự tạo)
```

Test gọi LM Studio thật (chậm, vài phút) chỉ chạy khi bật: `$env:RUN_LMSTUDIO=1; cd backend; uv run pytest tests/lmstudio -s`.

Test tích hợp tự **skip** khi dịch vụ chưa chạy. Đặt `REQUIRE_SERVICES=postgres,neo4j,elasticsearch` để thiếu dịch vụ thì **fail** (CI đặt `postgres,neo4j`).

## Cấu trúc

```text
backend/
├── app/
│   ├── core/      config, logging JSON + request_id, lỗi chuẩn, auth X-API-Key, phân trang, đồng hồ VN
│   ├── db/        PostgreSQL, Neo4j (+ schema), Elasticsearch, file storage
│   ├── legal/     ID văn bản / điều khoản / phiên bản, khoảng hiệu lực
│   ├── models/    model dùng chung (TrangThaiHieuLuc, ThayDoi, Citation)
│   ├── jobs/      hàng đợi job PostgreSQL (SKIP LOCKED), registry handler, worker
│   ├── api/       router (health)
│   ├── main.py    FastAPI app
│   └── worker.py  entrypoint worker
├── alembic/       migration
├── scripts/       seed_api_keys
└── tests/         unit/, integration/
docker/            Dockerfile backend, Elasticsearch + ICU
scripts/dev.ps1    lệnh dev cho Windows
```

## Quy ước cho module sau

- **Bảng mới**: thêm ORM model, import vào `app/db/all_models.py`, tạo migration `cd backend; uv run alembic revision -m "..."`.
- **Job mới**: `@handler("<step>")` trong module nghiệp vụ, import module đó trong `app/worker.py::_register_handlers`; handler phải idempotent; enqueue bằng `app.jobs.queue.enqueue(conn, step, payload, dedupe_key=...)`.
- **"Hôm nay"**: luôn dùng `app.core.clock.today_vn()` (thay được bằng `APP_FAKE_TODAY` / `APP_FAKE_NOW`).
- **Hiệu lực**: luôn dùng `app.legal.validity.is_active()` – khoảng nửa mở `[tu, den)`.
- **ID**: luôn dùng `app.legal.ids` – không tự ghép chuỗi.
- **Lỗi**: ném `AppError(code, message, status_code=..., details=...)`.

## Xử lý sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| Neo4j `unhealthy` lần đầu | Đang tải plugin APOC / GDS – chờ 1–2 phút (`./scripts/dev.ps1 logs`) |
| Elasticsearch thoát ngay | Docker VM thiếu RAM – tăng trong Docker Desktop → Settings → Resources |
| `/health` báo `elasticsearch` lỗi "Thiếu plugin analysis-icu" | Build lại image: `docker compose build elasticsearch` |
| `uv run` lỗi múi giờ trên Windows | `uv sync` lại (cần gói `tzdata`) |
| Sửa `.env` mà container không nhận | `docker compose restart` giữ biến cũ – dùng `./scripts/dev.ps1 up` (hoặc `docker compose up -d`) để tạo lại container |
| `password authentication failed` khi migrate | Đang kết nối nhầm PostgreSQL cài sẵn trên máy ở cổng 5432 – dùng cổng `PG_HOST_PORT` (5433) trong `DATABASE_URL` |
