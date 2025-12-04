"""Add per-framework score columns for multi-framework comparison

Revision ID: 20251204_per_fw_scores
Revises: 20251202_fwparams
Create Date: 2025-12-04

"""
from alembic import op
import sqlalchemy as sa


revision = '20251204_per_fw_scores'
down_revision = '20251202_fwparams'
branch_labels = None
depends_on = None


def upgrade():
    # RICE framework scores
    op.add_column('initiatives', sa.Column('rice_value_score', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('rice_effort_score', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('rice_overall_score', sa.Float(), nullable=True))
    
    # WSJF framework scores
    op.add_column('initiatives', sa.Column('wsjf_value_score', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('wsjf_effort_score', sa.Float(), nullable=True))
    op.add_column('initiatives', sa.Column('wsjf_overall_score', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('initiatives', 'wsjf_overall_score')
    op.drop_column('initiatives', 'wsjf_effort_score')
    op.drop_column('initiatives', 'wsjf_value_score')
    op.drop_column('initiatives', 'rice_overall_score')
    op.drop_column('initiatives', 'rice_effort_score')
    op.drop_column('initiatives', 'rice_value_score')
