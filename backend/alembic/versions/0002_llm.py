"""M01 – llm_call_log (F17 §6.2) + runtime_flag (bổ sung)

Revision ID: 0002_llm
Revises: 0001_base
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_llm"
down_revision: str | None = "0001_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE llm_call_log (
            id               BIGSERIAL PRIMARY KEY,
            task             TEXT NOT NULL,
            model            TEXT NOT NULL,
            priority         SMALLINT NOT NULL,
            thinking         BOOLEAN NOT NULL,
            attempts         SMALLINT NOT NULL,
            tokens_in        INT,
            tokens_out       INT,
            reasoning_tokens INT,          -- bổ sung: DeepSeek R1 luôn suy nghĩ
            queue_ms         INT,
            latency_ms       INT,
            outcome          TEXT NOT NULL,
            error            TEXT,
            prompt           JSONB,         -- chỉ khi LLM_LOG_CONTENT
            output           TEXT,
            caller_ref       TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_llm_call_log_outcome CHECK (outcome IN
                ('ok','json_error','timeout','unavailable','context_too_long','error'))
        )
        """
    )
    op.execute("CREATE INDEX ix_llm_call_log_task_created_at ON llm_call_log (task, created_at)")
    op.execute(
        """
        CREATE TABLE runtime_flag (
            key         TEXT PRIMARY KEY,
            value_ts    TIMESTAMPTZ,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS runtime_flag")
    op.execute("DROP TABLE IF EXISTS llm_call_log")
