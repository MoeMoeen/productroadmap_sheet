"""merge_metrics_cols_and_lifecycle

Revision ID: 7068510c854f
Revises: 20260125_metrics_cols, 2304eed16ddb
Create Date: 2026-01-25 08:24:40.413474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7068510c854f'
down_revision: Union[str, Sequence[str], None] = ('20260125_metrics_cols', '2304eed16ddb')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
