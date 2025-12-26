# productroadmap_sheet_project/app/jobs/backlog_update_job.py

from __future__ import annotations

from typing import Optional, cast

from sqlalchemy.orm import Session

from app.config import settings, BacklogSheetConfig
from app.sheets.client import SheetsClient, get_sheets_service
from app.sheets.backlog_reader import BacklogReader, BacklogRow
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
    initiative_keys: list[str] | None = None,
) -> int:
    """Read central backlog and apply updates into DB.
    
    Args:
        initiative_keys: Optional list of initiative_keys to filter rows. If provided, only rows
                        with matching initiative_keys are updated. If None, all rows are updated.

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
    
    # Filter to selected initiative_keys if provided
    if initiative_keys is not None:
        allowed = set(initiative_keys)
        filtered = []
        for item in rows:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], dict):
                row_dict = cast(BacklogRow, item[1])
                key = service._extract_initiative_key(row_dict)
                if key in allowed:
                    filtered.append(item)
            else:
                row_dict = cast(BacklogRow, item)  # type: ignore[assignment]
                key = service._extract_initiative_key(row_dict)
                if key in allowed:
                    filtered.append(item)
        rows = filtered
    
    return service.update_many(rows, commit_every=commit_every)
