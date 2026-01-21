# app/services/feasibility_persistence.py
"""
Feasibility report persistence utilities.

Provides a stable contract for attaching feasibility validation results
to OptimizationRun.result_json.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.db.models.optimization import OptimizationRun
    from app.schemas.feasibility import FeasibilityReport

logger = logging.getLogger(__name__)

# Stable key for feasibility results in result_json
FEASIBILITY_RESULT_KEY = "feasibility_report"


def persist_feasibility_report(
    db: "Session",
    optimization_run: "OptimizationRun",
    report: "FeasibilityReport",
    *,
    status_on_infeasible: str = "failed",
    status_on_feasible: str | None = None,
) -> "OptimizationRun":
    """
    Persist feasibility output to OptimizationRun.result_json under a stable key.

    - Writes result_json[FEASIBILITY_RESULT_KEY] = report.model_dump()
    - Optionally updates OptimizationRun.status
    - Stamps finished_at when infeasible (since solver will not run)
    
    Args:
        db: Database session
        optimization_run: OptimizationRun to update
        report: FeasibilityReport from pre-solver validation
        status_on_infeasible: Status to set if report.is_feasible == False (default: "failed")
        status_on_feasible: Optional status to set if report.is_feasible == True
        
    Returns:
        Updated OptimizationRun (refreshed from DB)
        
    Usage:
        problem = build_optimization_problem(...)
        checker = FeasibilityChecker()
        report = checker.check(problem)
        
        persist_feasibility_report(db, run, report)
        
        if not report.is_feasible:
            # Stop here. Do NOT call solver.
            return
    """
    # PRODUCTION FIX: Merge into existing result_json without mutating
    payload: dict[str, Any] = dict(optimization_run.result_json or {})  # type: ignore[arg-type]
    payload[FEASIBILITY_RESULT_KEY] = report.model_dump()

    optimization_run.result_json = payload  # type: ignore[assignment]

    # PRODUCTION FIX: Update status and stamp finished_at if infeasible
    if not report.is_feasible:
        optimization_run.status = status_on_infeasible  # type: ignore[assignment]
        optimization_run.finished_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        logger.warning(
            "Optimization problem is infeasible - solver will not run",
            extra={
                "run_id": optimization_run.run_id,
                "errors_count": len(report.errors),
                "warnings_count": len(report.warnings),
            },
        )
    elif status_on_feasible:
        optimization_run.status = status_on_feasible  # type: ignore[assignment]
        logger.info(
            "Optimization problem is feasible",
            extra={
                "run_id": optimization_run.run_id,
                "warnings_count": len(report.warnings),
            },
        )

    db.add(optimization_run)
    db.commit()
    db.refresh(optimization_run)

    return optimization_run
