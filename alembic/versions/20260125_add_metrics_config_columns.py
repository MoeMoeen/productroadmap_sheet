"""20260125_add_metrics_config_columns

Revision ID: 20260125_metrics_cols
Revises: 20260122_metric_chain
Create Date: 2026-01-25

Changes:
1. Add description (Text) to organization_metric_configs
2. Add is_active (Boolean) to organization_metric_configs  
3. Add notes (Text) to organization_metric_configs

Rationale:
- Aligns DB schema with ProductOps Metrics_Config sheet columns
- Enables proper is_active filtering for north_star KPI resolution
- Supports PM descriptions and notes for KPI documentation
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260125_metrics_cols'
down_revision = '20260122_metric_chain'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add description column
    op.add_column(
        'organization_metric_configs',
        sa.Column('description', sa.Text(), nullable=True)
    )
    
    # Add is_active column (defaults to True for existing rows)
    op.add_column(
        'organization_metric_configs',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true')
    )
    
    # Add notes column
    op.add_column(
        'organization_metric_configs',
        sa.Column('notes', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('organization_metric_configs', 'notes')
    op.drop_column('organization_metric_configs', 'is_active')
    op.drop_column('organization_metric_configs', 'description')
