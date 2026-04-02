# productroadmap_sheet_project/app/jobs/flow1_full_sync_job.py
"""
Flow 1 is the end-to-end sync cycle for departmental intake sheets feeding into a central backlog sheet.
It consists of three main steps:
1. Intake Sync: Sync data from departmental intake Google Sheets into the database, including backfilling initiative keys.
2. Backlog Update: Apply any central edits made in the backlog sheet back into the database.
3. Backlog Sync: Regenerate the central backlog Google Sheet from the updated database initiatives.
"""
from __future__ import annotations

import logging
from typing import Optional, TypedDict

from sqlalchemy.orm import Session

from app.jobs.sync_intake_job import run_sync_all_intake_sheets
from app.jobs.backlog_update_job import run_backlog_update
from app.jobs.backlog_sync_job import run_all_backlog_sync

# Flow 1 full sync orchestration.
#
# Cycle:
#   1) Intake sync (dept sheets → DB + keys backfill)
#   2) Backlog update (central edits → DB)
#   3) Backlog sync (DB → central backlog)
#

logger = logging.getLogger(__name__)


class Flow1SyncResult(TypedDict):
    """Result of Flow 1 full sync execution."""
    intake_sync_completed: bool
    backlog_update_completed: bool
    backlog_update_error: Optional[str]
    backlog_sync_completed: bool
    substeps: list[str]
    # Counts
    intake_sheets_processed: int
    intake_rows_processed: int
    intake_created: int
    intake_updated: int
    intake_archived: int
    intake_unarchived: int
    intake_already_archived: int
    intake_managed_checked: int
    intake_keys_seen: int
    backlog_initiatives_written: int
    backlog_cells_updated: int
    backlog_archived_excluded: int


def run_flow1_full_sync(
    db: Session,
    *,
    allow_status_override_global: bool = False,
    backlog_commit_every: Optional[int] = None,
    product_org: Optional[str] = None,
    archive_missing_initiatives: bool = True,
    include_archived_in_backlog: bool = False,
) -> Flow1SyncResult:
    """Run the full Flow 1 cycle.

    Args:
        db: SQLAlchemy session
        allow_status_override_global: pass-through to intake sync
        backlog_commit_every: batch commit frequency for backlog update
        product_org: optional org filter for backlog target resolution
        archive_missing_initiatives: if True, soft-archive intake-managed initiatives missing from intake
        include_archived_in_backlog: include archived initiatives in DB -> backlog sync
        
    Returns:
        Flow1SyncResult with completion status and counts for each substep
    """
    logger.info("flow1.start")
    
    result: Flow1SyncResult = {
        "intake_sync_completed": False,
        "backlog_update_completed": False,
        "backlog_update_error": None,
        "backlog_sync_completed": False,
        "substeps": [],
        "intake_sheets_processed": 0,
        "intake_rows_processed": 0,
        "intake_created": 0,
        "intake_updated": 0,
        "intake_archived": 0,
        "intake_unarchived": 0,
        "intake_already_archived": 0,
        "intake_managed_checked": 0,
        "intake_keys_seen": 0,
        "backlog_initiatives_written": 0,
        "backlog_cells_updated": 0,
        "backlog_archived_excluded": 0,
    }

    # 1) Intake sync: department sheets -> DB (+ initiative key backfill)
    logger.info("flow1.intake_sync.start")
    intake_result = run_sync_all_intake_sheets(
        db=db,
        allow_status_override_global=allow_status_override_global,
        archive_missing=archive_missing_initiatives,
    )
    result["intake_sync_completed"] = True
    result["intake_sheets_processed"] = intake_result["sheets_processed"]
    result["intake_rows_processed"] = intake_result["rows_processed"]
    result["intake_created"] = intake_result["initiatives_created"]
    result["intake_updated"] = intake_result["initiatives_updated"]
    result["intake_archived"] = intake_result["initiatives_archived"]
    result["intake_unarchived"] = intake_result["initiatives_unarchived"]
    result["intake_already_archived"] = intake_result["already_archived"]
    result["intake_managed_checked"] = intake_result["db_intake_managed_checked"]
    result["intake_keys_seen"] = intake_result["intake_keys_seen"]
    result["substeps"].append("flow0.intake_sync")
    logger.info(
        "flow1.intake_sync.done",
        extra={
            "sheets": intake_result["sheets_processed"],
            "rows": intake_result["rows_processed"],
            "created_count": intake_result["initiatives_created"],
            "updated_count": intake_result["initiatives_updated"],
            "archived_count": intake_result["initiatives_archived"],
            "unarchived_count": intake_result["initiatives_unarchived"],
            "already_archived_count": intake_result["already_archived"],
        },
    )

    # 2) Backlog update: central edits -> DB (use configured backlog sheet(s))
    logger.info("flow1.backlog_update.start")
    # product_org can narrow to a specific configured backlog; if None, default resolution applies
    try:
        run_backlog_update(db=db, product_org=product_org, commit_every=backlog_commit_every)
        result["backlog_update_completed"] = True
        result["substeps"].append("flow1.backlogsheet_read")
    except Exception as exc:
        logger.exception("flow1.backlog_update.error")
        result["backlog_update_error"] = str(exc)[:500]  # Truncate for safety
        # Keep going to ensure DB -> sheet sync runs with whatever is in DB
    logger.info("flow1.backlog_update.done")

    # 3) Backlog sync: DB -> central backlog sheet(s)
    logger.info("flow1.backlog_sync.start")
    backlog_result = run_all_backlog_sync(db=db, include_archived=include_archived_in_backlog)
    result["backlog_sync_completed"] = True
    result["backlog_initiatives_written"] = backlog_result["initiatives_written"]
    result["backlog_cells_updated"] = backlog_result["cells_updated"]
    result["backlog_archived_excluded"] = backlog_result["archived_rows_excluded"]
    result["substeps"].append("flow1.backlogsheet_write")
    logger.info(
        "flow1.backlog_sync.done",
        extra={
            "initiatives": backlog_result["initiatives_written"],
            "cells": backlog_result["cells_updated"],
            "archived_excluded_count": backlog_result["archived_rows_excluded"],
        },
    )

    logger.info("flow1.done")
    return result


__all__ = ["run_flow1_full_sync"]
