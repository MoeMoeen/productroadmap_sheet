"""Add metric_chain_text to initiative_math_models

Revision ID: r260104_mctext_add
Revises: r260104_mcjson_add
Create Date: 2026-01-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "r260104_mctext_add"
down_revision = "r260104_mcjson_add"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("initiative_math_models") as batch:
        batch.add_column(sa.Column("metric_chain_text", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("initiative_math_models") as batch:
        batch.drop_column("metric_chain_text")
