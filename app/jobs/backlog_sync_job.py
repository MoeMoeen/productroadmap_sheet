# productroadmap_sheet_project/app/jobs/backlog_sync_job.py

from __future__ import annotations

from typing import Optional, TypedDict

from sqlalchemy.orm import Session

from app.config import settings, BacklogSheetConfig
from app.sheets.client import SheetsClient, get_sheets_service
from app.sheets.backlog_writer import write_backlog_from_db


class BacklogSyncResult(TypedDict):
    """Result of backlog sync operation."""
    sheets_processed: int
    initiatives_written: int
    cells_updated: int
    archived_rows_excluded: int


def _resolve_backlog_target(
    spreadsheet_id: Optional[str], tab_name: Optional[str], product_org: Optional[str]
) -> BacklogSheetConfig:
    """Pick a backlog sheet config based on overrides or settings.

    Priority:
    1. Explicit spreadsheet_id/tab_name overrides => construct temp config.
    2. Match product_org in CENTRAL_BACKLOG_SHEETS.
    3. settings.CENTRAL_BACKLOG if present.
    4. First entry in CENTRAL_BACKLOG_SHEETS.
    """
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


def run_backlog_sync(
    db: Session,
    spreadsheet_id: str | None = None,
    tab_name: str | None = None,
    product_org: str | None = None,
    include_archived: bool = True,
) -> dict[str, int]:
    """Regenerate a backlog Google Sheet from DB Initiatives.

    Supports multi-org via Settings.CENTRAL_BACKLOG_SHEETS or a single Settings.CENTRAL_BACKLOG.
    
    Returns:
        Dict with counts: {initiatives_written, cells_updated}
    """
    target = _resolve_backlog_target(spreadsheet_id, tab_name, product_org)
    service_obj = get_sheets_service()
    client = SheetsClient(service_obj)
    return write_backlog_from_db(
        db=db,
        client=client,
        backlog_spreadsheet_id=target.spreadsheet_id,
        backlog_tab_name=target.tab_name,
        include_archived=include_archived,
    )


def run_all_backlog_sync(db: Session, include_archived: bool = True) -> BacklogSyncResult:
    """Regenerate all configured backlog sheets (multi-org scenario).
    
    Returns:
        BacklogSyncResult with total counts across all sheets.
    """
    service_obj = get_sheets_service()
    client = SheetsClient(service_obj)
    targets: list[BacklogSheetConfig] = []
    if settings.CENTRAL_BACKLOG:
        targets.append(settings.CENTRAL_BACKLOG)
    targets.extend(settings.CENTRAL_BACKLOG_SHEETS)
    if not targets:
        raise ValueError("No backlog sheets configured.")
    
    total_initiatives = 0
    total_cells = 0
    total_archived_excluded = 0
    sheets_processed = 0
    
    for cfg in targets:
        result = write_backlog_from_db(
            db=db,
            client=client,
            backlog_spreadsheet_id=cfg.spreadsheet_id,
            backlog_tab_name=cfg.tab_name,
            include_archived=include_archived,
        )
        sheets_processed += 1
        total_initiatives = result["initiatives_written"]  # Same initiatives go to each sheet
        total_cells += result["cells_updated"]
        total_archived_excluded += result["archived_rows_excluded"]
    
    return BacklogSyncResult(
        sheets_processed=sheets_processed,
        initiatives_written=total_initiatives,
        cells_updated=total_cells,
        archived_rows_excluded=total_archived_excluded,
    )
