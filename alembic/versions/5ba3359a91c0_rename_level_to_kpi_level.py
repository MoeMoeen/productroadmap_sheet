"""rename_level_to_kpi_level

Revision ID: 5ba3359a91c0
Revises: 20260122_metric_chain
Create Date: 2026-01-22 12:23:55.574808

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ba3359a91c0'
down_revision: Union[str, Sequence[str], None] = '20260122_metric_chain'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Rename column 'level' to 'kpi_level' in organization_metric_configs
    op.alter_column(
        'organization_metric_configs',
        'level',
        new_column_name='kpi_level'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Rename column 'kpi_level' back to 'level'
    op.alter_column(
        'organization_metric_configs',
        'kpi_level',
        new_column_name='level'
    )
