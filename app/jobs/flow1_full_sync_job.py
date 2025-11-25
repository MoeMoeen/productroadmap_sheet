# productroadmap_sheet_project/app/jobs/flow1_full_sync_job.py

from __future__ import annotations

import logging
from typing import Optional

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


def run_flow1_full_sync(
    db: Session,
    *,
    allow_status_override_global: bool = False,
    backlog_commit_every: Optional[int] = None,
    product_org: Optional[str] = None,
) -> None:
    """Run the full Flow 1 cycle.

    Args:
        db: SQLAlchemy session
        allow_status_override_global: pass-through to intake sync
        backlog_commit_every: batch commit frequency for backlog update
        product_org: optional org filter for backlog target resolution
    """
    logger.info("flow1.start")

    # 1) Intake sync: department sheets -> DB (+ initiative key backfill)
    logger.info("flow1.intake_sync.start")
    run_sync_all_intake_sheets(db=db, allow_status_override_global=allow_status_override_global)
    logger.info("flow1.intake_sync.done")

    # 2) Backlog update: central edits -> DB (use configured backlog sheet(s))
    logger.info("flow1.backlog_update.start")
    # product_org can narrow to a specific configured backlog; if None, default resolution applies
    try:
        run_backlog_update(db=db, product_org=product_org, commit_every=backlog_commit_every)
    except Exception:
        logger.exception("flow1.backlog_update.error")
        # Keep going to ensure DB -> sheet sync runs with whatever is in DB
    logger.info("flow1.backlog_update.done")

    # 3) Backlog sync: DB -> central backlog sheet(s)
    logger.info("flow1.backlog_sync.start")
    run_all_backlog_sync(db=db)
    logger.info("flow1.backlog_sync.done")

    logger.info("flow1.done")


__all__ = ["run_flow1_full_sync"]
