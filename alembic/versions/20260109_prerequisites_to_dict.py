"""Convert prerequisites from list-of-lists to dict structure

Revision ID: 20260109_prereq_dict
Revises: 20260108_split_exclusions
Create Date: 2026-01-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "r20260109_prereq_dict"
down_revision = "r20260108_split_excl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Convert prerequisites_json from list-of-lists format:
    [[dependent, prereq1, prereq2], ...]
    
    to dict format:
    {dependent: [prereq1, prereq2], ...}
    """
    conn = op.get_bind()
    
    # Fetch all constraint sets with prerequisites_json
    result = conn.execute(
        text("SELECT id, prerequisites_json FROM optimization_constraint_sets WHERE prerequisites_json IS NOT NULL")
    )
    
    for row in result:
        constraint_set_id, prereqs_json = row
        
        if not prereqs_json:
            continue
        
        # Convert list-of-lists to dict
        if isinstance(prereqs_json, list):
            prereqs_dict = {}
            for item in prereqs_json:
                if isinstance(item, list) and len(item) >= 2:
                    dependent = item[0]
                    prerequisites = item[1:]
                    prereqs_dict[dependent] = prerequisites
            
            # Update the row with the new dict structure
            conn.execute(
                text("UPDATE optimization_constraint_sets SET prerequisites_json = :prereqs WHERE id = :id"),
                {"prereqs": sa.JSON().bind_processor(conn.dialect)(prereqs_dict), "id": constraint_set_id}
            )
    
    conn.commit()


def downgrade() -> None:
    """
    Convert prerequisites_json from dict format:
    {dependent: [prereq1, prereq2], ...}
    
    back to list-of-lists format:
    [[dependent, prereq1, prereq2], ...]
    """
    conn = op.get_bind()
    
    # Fetch all constraint sets with prerequisites_json
    result = conn.execute(
        text("SELECT id, prerequisites_json FROM optimization_constraint_sets WHERE prerequisites_json IS NOT NULL")
    )
    
    for row in result:
        constraint_set_id, prereqs_json = row
        
        if not prereqs_json:
            continue
        
        # Convert dict to list-of-lists
        if isinstance(prereqs_json, dict):
            prereqs_list = []
            for dependent, prerequisites in prereqs_json.items():
                prereqs_list.append([dependent] + prerequisites)
            
            # Update the row with the old list-of-lists structure
            conn.execute(
                text("UPDATE optimization_constraint_sets SET prerequisites_json = :prereqs WHERE id = :id"),
                {"prereqs": sa.JSON().bind_processor(conn.dialect)(prereqs_list), "id": constraint_set_id}
            )
    
    conn.commit()
