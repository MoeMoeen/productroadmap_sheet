"""Phase 4: Add math models and params tables; add math_* scores to initiatives

Revision ID: 20251214_phase4_math_models
Revises: 20251204_drop_deprecated
Create Date: 2025-12-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20251214_phase4_math_models"
down_revision = "20251204_drop_deprecated"
branch_labels = None
depends_on = None


def upgrade():
    # Create initiative_math_models
    op.create_table(
        "initiative_math_models",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("framework", sa.String(length=50), nullable=False, server_default=sa.text("'MATH_MODEL'"), index=True),
        sa.Column("formula_text", sa.Text(), nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=True),
        sa.Column("assumptions_text", sa.Text(), nullable=True),
        sa.Column("suggested_by_llm", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approved_by_user", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Create initiative_params
    op.create_table(
        "initiative_params",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("initiative_id", sa.Integer(), sa.ForeignKey("initiatives.id"), nullable=False, index=True),
        sa.Column("framework", sa.String(length=50), nullable=False, index=True),
        sa.Column("param_name", sa.String(length=100), nullable=False, index=True),
        sa.Column("param_display", sa.String(length=150), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("min", sa.Float(), nullable=True),
        sa.Column("max", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_auto_seeded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Add math_* score columns to initiatives
    op.add_column("initiatives", sa.Column("math_value_score", sa.Float(), nullable=True))
    op.add_column("initiatives", sa.Column("math_effort_score", sa.Float(), nullable=True))
    op.add_column("initiatives", sa.Column("math_overall_score", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("initiatives", "math_overall_score")
    op.drop_column("initiatives", "math_effort_score")
    op.drop_column("initiatives", "math_value_score")
    op.drop_table("initiative_params")
    op.drop_table("initiative_math_models")
