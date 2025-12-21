# productroadmap_sheet_project/app/db/models/action_run.py

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text

from app.db.base import Base


class ActionRun(Base):
    """Execution ledger entry for sheet-triggered or system actions."""

    __tablename__ = "action_runs"

    id = Column(Integer, primary_key=True, index=True)

    # Public identifier returned to Sheets/UI
    run_id = Column(String(100), unique=True, index=True, nullable=False)

    # Routing / state
    action = Column(String(100), index=True, nullable=False)
    status = Column(String(20), index=True, nullable=False, default="queued")

    # Request + outcome
    payload_json = Column(JSON, nullable=False)
    result_json = Column(JSON, nullable=True)
    error_text = Column(Text, nullable=True)

    # Metadata for filtering / debugging
    requested_by_email = Column(String(255), nullable=True)
    requested_by_ui = Column(String(50), nullable=True)

    spreadsheet_id = Column(String(255), nullable=True)
    tab_name = Column(String(255), nullable=True)

    scope_type = Column(String(50), nullable=True)
    scope_summary = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
