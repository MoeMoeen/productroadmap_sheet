"""Remove deprecated reach_estimated_users column

Revision ID: 20251204_drop_deprecated
Revises: 20251204_per_fw_scores
Create Date: 2025-12-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251204_drop_deprecated'
down_revision = '20251204_per_fw_scores'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the deprecated reach_estimated_users column
    with op.batch_alter_table('initiatives', schema=None) as batch_op:
        batch_op.drop_column('reach_estimated_users')


def downgrade() -> None:
    # Restore the column if rolling back (though it's deprecated, keep for rollback safety)
    with op.batch_alter_table('initiatives', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reach_estimated_users', sa.Float(), nullable=True))
