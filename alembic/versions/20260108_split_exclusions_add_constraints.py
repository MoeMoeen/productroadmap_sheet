"""Split exclusions and add prerequisites/synergies JSON columns

Revision ID: 20260108_split_exclusions
Revises: 20260103_roadmap_publish_layer
Create Date: 2026-01-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "r20260108_split_excl"
down_revision = "r260104_mcjson_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new JSON columns for split exclusions and prerequisites/synergies
    with op.batch_alter_table("optimization_constraint_sets") as batch:
        batch.add_column(sa.Column("exclusions_initiatives_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("exclusions_pairs_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("prerequisites_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("synergy_bonuses_json", sa.JSON(), nullable=True))
    
    # Note: exclusions_json column retained for backwards compatibility
    # New code should use exclusions_initiatives_json and exclusions_pairs_json


def downgrade() -> None:
    with op.batch_alter_table("optimization_constraint_sets") as batch:
        batch.drop_column("synergy_bonuses_json")
        batch.drop_column("prerequisites_json")
        batch.drop_column("exclusions_pairs_json")
        batch.drop_column("exclusions_initiatives_json")
