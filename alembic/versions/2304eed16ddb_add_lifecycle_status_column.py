"""add_lifecycle_status_column

Revision ID: 2304eed16ddb
Revises: 3315d6fc1ff2
Create Date: 2026-01-23 19:52:31.416364

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2304eed16ddb'
down_revision: Union[str, Sequence[str], None] = '3315d6fc1ff2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'initiatives',
        sa.Column('lifecycle_status', sa.String(50), nullable=False, server_default='new')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('initiatives', 'lifecycle_status')
