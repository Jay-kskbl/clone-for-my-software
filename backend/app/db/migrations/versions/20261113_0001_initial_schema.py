"""初始表结构：GLOBAL §6 的全部核心实体。

Revision ID: 0001
Revises:
Create Date: 2026-11-13 04:38:46.299008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_results_path", sa.String(length=512), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment_runs")),
    )
    op.create_table(
        "image_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", postgresql.ARRAY(sa.REAL()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("dim >= 1", name=op.f("ck_image_embeddings_dim_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_image_embeddings")),
        sa.UniqueConstraint(
            "sha256",
            "model_name",
            "model_version",
            name=op.f("uq_image_embeddings_sha256_model_name_model_version"),
        ),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="user", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'admin')", name=op.f("ck_users_role_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("parse_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name=op.f("ck_documents_status_valid"),
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_documents_size_non_negative")),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_documents_owner_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_documents_storage_key")),
    )
    op.create_index(op.f("ix_documents_deleted_at"), "documents", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_documents_owner_id"), "documents", ["owner_id"], unique=False)
    op.create_index(op.f("ix_documents_sha256"), "documents", ["sha256"], unique=False)
    op.create_table(
        "search_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("channels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Double(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_search_logs_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_logs")),
    )
    op.create_index(op.f("ix_search_logs_created_at"), "search_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_search_logs_user_id"), "search_logs", ["user_id"], unique=False)
    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("parse_version", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=8), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN ('body', 'ocr')", name=op.f("ck_document_chunks_source_type_valid")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("chunk_id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint(
            "document_id",
            "parse_version",
            "seq",
            name=op.f("uq_document_chunks_document_id_parse_version_seq"),
        ),
    )
    op.create_table(
        "document_shares",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_shares_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_document_shares_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", "user_id", name=op.f("pk_document_shares")),
    )
    op.create_index(
        op.f("ix_document_shares_user_id"), "document_shares", ["user_id"], unique=False
    )
    op.create_table(
        "document_tags",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_tags_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], name=op.f("fk_document_tags_tag_id_tags"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("document_id", "tag_id", name=op.f("pk_document_tags")),
    )
    op.create_index(op.f("ix_document_tags_tag_id"), "document_tags", ["tag_id"], unique=False)
    op.create_table(
        "image_assets",
        sa.Column("image_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_image_assets_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("image_id", name=op.f("pk_image_assets")),
    )
    op.create_index(
        op.f("ix_image_assets_document_id"), "image_assets", ["document_id"], unique=False
    )
    op.create_index(op.f("ix_image_assets_sha256"), "image_assets", ["sha256"], unique=False)
    op.create_table(
        "ocr_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lines", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_ocr_results_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ocr_results")),
    )
    op.create_index(
        op.f("ix_ocr_results_document_id"), "ocr_results", ["document_id"], unique=False
    )
    op.create_table(
        "processing_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name=op.f("ck_processing_tasks_status_valid"),
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts >= 1", name=op.f("ck_processing_tasks_attempts_valid")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_processing_tasks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_tasks")),
    )
    op.create_index(
        "ix_processing_tasks_claim",
        "processing_tasks",
        ["status", "task_type", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_processing_tasks_document_id"), "processing_tasks", ["document_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_processing_tasks_document_id"), table_name="processing_tasks")
    op.drop_index("ix_processing_tasks_claim", table_name="processing_tasks")
    op.drop_table("processing_tasks")
    op.drop_index(op.f("ix_ocr_results_document_id"), table_name="ocr_results")
    op.drop_table("ocr_results")
    op.drop_index(op.f("ix_image_assets_sha256"), table_name="image_assets")
    op.drop_index(op.f("ix_image_assets_document_id"), table_name="image_assets")
    op.drop_table("image_assets")
    op.drop_index(op.f("ix_document_tags_tag_id"), table_name="document_tags")
    op.drop_table("document_tags")
    op.drop_index(op.f("ix_document_shares_user_id"), table_name="document_shares")
    op.drop_table("document_shares")
    op.drop_table("document_chunks")
    op.drop_index(op.f("ix_search_logs_user_id"), table_name="search_logs")
    op.drop_index(op.f("ix_search_logs_created_at"), table_name="search_logs")
    op.drop_table("search_logs")
    op.drop_index(op.f("ix_documents_sha256"), table_name="documents")
    op.drop_index(op.f("ix_documents_owner_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_deleted_at"), table_name="documents")
    op.drop_table("documents")
    op.drop_table("users")
    op.drop_table("tags")
    op.drop_table("image_embeddings")
    op.drop_table("experiment_runs")
