# Lệnh dev (Linux / macOS / Git Bash có make). Windows PowerShell: dùng scripts/dev.ps1 cùng tên lệnh.
.PHONY: help up up-deps down logs ps migrate seed test test-unit test-int lint fmt typecheck check

BACKEND := cd backend &&

help:
	@echo "up        – dựng toàn bộ (kho dữ liệu + backend + worker)"
	@echo "up-deps   – chỉ dựng Neo4j, PostgreSQL, Elasticsearch (chạy backend local bằng uv)"
	@echo "down      – dừng (giữ dữ liệu)"
	@echo "migrate   – alembic upgrade head"
	@echo "seed      – tạo 3 API key dev"
	@echo "test      – unit + integration;  test-unit / test-int"
	@echo "lint fmt typecheck check"

up:
	docker compose up -d --build

up-deps:
	docker compose up -d --build neo4j postgres elasticsearch

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

migrate:
	$(BACKEND) uv run alembic upgrade head

seed:
	$(BACKEND) uv run python -m scripts.seed_api_keys

test:
	$(BACKEND) uv run pytest

test-unit:
	$(BACKEND) uv run pytest tests/unit

test-int:
	$(BACKEND) uv run pytest tests/integration

lint:
	$(BACKEND) uv run ruff check . && uv run ruff format --check .

fmt:
	$(BACKEND) uv run ruff format . && uv run ruff check --fix .

typecheck:
	$(BACKEND) uv run mypy app scripts

check: lint typecheck test
