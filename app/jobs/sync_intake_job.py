# productroadmap_sheet_project/app/jobs/sync_intake_job.py

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Optional, Sequence, TypedDict

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.sheets.client import SheetsClient, get_sheets_service
from app.sheets.intake_reader import IntakeReader
from app.sheets.intake_writer import GoogleSheetsIntakeWriter
from app.services.intake_service import IntakeService
from app.config import settings
from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeMathModel, InitiativeParam, InitiativeScore
from app.db.models.roadmap_entry import RoadmapEntry
from app.db.models.optimization import PortfolioItem

logger = logging.getLogger(__name__)


class IntakeSyncResult(TypedDict):
    """Result of intake sync operation."""
    sheets_processed: int
    rows_processed: int
    initiatives_created: int
    initiatives_updated: int
    initiatives_archived: int
    initiatives_unarchived: int
    already_archived: int
    db_intake_managed_checked: int
    intake_keys_seen: int
    keys_backfilled: int


class IntakeReconcileResult(TypedDict):
    """Archive reconciliation stats for intake-managed initiatives."""
    intake_keys_seen: int
    db_intake_managed_checked: int
    archived_count: int
    unarchived_count: int
    already_archived_count: int


def reset_initiatives_for_intake_sync(db: Session) -> int:
    """Admin-only destructive reset helper; normal sync flows should not use this."""
    deleted = db.query(Initiative).count()

    db.query(RoadmapEntry).delete(synchronize_session=False)
    db.query(PortfolioItem).delete(synchronize_session=False)
    db.query(InitiativeScore).delete(synchronize_session=False)
    db.query(InitiativeParam).delete(synchronize_session=False)
    db.query(InitiativeMathModel).delete(synchronize_session=False)
    db.query(Initiative).delete(synchronize_session=False)
    db.commit()

    logger.info("intake.reset_db.done", extra={"deleted_count": deleted})
    return deleted


def reconcile_intake_managed_initiatives(
    db: Session,
    current_intake_keys: set[str],
    *,
    managed_scopes: Optional[Sequence[tuple[str, str]]] = None,
) -> IntakeReconcileResult:
    """Soft-archive intake-managed initiatives missing from the current intake snapshot."""
    scopes = list(managed_scopes) if managed_scopes is not None else [
        (tab.spreadsheet_id, tab.tab_name)
        for sheet_cfg in settings.INTAKE_SHEETS
        for tab in sheet_cfg.active_tabs()
    ]

    if not scopes:
        return IntakeReconcileResult(
            intake_keys_seen=len(current_intake_keys),
            db_intake_managed_checked=0,
            archived_count=0,
            unarchived_count=0,
            already_archived_count=0,
        )

    scope_filters = [
        and_(Initiative.source_sheet_id == spreadsheet_id, Initiative.source_tab_name == tab_name)
        for spreadsheet_id, tab_name in scopes
    ]
    managed_initiatives = db.query(Initiative).filter(or_(*scope_filters)).all()

    archived_count = 0
    unarchived_count = 0
    already_archived_count = 0
    now = datetime.now(timezone.utc)

    for initiative in managed_initiatives:
        key = str(initiative.initiative_key or "").strip()
        if not key:
            continue

        if key in current_intake_keys:
            if bool(getattr(initiative, "is_archived", False)):
                setattr(initiative, "is_archived", False)
                setattr(initiative, "archived_at", None)
                setattr(initiative, "archived_reason", None)
                unarchived_count += 1
            continue

        if bool(getattr(initiative, "is_archived", False)):
            already_archived_count += 1
            continue

        setattr(initiative, "is_archived", True)
        setattr(initiative, "archived_at", now)
        setattr(initiative, "archived_reason", "missing_from_intake_sync")
        archived_count += 1

    if archived_count or unarchived_count:
        db.commit()

    logger.info(
        "intake.archive_reconcile.done",
        extra={
            "intake_keys_seen": len(current_intake_keys),
            "db_intake_managed_checked": len(managed_initiatives),
            "archived_count": archived_count,
            "unarchived_count": unarchived_count,
            "already_archived_count": already_archived_count,
        },
    )

    return IntakeReconcileResult(
        intake_keys_seen=len(current_intake_keys),
        db_intake_managed_checked=len(managed_initiatives),
        archived_count=archived_count,
        unarchived_count=unarchived_count,
        already_archived_count=already_archived_count,
    )


