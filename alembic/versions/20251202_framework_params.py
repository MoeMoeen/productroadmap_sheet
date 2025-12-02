"""Add framework-prefixed scoring parameter columns

Revision ID: 20251202_fwparams
Revises: 20251129_reach_field
Create Date: 2025-12-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251202_fwparams'
down_revision = '20251129_reach_field'
branch_labels = None
depends_on = None


def upgrade():
    # RICE framework parameters
    op.add_column('initiatives', sa.Column('rice_reach', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('rice_impact', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('rice_confidence', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('rice_effort', sa.Float(), nullable=True))
    
    # WSJF framework parameters
    op.add_column('initiatives', sa.Column('wsjf_business_value', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('wsjf_time_criticality', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('wsjf_risk_reduction', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('wsjf_job_size', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('initiatives', 'wsjf_job_size')
    op.drop_column('initiatives', 'wsjf_risk_reduction')
    op.drop_column('initiatives', 'wsjf_time_criticality')
    op.drop_column('initiatives', 'wsjf_business_value')
    op.drop_column('initiatives', 'rice_effort')
    op.drop_column('initiatives', 'rice_confidence')
    op.drop_column('initiatives', 'rice_impact')
    op.drop_column('initiatives', 'rice_reach')
