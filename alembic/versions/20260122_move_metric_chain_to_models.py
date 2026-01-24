"""20260122_move_metric_chain_to_models

Revision ID: 20260122_metric_chain
Revises: 20260121_multi_mm
Create Date: 2026-01-22

Changes:
1. Add metric_chain_json to initiative_math_models (parsed JSON version)
2. Migrate Initiative.metric_chain_json to primary model's metric_chain_json
3. Drop Initiative.metric_chain_json (moved to model level)

Rationale:
- Each math model targets a specific KPI with its own metric chain
- No single "initiative chain" makes sense with multiple models
- Avoids duplication and maintains single source of truth
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260122_metric_chain'
down_revision = '20260121_multi_mm'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add metric_chain_json to initiative_math_models (parsed version)
    op.add_column('initiative_math_models', sa.Column('metric_chain_json', sa.JSON(), nullable=True))
    
    # Step 2: Migrate existing Initiative.metric_chain_json to primary model
    # For each initiative with metric_chain_json, copy to its primary math model
    op.execute("""
        UPDATE initiative_math_models imm
        SET metric_chain_json = (
            SELECT i.metric_chain_json
            FROM initiatives i
            WHERE i.id = imm.initiative_id
            AND i.metric_chain_json IS NOT NULL
            AND imm.is_primary = true
        )
        WHERE imm.is_primary = true
        AND EXISTS (
            SELECT 1 FROM initiatives i 
            WHERE i.id = imm.initiative_id 
            AND i.metric_chain_json IS NOT NULL
        )
    """)
    
    # Step 3: Drop metric_chain_json from initiatives (now at model level)
    op.drop_column('initiatives', 'metric_chain_json')


def downgrade() -> None:
    # Restore metric_chain_json column to initiatives
    op.add_column('initiatives', sa.Column('metric_chain_json', sa.JSON(), nullable=True))
    
    # Migrate back: copy from primary model to initiative
    op.execute("""
        UPDATE initiatives i
        SET metric_chain_json = (
            SELECT imm.metric_chain_json
            FROM initiative_math_models imm
            WHERE imm.initiative_id = i.id
            AND imm.is_primary = true
            AND imm.metric_chain_json IS NOT NULL
            ORDER BY imm.id
            LIMIT 1
        )
    """)
    
    # Drop metric_chain_json from math models
    op.drop_column('initiative_math_models', 'metric_chain_json')