def run_sync_for_sheet(
    db: Session,
    spreadsheet_id: str,
    tab_name: str,
    source_sheet_key: Optional[str] = None,
    sheets_service=None,
    allow_status_override: bool = False,
    commit_every: Optional[int] = None,
    header_row: int = 1,
    start_data_row: int = 2,
    max_rows: Optional[int] = None,
    seen_keys: Optional[set[str]] = None,
) -> dict[str, int]:
    """Run intake sync for one sheet tab end-to-end.

    - Reads evaluated values from Google Sheets
    - Maps to InitiativeCreate via IntakeService and upserts into DB
    - Writes initiative_key back to the intake sheet for new records
    - Optionally tracks seen initiative_keys in provided set for later deletion logic
    
    Returns:
        Dict with counts: {rows_processed, initiatives_created, initiatives_updated, keys_backfilled}
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
    rows_processed = 0
    initiatives_created = 0
    initiatives_updated = 0
    
    for row_number, row_dict in rows:
        try:
            initiative, was_created = intake_service.upsert_from_intake_row_with_status(
                row=row_dict,
                source_sheet_id=spreadsheet_id,
                source_sheet_key=source_sheet_key,
                source_tab_name=tab_name,
                source_row_number=row_number,
                allow_status_override=allow_status_override,
                auto_commit=False,
            )
            rows_processed += 1
            if was_created:
                initiatives_created += 1
            else:
                initiatives_updated += 1
            
            # Track seen keys for deletion logic
            initiative_key = getattr(initiative, "initiative_key", None)
            if seen_keys is not None and initiative_key:
                seen_keys.add(str(initiative_key))
                
        except Exception as e:
            logger.warning(
                "intake.row_sync_failed",
                extra={"sheet_id": spreadsheet_id, "tab": tab_name, "row": row_number, "error": str(e)[:100]},
            )
            continue
            
        if batch_size and (rows_processed % batch_size == 0):
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "intake.batch_commit_failed",
                    extra={"sheet_id": spreadsheet_id, "tab": tab_name, "rows_processed": rows_processed},
                )
                raise

            try:
                intake_service.flush_pending_key_backfills()
            except Exception:
                logger.exception(
                    "intake.batch_backfill_failed",
                    extra={"sheet_id": spreadsheet_id, "tab": tab_name, "rows_processed": rows_processed},
                )
                raise
                
    # Final commit and backfill for remainder
    keys_backfilled = 0
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "intake.final_commit_failed",
            extra={"sheet_id": spreadsheet_id, "tab": tab_name, "rows_processed": rows_processed},
        )
        raise

    try:
        keys_backfilled = intake_service.flush_pending_key_backfills()
    except Exception:
        logger.exception(
            "intake.final_backfill_failed",
            extra={"sheet_id": spreadsheet_id, "tab": tab_name, "rows_processed": rows_processed},
        )
        raise
    
    return {
        "rows_processed": rows_processed,
        "initiatives_created": initiatives_created,
        "initiatives_updated": initiatives_updated,
        "keys_backfilled": keys_backfilled,
    }


def run_sync_all_intake_sheets(
    db: Session,
    allow_status_override_global: bool = False,
    archive_missing: bool = True,
) -> IntakeSyncResult:
    """Run intake sync for all configured hierarchical sheets / tabs.

    Uses the new settings.INTAKE_SHEETS list of SheetConfig objects.
    Each TabConfig may specify its own allow_status_override flag.
    
    Args:
        db: Database session
        allow_status_override_global: Allow overwriting status fields
        archive_missing: If True, soft-archive intake-managed initiatives missing from current intake sheets
        
    Returns:
        IntakeSyncResult with detailed counts
    """
    service_obj = get_sheets_service()
    
    # Track all initiative_keys seen across all intake sheets
    seen_keys: set[str] = set()
    
    sheets_processed = 0
    total_rows = 0
    total_created = 0
    total_updated = 0
    total_backfilled = 0
    managed_scopes: list[tuple[str, str]] = []
    
    for sheet_cfg in settings.INTAKE_SHEETS:
        for tab in sheet_cfg.active_tabs():
            result = run_sync_for_sheet(
                db=db,
                spreadsheet_id=tab.spreadsheet_id,
                source_sheet_key=sheet_cfg.sheet_key,
                tab_name=tab.tab_name,
                sheets_service=service_obj,
                allow_status_override=tab.allow_status_override or allow_status_override_global,
                header_row=tab.header_row,
                start_data_row=tab.start_data_row,
                max_rows=tab.max_rows,
                seen_keys=seen_keys,
            )
            managed_scopes.append((tab.spreadsheet_id, tab.tab_name))
            sheets_processed += 1
            total_rows += result["rows_processed"]
            total_created += result["initiatives_created"]
            total_updated += result["initiatives_updated"]
            total_backfilled += result["keys_backfilled"]
            
            logger.info(
                "intake.sheet_synced",
                extra={
                    "sheet_key": sheet_cfg.sheet_key,
                    "tab": tab.tab_name,
                    "rows": result["rows_processed"],
                    "created_count": result["initiatives_created"],
                    "updated_count": result["initiatives_updated"],
                },
            )
    
    reconcile_result = IntakeReconcileResult(
        intake_keys_seen=len(seen_keys),
        db_intake_managed_checked=0,
        archived_count=0,
        unarchived_count=0,
        already_archived_count=0,
    )
    if archive_missing:
        reconcile_result = reconcile_intake_managed_initiatives(
            db,
            seen_keys,
            managed_scopes=managed_scopes,
        )
    
    return IntakeSyncResult(
        sheets_processed=sheets_processed,
        rows_processed=total_rows,
        initiatives_created=total_created,
        initiatives_updated=total_updated,
        initiatives_archived=reconcile_result["archived_count"],
        initiatives_unarchived=reconcile_result["unarchived_count"],
        already_archived=reconcile_result["already_archived_count"],
        db_intake_managed_checked=reconcile_result["db_intake_managed_checked"],
        intake_keys_seen=reconcile_result["intake_keys_seen"],
        keys_backfilled=total_backfilled,
    )