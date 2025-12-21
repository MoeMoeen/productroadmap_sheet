"""Create action_runs table for sheet-native control plane

Revision ID: 20251221_action_runs
Revises: 20251220_widen_src_col
Create Date: 2025-12-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20251221_action_runs"
down_revision = "20251220_widen_src_col"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("requested_by_email", sa.String(length=255), nullable=True),
        sa.Column("requested_by_ui", sa.String(length=50), nullable=True),
        sa.Column("spreadsheet_id", sa.String(length=255), nullable=True),
        sa.Column("tab_name", sa.String(length=255), nullable=True),
        sa.Column("scope_type", sa.String(length=50), nullable=True),
        sa.Column("scope_summary", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_action_runs_run_id", "action_runs", ["run_id"], unique=True)
    op.create_index("ix_action_runs_action", "action_runs", ["action"])
    op.create_index("ix_action_runs_status", "action_runs", ["status"])
    op.create_index("ix_action_runs_created_at", "action_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_action_runs_created_at", table_name="action_runs")
    op.drop_index("ix_action_runs_status", table_name="action_runs")
    op.drop_index("ix_action_runs_action", table_name="action_runs")
    op.drop_index("ix_action_runs_run_id", table_name="action_runs")
    op.drop_table("action_runs")
