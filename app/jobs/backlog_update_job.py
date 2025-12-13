# productroadmap_sheet_project/app/jobs/backlog_update_job.py

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings, BacklogSheetConfig
from app.sheets.client import SheetsClient, get_sheets_service
from app.sheets.backlog_reader import BacklogReader
from app.services.backlog_service import BacklogService


def _resolve_backlog_target(
    spreadsheet_id: Optional[str], tab_name: Optional[str], product_org: Optional[str]
) -> BacklogSheetConfig:
    """Pick a backlog sheet config based on overrides or settings."""
    if spreadsheet_id:
        return BacklogSheetConfig(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name or "Backlog",
            product_org=product_org,
        )
    if product_org:
        for cfg in settings.CENTRAL_BACKLOG_SHEETS:
            if (cfg.product_org or "").lower() == product_org.lower():
                return cfg
    if settings.CENTRAL_BACKLOG:
        return settings.CENTRAL_BACKLOG
    if settings.CENTRAL_BACKLOG_SHEETS:
        return settings.CENTRAL_BACKLOG_SHEETS[0]
    raise ValueError("No backlog sheet configuration found.")


def run_backlog_update(
    db: Session,
    spreadsheet_id: str | None = None,
    tab_name: str | None = None,
    product_org: str | None = None,
    commit_every: int | None = None,
) -> int:
    """Read central backlog and apply updates into DB.

    Returns number of initiatives updated.
    """
    target = _resolve_backlog_target(spreadsheet_id, tab_name, product_org)
    service_obj = get_sheets_service()
    client = SheetsClient(service_obj)
    reader = BacklogReader(client)
    service = BacklogService(db)

    rows = reader.get_rows(
        spreadsheet_id=target.spreadsheet_id,
        tab_name=target.tab_name,
    )
    return service.update_many(rows, commit_every=commit_every)
