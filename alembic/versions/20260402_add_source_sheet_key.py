"""20260402_add_source_sheet_key

Revision ID: 20260402_add_source_sheet_key
Revises: 20260330_soft_archive
Create Date: 2026-04-02

Changes:
1. Add source_sheet_key to initiatives

Rationale:
- Persist a stable, human-readable intake source identifier from config
- Support PM-facing backlog display of intake provenance without relying on mutable sheet titles
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260402_add_source_sheet_key"
down_revision = "20260330_soft_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("initiatives")}

    if "source_sheet_key" not in existing_columns:
        op.add_column("initiatives", sa.Column("source_sheet_key", sa.String(length=255), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("initiatives")}

    if "source_sheet_key" in existing_columns:
        op.drop_column("initiatives", "source_sheet_key")