# productroadmap_sheet_project/app/db/schema_ensure.py

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy import text


def ensure_math_scoring_columns(engine: Engine) -> None:
    """Ensure math_* and active_scoring_framework columns exist on initiatives.

    Safe to call multiple times; uses IF NOT EXISTS where supported and guards otherwise.
    Works for PostgreSQL and SQLite.
    """
    try:
        dialect = engine.dialect.name
        if dialect == "postgresql":
            stmts = [
                "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS math_value_score DOUBLE PRECISION",
                "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS math_effort_score DOUBLE PRECISION",
                "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS math_overall_score DOUBLE PRECISION",
                "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS math_warnings TEXT",
                "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS active_scoring_framework VARCHAR(50)",
            ]
        else:
            # SQLite doesn't support IF NOT EXISTS for ADD COLUMN; guard via pragma
            existing = set()
            with engine.connect() as conn:
                res = conn.execute(text("PRAGMA table_info(initiatives)"))
                for row in res:
                    existing.add(row[1])  # column name
            stmts = []
            def add(col_def: str, name: str) -> None:
                if name not in existing:
                    stmts.append(f"ALTER TABLE initiatives ADD COLUMN {col_def}")
            add("math_value_score REAL", "math_value_score")
            add("math_effort_score REAL", "math_effort_score")
            add("math_overall_score REAL", "math_overall_score")
            add("math_warnings TEXT", "math_warnings")
            add("active_scoring_framework TEXT", "active_scoring_framework")

        if stmts:
            with engine.begin() as conn:
                for s in stmts:
                    conn.execute(text(s))
    except Exception:
        # Best-effort; do not crash pipeline if ensure fails
        pass


__all__ = ["ensure_math_scoring_columns"]