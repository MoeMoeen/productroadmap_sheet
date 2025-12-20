"""Add scoring provenance columns to initiatives

Revision ID: 20251220_add_scoring_prov
Revises: 20251216_math_warnings_active_fw
Create Date: 2025-12-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20251220_add_scoring_prov"
down_revision = "20251216_math_warnings_active_fw"
branch_labels = None
depends_on = None


def upgrade():
    """Add scoring provenance columns if they do not already exist."""
    from sqlalchemy import inspect
    from alembic import context

    conn = context.get_bind()
    inspector = inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("initiatives")}

    if "scoring_updated_source" not in existing_columns:
        op.add_column("initiatives", sa.Column("scoring_updated_source", sa.String(length=50), nullable=True))

    if "scoring_updated_at" not in existing_columns:
        op.add_column("initiatives", sa.Column("scoring_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    """Remove scoring provenance columns."""
    op.drop_column("initiatives", "scoring_updated_at")
    op.drop_column("initiatives", "scoring_updated_source")
