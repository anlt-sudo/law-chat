"""Cấu hình ứng dụng, đọc từ biến môi trường / file .env (00-common, inception 6.1)."""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env ở thư mục gốc repo (chạy từ backend/) hoặc ngay thư mục hiện tại
        env_file=(_BACKEND_DIR.parent / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- ứng dụng ----
    app_env: str = "dev"
    log_level: str = "INFO"
    app_fake_today: date | None = None
    app_fake_now: datetime | None = None
    data_dir: Path = _BACKEND_DIR.parent / "data"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    job_stale_minutes: int = 30
    worker_poll_interval_s: float = 1.0

    # ---- PostgreSQL ----
    database_url: str = "postgresql+asyncpg://legalgraph:legalgraph-dev@localhost:5433/legalgraph"

    # ---- Neo4j ----
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "legalgraph-dev"
    neo4j_database: str = "neo4j"

    # ---- Elasticsearch ----
    es_url: str = "http://localhost:9200"

    # ---- Embedding (cần ngay để tạo vector index Neo4j) ----
    # Máy dev dùng nomic-embed-text v1.5 (768 chiều) – docs/spikes/lmstudio.md
    embedding_dim: int = 768

    # ---- LLM Gateway (F17 §6.1 + điều chỉnh M01 §2b) ----
    llm_base_url: str = "http://localhost:1235/v1"
    llm_api_key: str = "lm-studio"
    llm_model: str = "deepseek-r1-0528-qwen3-8b"
    embedding_model: str = "text-embedding-nomic-embed-text-v1.5"
    embedding_query_prefix: str = "search_query: "
    embedding_document_prefix: str = "search_document: "
    embedding_context_tokens: int = 2048
    embedding_batch_size: int = 32
    llm_temperature: float = 0.1
    llm_context_tokens: int = 8192
    llm_max_concurrency: int = 1
    embed_max_concurrency: int = 2
    chat_thinking: bool = True
    # none: model luôn suy nghĩ (DeepSeek R1) – không chèn chỉ thị;
    # template: chat_template_kwargs.enable_thinking; soft_switch: thêm "/no_think"
    thinking_mode: Literal["none", "template", "soft_switch"] = "none"
    # json_schema: response_format do LM Studio ép; prompt: mô tả schema trong prompt
    llm_json_mode: Literal["json_schema", "prompt"] = "json_schema"
    llm_json_max_attempts: int = 3
    llm_reasoning_budget: int = 600  # token cộng thêm vào max_tokens cho phần suy nghĩ
    llm_chars_per_token: float = 2.5
    llm_log_content: bool = True
    trace_thinking: bool = False
    llm_health_interval_s: float = 30.0
    # Ghi đè timeout theo tác vụ, vd LLM_TIMEOUTS='{"chat_answer": 240}'
    llm_timeouts: dict[str, float] = Field(default_factory=dict)

    @field_validator("app_fake_today", "app_fake_now", mode="before")
    @classmethod
    def _empty_as_none(cls, v: object) -> object:
        return None if v == "" else v

    @field_validator("data_dir", mode="after")
    @classmethod
    def _resolve_data_dir(cls, v: Path) -> Path:
        # Đường dẫn tương đối tính từ thư mục backend/, không phụ thuộc cwd
        return v if v.is_absolute() else (_BACKEND_DIR / v).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
