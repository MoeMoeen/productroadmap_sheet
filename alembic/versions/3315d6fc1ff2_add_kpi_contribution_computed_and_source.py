"""add_kpi_contribution_computed_and_source

Revision ID: 3315d6fc1ff2
Revises: 5ba3359a91c0
Create Date: 2026-01-22 13:17:16.713969

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3315d6fc1ff2'
down_revision: Union[str, Sequence[str], None] = '5ba3359a91c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add kpi_contribution_computed_json column (system-computed contributions)
    op.add_column(
        'initiatives',
        sa.Column('kpi_contribution_computed_json', sa.JSON(), nullable=True)
    )
    
    # Add kpi_contribution_source column (tracks if PM override or computed)
    op.add_column(
        'initiatives',
        sa.Column('kpi_contribution_source', sa.String(50), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('initiatives', 'kpi_contribution_source')
    op.drop_column('initiatives', 'kpi_contribution_computed_json')
