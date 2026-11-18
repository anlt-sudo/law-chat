"""M00 – bảng nền: api_key, pipeline_run, pipeline_job

Revision ID: 0001_base
Revises:
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_base"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # (bổ sung) API key cho bản dev – 00-common §6
    op.execute(
        """
        CREATE TABLE api_key (
            id          TEXT PRIMARY KEY,
            key_hash    VARCHAR(64) NOT NULL,
            role        TEXT NOT NULL,
            enabled     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_api_key_key_hash UNIQUE (key_hash),
            CONSTRAINT ck_api_key_role CHECK (role IN ('nguoi_dung','bien_tap_vien','quan_tri'))
        )
        """
    )

    # F15 §6, tạo sớm cho mọi module
    op.execute(
        """
        CREATE TABLE pipeline_run (
            id          UUID PRIMARY KEY,
            type        TEXT NOT NULL,
            trigger     TEXT NOT NULL,
            params      JSONB NOT NULL DEFAULT '{}',
            status      TEXT NOT NULL,
            summary     JSONB NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            CONSTRAINT ck_pipeline_run_trigger CHECK (trigger IN ('schedule','manual','event')),
            CONSTRAINT ck_pipeline_run_status
                CHECK (status IN ('QUEUED','RUNNING','DONE','PARTIAL','FAILED'))
        )
        """
    )

    # F15 §6 + (bổ sung) priority, run_after, dedupe_key.
    # FK source_document_id được thêm ở M02 khi có bảng source_document.
    op.execute(
        """
        CREATE TABLE pipeline_job (
            id                 UUID PRIMARY KEY,
            run_id             UUID REFERENCES pipeline_run(id),
            step               TEXT NOT NULL,
            source_document_id UUID,
            payload            JSONB NOT NULL DEFAULT '{}',
            status             TEXT NOT NULL,
            priority           SMALLINT NOT NULL DEFAULT 3,
            run_after          TIMESTAMPTZ NOT NULL DEFAULT now(),
            dedupe_key         VARCHAR,
            attempts           INT NOT NULL DEFAULT 0,
            error              TEXT,
            queued_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at         TIMESTAMPTZ,
            finished_at        TIMESTAMPTZ,
            CONSTRAINT ck_pipeline_job_status
                CHECK (status IN ('QUEUED','RUNNING','DONE','FAILED','CANCELLED'))
        )
        """
    )
    op.execute("CREATE INDEX ix_pipeline_job_claim ON pipeline_job (status, priority, run_after)")
    op.execute(
        "CREATE UNIQUE INDEX uq_pipeline_job_dedupe_active ON pipeline_job (dedupe_key) "
        "WHERE status IN ('QUEUED','RUNNING')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pipeline_job")
    op.execute("DROP TABLE IF EXISTS pipeline_run")
    op.execute("DROP TABLE IF EXISTS api_key")
