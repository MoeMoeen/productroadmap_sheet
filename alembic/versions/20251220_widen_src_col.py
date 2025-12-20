"""Widen updated_source column for provenance tokens

Revision ID: 20251220_widen_src_col
Revises: 20251220_add_scoring_prov
Create Date: 2025-12-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20251220_widen_src_col"
down_revision = "20251220_add_scoring_prov"
branch_labels = None
depends_on = None


def upgrade():
    """Widen updated_source to handle canonical tokens."""
    op.alter_column(
        "initiatives",
        "updated_source",
        existing_type=sa.String(length=20),
        type_=sa.String(length=100),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "initiatives",
        "updated_source",
        existing_type=sa.String(length=100),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
