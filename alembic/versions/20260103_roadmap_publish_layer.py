"""Refocus roadmap as publish layer and add portfolio lineage

Revision ID: 20260103_roadmap_publish_layer
Revises: 20260103_phase5_optimization_models
Create Date: 2026-01-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "r20260103_publish"
down_revision = "r20260103_p5_opt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Roadmaps: add provenance to portfolios
    with op.batch_alter_table("roadmaps") as batch:
        batch.add_column(sa.Column("source_portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=True))

    # Roadmap entries: add lineage to portfolio items, remove duplicated optimization fields, add notes
    with op.batch_alter_table("roadmap_entries") as batch:
        batch.add_column(sa.Column("source_portfolio_item_id", sa.Integer(), sa.ForeignKey("portfolio_items.id"), nullable=True))
        batch.add_column(sa.Column("notes", sa.Text(), nullable=True))

        batch.drop_column("is_selected")
        batch.drop_column("is_mandatory_in_this_roadmap")
        batch.drop_column("value_score_used")
        batch.drop_column("effort_score_used")
        batch.drop_column("overall_score_used")
        batch.drop_column("optimization_run_id")
        batch.drop_column("scenario_label")

    op.create_index(
        "ix_roadmap_entries_source_portfolio_item_id",
        "roadmap_entries",
        ["source_portfolio_item_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_roadmap_entries_roadmap_initiative",
        "roadmap_entries",
        ["roadmap_id", "initiative_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_roadmap_entries_source_portfolio_item_id", table_name="roadmap_entries")
    op.drop_constraint(
        "uq_roadmap_entries_roadmap_initiative",
        "roadmap_entries",
        type_="unique",
    )

    with op.batch_alter_table("roadmap_entries") as batch:
        batch.drop_column("source_portfolio_item_id")
        batch.drop_column("notes")

        batch.add_column(sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("is_mandatory_in_this_roadmap", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("value_score_used", sa.Float(), nullable=True))
        batch.add_column(sa.Column("effort_score_used", sa.Float(), nullable=True))
        batch.add_column(sa.Column("overall_score_used", sa.Float(), nullable=True))
        batch.add_column(sa.Column("optimization_run_id", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("scenario_label", sa.String(length=100), nullable=True))

    with op.batch_alter_table("roadmaps") as batch:
        batch.drop_column("source_portfolio_id")
