"""add components_json and warnings_json to initiative_scores

Revision ID: 20251129_audit_cols
Revises: 
Create Date: 2025-11-29
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251129_audit_cols'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Use `op.add_column` guarded by existence checks where possible
    with op.batch_alter_table('initiative_scores') as batch_op:
        batch_op.add_column(sa.Column('components_json', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('warnings_json', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('initiative_scores') as batch_op:
        batch_op.drop_column('warnings_json')
        batch_op.drop_column('components_json')
