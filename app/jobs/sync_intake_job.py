from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.sheets.client import SheetsClient, get_sheets_service
from app.sheets.intake_reader import IntakeReader
from app.sheets.intake_writer import GoogleSheetsIntakeWriter
from app.services.intake_service import IntakeService
from app.config import settings


def run_sync_for_sheet(
    db: Session,
    spreadsheet_id: str,
    tab_name: str,
    sheets_service=None,
    allow_status_override: bool = False,
    commit_every: Optional[int] = None,
    header_row: int = 1,
    start_data_row: int = 2,
    max_rows: Optional[int] = None,
) -> None:
    """Run intake sync for one sheet tab end-to-end.

    - Reads evaluated values from Google Sheets
    - Maps to InitiativeCreate via IntakeService and upserts into DB
    - Writes initiative_key back to the intake sheet for new records
    """
    service_obj = sheets_service or get_sheets_service()
    sheets_client = SheetsClient(service_obj)

    reader = IntakeReader(sheets_client)
    key_writer = GoogleSheetsIntakeWriter(sheets_client)
    intake_service = IntakeService(db, key_writer=key_writer)

    rows = reader.get_rows_for_sheet(
        spreadsheet_id,
        tab_name,
        header_row=header_row,
        start_data_row=start_data_row,
        max_rows=max_rows,
    )
    # Batched upserts with periodic commits to improve performance and allow atomic chunks
    batch_size = commit_every or getattr(settings, "INTAKE_BATCH_COMMIT_EVERY", 100)
    count = 0
    for row_number, row_dict in rows:
        intake_service.upsert_from_intake_row(
            row=row_dict,
            source_sheet_id=spreadsheet_id,
            source_tab_name=tab_name,
            source_row_number=row_number,
            allow_status_override=allow_status_override,
            auto_commit=False,
        )
        count += 1 #what's the purpose of this line? It keeps track of how many rows have been processed to determine when to commit the batch. If count reaches batch_size, a commit is performed.
        if batch_size and (count % batch_size == 0):
            try:
                db.commit()
                # After commit, backfill any pending keys
                intake_service.flush_pending_key_backfills()
            except Exception:
                db.rollback()
                # Continue processing remaining rows; errors logged by service
                pass
    # Final commit and backfill for remainder
    try:
        db.commit()
        intake_service.flush_pending_key_backfills()
    except Exception:
        db.rollback()
        pass



def run_sync_all_intake_sheets(
    db: Session,
    allow_status_override_global: bool = False,
) -> None:
    """Run intake sync for all configured hierarchical sheets / tabs.

    Uses the new settings.INTAKE_SHEETS list of SheetConfig objects.
    Each TabConfig may specify its own allow_status_override flag.
    """
    service_obj = get_sheets_service()
    for sheet_cfg in settings.INTAKE_SHEETS:
        for tab in sheet_cfg.active_tabs():
            run_sync_for_sheet(
                db=db,
                spreadsheet_id=tab.spreadsheet_id,
                tab_name=tab.tab_name,
                sheets_service=service_obj,
                allow_status_override=tab.allow_status_override or allow_status_override_global,
                header_row=tab.header_row,
                start_data_row=tab.start_data_row,
                max_rows=tab.max_rows,
            )