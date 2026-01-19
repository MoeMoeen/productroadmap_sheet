"""Drop Initiative constraint columns - moved to Constraints tab

Revision ID: 20260119_drop_init_constr
Revises: r20260109_prereq_dict
Create Date: 2026-01-19

Architectural change: Constraint entry surface is now exclusively the Constraints tab
in Optimization Center. Initiative-level constraint columns are removed to enforce
separation of concerns. Candidates tab becomes display-only for constraints.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "r20260119_drop_init_constr"
down_revision = "r20260109_prereq_dict"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Drop Initiative constraint columns.
    
    These fields are removed:
    - is_mandatory (bool)
    - mandate_reason (text)
    - bundle_key (text)
    - prerequisite_keys (text)
    - exclusion_keys (text)
    - synergy_group_keys (text)
    
    No data migration - all existing data is test/sample data.
    Constraints should be entered via Optimization Center Constraints tab.
    """
    op.drop_column("initiatives", "is_mandatory")
    op.drop_column("initiatives", "mandate_reason")
    op.drop_column("initiatives", "bundle_key")
    op.drop_column("initiatives", "prerequisite_keys")
    op.drop_column("initiatives", "exclusion_keys")
    op.drop_column("initiatives", "synergy_group_keys")


def downgrade() -> None:
    """
    Restore Initiative constraint columns (for rollback only).
    """
    op.add_column("initiatives", sa.Column("is_mandatory", sa.Boolean(), nullable=True))
    op.add_column("initiatives", sa.Column("mandate_reason", sa.Text(), nullable=True))
    op.add_column("initiatives", sa.Column("bundle_key", sa.Text(), nullable=True))
    op.add_column("initiatives", sa.Column("prerequisite_keys", sa.Text(), nullable=True))
    op.add_column("initiatives", sa.Column("exclusion_keys", sa.Text(), nullable=True))
    op.add_column("initiatives", sa.Column("synergy_group_keys", sa.Text(), nullable=True))
