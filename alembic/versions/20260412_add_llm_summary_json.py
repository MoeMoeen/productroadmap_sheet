"""Add structured LLM summary JSON to initiatives

Revision ID: 20260412_add_llm_summary_json
Revises: 20260402_add_source_sheet_key
Create Date: 2026-04-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260412_add_llm_summary_json"
down_revision = "20260402_add_source_sheet_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("initiatives")}

    if "llm_summary_json" not in existing_columns:
        op.add_column("initiatives", sa.Column("llm_summary_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("initiatives")}

    if "llm_summary_json" in existing_columns:
        op.drop_column("initiatives", "llm_summary_json")