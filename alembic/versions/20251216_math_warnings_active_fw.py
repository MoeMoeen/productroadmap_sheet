"""Add math_warnings and active_scoring_framework to initiatives

Revision ID: 20251216_math_warnings_active_fw
Revises: 20251214_phase4_math_models
Create Date: 2025-12-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20251216_math_warnings_active_fw"
down_revision = "20251214_phase4_math_models"
branch_labels = None
depends_on = None


def upgrade():
    """Add math_warnings and active_scoring_framework columns to initiatives."""
    # Use IF NOT EXISTS for idempotent upgrades (Postgres only; skip for SQLite if needed)
    from sqlalchemy import inspect
    from alembic import context
    
    conn = context.get_bind()
    inspector = inspect(conn)
    existing_columns = {col['name'] for col in inspector.get_columns('initiatives')}
    
    if 'math_warnings' not in existing_columns:
        op.add_column("initiatives", sa.Column("math_warnings", sa.Text(), nullable=True))
    
    if 'active_scoring_framework' not in existing_columns:
        op.add_column("initiatives", sa.Column("active_scoring_framework", sa.String(length=50), nullable=True))


def downgrade():
    """Remove math_warnings and active_scoring_framework columns from initiatives."""
    op.drop_column("initiatives", "active_scoring_framework")
    op.drop_column("initiatives", "math_warnings")
