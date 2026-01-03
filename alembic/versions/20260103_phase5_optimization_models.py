"""Phase 5 optimization models and cleanup

Revision ID: 20260103_phase5_optimization_models
Revises: 20251221_action_runs
Create Date: 2026-01-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "r20260103_p5_opt"
down_revision = "20251221_action_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop deprecated Initiative fields
    with op.batch_alter_table("initiatives") as batch:
        batch.drop_column("current_pain")
        batch.drop_column("desired_outcome")
        batch.drop_column("target_metrics")
        batch.drop_column("strategic_theme")
        batch.drop_column("linked_objectives")
        batch.drop_column("expected_impact_description")
        batch.drop_column("impact_metric")
        batch.drop_column("impact_unit")
        batch.drop_column("impact_low")
        batch.drop_column("impact_expected")
        batch.drop_column("impact_high")
        batch.drop_column("total_cost_estimate")
        batch.drop_column("time_sensitivity")
        batch.drop_column("missing_fields")
        batch.drop_column("llm_notes")
        batch.drop_column("math_warnings")

    # Add new Initiative fields for Phase 5
    with op.batch_alter_table("initiatives") as batch:
        batch.add_column(sa.Column("market", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("department", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("category", sa.String(length=100), nullable=True))

        batch.add_column(sa.Column("immediate_kpi_key", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("metric_chain_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("kpi_contribution_json", sa.JSON(), nullable=True))

        batch.add_column(sa.Column("engineering_tokens", sa.Float(), nullable=True))
        batch.add_column(sa.Column("engineering_tokens_mvp", sa.Float(), nullable=True))
        batch.add_column(sa.Column("engineering_tokens_full", sa.Float(), nullable=True))
        batch.add_column(sa.Column("scope_mode", sa.String(length=50), nullable=True))

        batch.add_column(sa.Column("mandate_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("program_key", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("bundle_key", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("prerequisite_keys", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("exclusion_keys", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("synergy_group_keys", sa.JSON(), nullable=True))

        batch.add_column(sa.Column("time_sensitivity_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("earliest_start_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("latest_finish_date", sa.Date(), nullable=True))

        batch.add_column(sa.Column("is_optimization_candidate", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("candidate_period_key", sa.String(length=50), nullable=True))

    op.create_index(
        "ix_initiatives_candidate_period_key",
        "initiatives",
        ["candidate_period_key"],
        unique=False,
    )

    # Add InitiativeMathModel fields
    with op.batch_alter_table("initiative_math_models") as batch:
        batch.add_column(sa.Column("model_name", sa.String(length=150), nullable=True))
        batch.add_column(sa.Column("model_description_free_text", sa.Text(), nullable=True))

    # New table: organization_metric_configs
    op.create_table(
        "organization_metric_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kpi_key", sa.String(length=100), nullable=False),
        sa.Column("kpi_name", sa.String(length=255), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_organization_metric_configs_kpi_key",
        "organization_metric_configs",
        ["kpi_key"],
        unique=True,
    )

    # New table: optimization_scenarios
    op.create_table(
        "optimization_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("period_key", sa.String(length=100), nullable=True),
        sa.Column("objective_mode", sa.String(length=50), nullable=False),
        sa.Column("objective_weights_json", sa.JSON(), nullable=True),
        sa.Column("capacity_total_tokens", sa.Float(), nullable=True),
        sa.Column("capacity_by_market_json", sa.JSON(), nullable=True),
        sa.Column("capacity_by_department_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_optimization_scenarios_period_key", "optimization_scenarios", ["period_key"], unique=False)

    # New table: optimization_constraint_sets
    op.create_table(
        "optimization_constraint_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("optimization_scenarios.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("floors_json", sa.JSON(), nullable=True),
        sa.Column("caps_json", sa.JSON(), nullable=True),
        sa.Column("targets_json", sa.JSON(), nullable=True),
        sa.Column("mandatory_initiatives_json", sa.JSON(), nullable=True),
        sa.Column("bundles_json", sa.JSON(), nullable=True),
        sa.Column("exclusions_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_optimization_constraint_sets_scenario_id",
        "optimization_constraint_sets",
        ["scenario_id"],
        unique=False,
    )

    # New table: optimization_runs
    op.create_table(
        "optimization_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("optimization_scenarios.id"), nullable=False),
        sa.Column("constraint_set_id", sa.Integer(), sa.ForeignKey("optimization_constraint_sets.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("requested_by_email", sa.String(length=255), nullable=True),
        sa.Column("requested_by_ui", sa.String(length=50), nullable=True),
        sa.Column("inputs_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("solver_name", sa.String(length=50), nullable=True),
        sa.Column("solver_version", sa.String(length=50), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_optimization_runs_run_id", "optimization_runs", ["run_id"], unique=True)
    op.create_index("ix_optimization_runs_status", "optimization_runs", ["status"], unique=False)
    op.create_index("ix_optimization_runs_scenario_id", "optimization_runs", ["scenario_id"], unique=False)

    # New table: portfolios
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("optimization_scenarios.id"), nullable=False),
        sa.Column("optimization_run_id", sa.Integer(), sa.ForeignKey("optimization_runs.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_baseline", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_portfolios_scenario_id", "portfolios", ["scenario_id"], unique=False)
    op.create_index("ix_portfolios_optimization_run_id", "portfolios", ["optimization_run_id"], unique=False)

    # New table: portfolio_items
    op.create_table(
        "portfolio_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("initiative_id", sa.Integer(), sa.ForeignKey("initiatives.id"), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allocated_tokens", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_portfolio_items_portfolio_id", "portfolio_items", ["portfolio_id"], unique=False)
    op.create_index("ix_portfolio_items_initiative_id", "portfolio_items", ["initiative_id"], unique=False)
    op.create_unique_constraint(
        "uq_portfolio_items_portfolio_initiative",
        "portfolio_items",
        ["portfolio_id", "initiative_id"],
    )


def downgrade() -> None:
    # Drop new tables in reverse order
    op.drop_constraint(
        "uq_portfolio_items_portfolio_initiative", "portfolio_items", type_="unique"
    )
    op.drop_index("ix_portfolio_items_initiative_id", table_name="portfolio_items")
    op.drop_index("ix_portfolio_items_portfolio_id", table_name="portfolio_items")
    op.drop_table("portfolio_items")

    op.drop_index("ix_portfolios_optimization_run_id", table_name="portfolios")
    op.drop_index("ix_portfolios_scenario_id", table_name="portfolios")
    op.drop_table("portfolios")

    op.drop_index("ix_optimization_runs_scenario_id", table_name="optimization_runs")
    op.drop_index("ix_optimization_runs_status", table_name="optimization_runs")
    op.drop_index("ix_optimization_runs_run_id", table_name="optimization_runs")
    op.drop_table("optimization_runs")

    op.drop_index(
        "ix_optimization_constraint_sets_scenario_id",
        table_name="optimization_constraint_sets",
    )
    op.drop_table("optimization_constraint_sets")

    op.drop_index("ix_optimization_scenarios_period_key", table_name="optimization_scenarios")
    op.drop_table("optimization_scenarios")

    op.drop_index(
        "ix_organization_metric_configs_kpi_key",
        table_name="organization_metric_configs",
    )
    op.drop_table("organization_metric_configs")

    # Remove InitiativeMathModel additions
    with op.batch_alter_table("initiative_math_models") as batch:
        batch.drop_column("model_name")
        batch.drop_column("model_description_free_text")

    # Remove Initiative additions
    op.drop_index("ix_initiatives_candidate_period_key", table_name="initiatives")
    with op.batch_alter_table("initiatives") as batch:
        batch.drop_column("market")
        batch.drop_column("department")
        batch.drop_column("category")
        batch.drop_column("immediate_kpi_key")
        batch.drop_column("metric_chain_json")
        batch.drop_column("kpi_contribution_json")
        batch.drop_column("engineering_tokens")
        batch.drop_column("engineering_tokens_mvp")
        batch.drop_column("engineering_tokens_full")
        batch.drop_column("scope_mode")
        batch.drop_column("mandate_reason")
        batch.drop_column("program_key")
        batch.drop_column("bundle_key")
        batch.drop_column("prerequisite_keys")
        batch.drop_column("exclusion_keys")
        batch.drop_column("synergy_group_keys")
        batch.drop_column("time_sensitivity_score")
        batch.drop_column("earliest_start_date")
        batch.drop_column("latest_finish_date")
        batch.drop_column("is_optimization_candidate")
        batch.drop_column("candidate_period_key")

    # Re-add deprecated Initiative fields
    with op.batch_alter_table("initiatives") as batch:
        batch.add_column(sa.Column("current_pain", sa.Text(), nullable=True))
        batch.add_column(sa.Column("desired_outcome", sa.Text(), nullable=True))
        batch.add_column(sa.Column("target_metrics", sa.Text(), nullable=True))
        batch.add_column(sa.Column("strategic_theme", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("linked_objectives", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("expected_impact_description", sa.Text(), nullable=True))
        batch.add_column(sa.Column("impact_metric", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("impact_unit", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("impact_low", sa.Float(), nullable=True))
        batch.add_column(sa.Column("impact_expected", sa.Float(), nullable=True))
        batch.add_column(sa.Column("impact_high", sa.Float(), nullable=True))
        batch.add_column(sa.Column("total_cost_estimate", sa.Float(), nullable=True))
        batch.add_column(sa.Column("time_sensitivity", sa.String(length=50), nullable=True))
        batch.add_column(sa.Column("missing_fields", sa.Text(), nullable=True))
        batch.add_column(sa.Column("llm_notes", sa.Text(), nullable=True))
        batch.add_column(sa.Column("math_warnings", sa.Text(), nullable=True))