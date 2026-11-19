"""ocr_results 新增 params：记录每条识别结果实际用的 OCR 参数（T24c，decisions.md D42）。

已有的行填 {}，表示没有记录。不涉及索引结构，不需要重建索引。

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ocr_results",
        sa.Column(
            "params", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("ocr_results", "params")
