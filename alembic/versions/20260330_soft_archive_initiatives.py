"""20260330_soft_archive_initiatives

Revision ID: 20260330_soft_archive
Revises: 7068510c854f
Create Date: 2026-03-30

Changes:
1. Add is_archived flag to initiatives
2. Add archived_at timestamp to initiatives
3. Add archived_reason text to initiatives

Rationale:
- Preserve auditability for initiatives removed from intake sheets
- Prevent stale intake-managed initiatives from continuing to appear in backlog views
- Support future restore/unarchive behavior without hard deletion
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260330_soft_archive"
down_revision = "7068510c854f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("initiatives")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("initiatives")}

    if "is_archived" not in existing_columns:
        op.add_column(
            "initiatives",
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    if "archived_at" not in existing_columns:
        op.add_column("initiatives", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    if "archived_reason" not in existing_columns:
        op.add_column("initiatives", sa.Column("archived_reason", sa.String(length=100), nullable=True))

    if "ix_initiatives_is_archived" not in existing_indexes:
        op.create_index("ix_initiatives_is_archived", "initiatives", ["is_archived"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("initiatives")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("initiatives")}

    if "ix_initiatives_is_archived" in existing_indexes:
        op.drop_index("ix_initiatives_is_archived", table_name="initiatives")

    if "archived_reason" in existing_columns:
        op.drop_column("initiatives", "archived_reason")

    if "archived_at" in existing_columns:
        op.drop_column("initiatives", "archived_at")

    if "is_archived" in existing_columns:
        op.drop_column("initiatives", "is_archived")