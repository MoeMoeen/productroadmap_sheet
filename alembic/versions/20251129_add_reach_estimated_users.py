"""add reach_estimated_users column to initiatives

Revision ID: 20251129_reach_field
Revises: 20251129_audit_cols
Create Date: 2025-11-29
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251129_reach_field'
down_revision = '20251129_audit_cols'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('initiatives') as batch_op:
        batch_op.add_column(sa.Column('reach_estimated_users', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('initiatives') as batch_op:
        batch_op.drop_column('reach_estimated_users')
