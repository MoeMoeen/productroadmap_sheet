"""20260121_multiple_math_models_per_initiative

Revision ID: 20260121_multi_mm
Revises: 20260119_drop_initiative_constraints
Create Date: 2026-01-21

Changes:
1. Add initiative_id FK to initiative_math_models (enable 1:N relationship)
2. Add target_kpi_key, is_primary, computed_score to initiative_math_models
3. Remove math_model_id FK from initiatives (replaced by relationship)
4. Migrate existing data: copy math_model_id to initiative_id in math_models
5. Drop math_model_id column from initiatives

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260121_multi_mm'
down_revision = 'r20260119_drop_init_constr'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add initiative_id to initiative_math_models
    op.add_column('initiative_math_models', sa.Column('initiative_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_initiative_math_models_initiative_id',
        'initiative_math_models',
        'initiatives',
        ['initiative_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_initiative_math_models_initiative_id', 'initiative_math_models', ['initiative_id'])
    
    # Step 2: Add new fields for multiple math models support
    op.add_column('initiative_math_models', sa.Column('target_kpi_key', sa.String(100), nullable=True))
    op.add_column('initiative_math_models', sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('initiative_math_models', sa.Column('computed_score', sa.Float(), nullable=True))
    
    # Step 3: Migrate existing data - copy initiative references
    # For existing math models, set initiative_id from the initiative.math_model_id reference
    op.execute("""
        UPDATE initiative_math_models imm
        SET initiative_id = (
            SELECT i.id 
            FROM initiatives i 
            WHERE i.math_model_id = imm.id
        )
    """)
    
    # Step 4: Set is_primary = true for all existing models (they're the only model per initiative)
    op.execute("UPDATE initiative_math_models SET is_primary = true WHERE initiative_id IS NOT NULL")
    
    # Step 5: Make initiative_id NOT NULL now that data is migrated
    op.alter_column('initiative_math_models', 'initiative_id', nullable=False)
    
    # Step 6: Drop the old FK from initiatives table
    op.drop_constraint('initiatives_math_model_id_fkey', 'initiatives', type_='foreignkey')
    op.drop_column('initiatives', 'math_model_id')


def downgrade() -> None:
    # Restore math_model_id column
    op.add_column('initiatives', sa.Column('math_model_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'initiatives_math_model_id_fkey',
        'initiatives',
        'initiative_math_models',
        ['math_model_id'],
        ['id']
    )
    
    # Restore references: for each initiative, pick the primary math model (or first one)
    op.execute("""
        UPDATE initiatives i
        SET math_model_id = (
            SELECT id 
            FROM initiative_math_models imm 
            WHERE imm.initiative_id = i.id 
            ORDER BY is_primary DESC, id ASC 
            LIMIT 1
        )
    """)
    
    # Drop new columns and constraints from initiative_math_models
    op.drop_index('ix_initiative_math_models_initiative_id', table_name='initiative_math_models')
    op.drop_constraint('fk_initiative_math_models_initiative_id', 'initiative_math_models', type_='foreignkey')
    op.drop_column('initiative_math_models', 'computed_score')
    op.drop_column('initiative_math_models', 'is_primary')
    op.drop_column('initiative_math_models', 'target_kpi_key')
    op.drop_column('initiative_math_models', 'initiative_id')
