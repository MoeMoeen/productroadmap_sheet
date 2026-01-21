# app/services/optimization_run_persistence.py
"""
Persistence utilities for OptimizationRun objects.
Handles storing solver inputs/outputs for reproducibility and audit trail.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.optimization import OptimizationRun
from app.schemas.optimization_problem import OptimizationProblem

logger = logging.getLogger(__name__)


def persist_inputs_snapshot(
    db: Session,
    optimization_run: OptimizationRun,
    problem: OptimizationProblem,
    extra_snapshot_metadata: Optional[Dict[str, Any]] = None,
) -> OptimizationRun:
    """
    Store the exact solver input into OptimizationRun.inputs_snapshot_json for reproducibility.
    
    This enables:
    - Full audit trail of what was sent to solver
    - Rerun capability with identical inputs
    - Debugging solver issues
    - Comparing runs across time
    
    Args:
        db: Database session
        optimization_run: OptimizationRun to update (must already exist in DB)
        problem: The OptimizationProblem to snapshot
        extra_snapshot_metadata: Optional additional metadata to merge into problem.metadata
        
    Returns:
        Updated OptimizationRun (refreshed from DB)
        
    Note:
        This does NOT create the run; it only updates the snapshot + timestamps.
        The run must be created separately before calling this function.
    """
    # PRODUCTION FIX: Serialize problem to dict for JSON storage
    snapshot = problem.model_dump()

    # PRODUCTION FIX: Merge extra metadata without mutating original problem
    if extra_snapshot_metadata:
        snapshot_meta = dict(snapshot.get("metadata") or {})
        snapshot_meta.update(extra_snapshot_metadata)
        snapshot["metadata"] = snapshot_meta

    # Store snapshot (SQLAlchemy handles JSON serialization)
    optimization_run.inputs_snapshot_json = snapshot  # type: ignore[assignment]

    # PRODUCTION FIX: Set started_at timestamp if not already set
    if optimization_run.started_at is None:
        optimization_run.started_at = datetime.now(timezone.utc)  # type: ignore[assignment]

    db.add(optimization_run)
    db.commit()
    db.refresh(optimization_run)

    logger.info(
        "Persisted optimization problem snapshot",
        extra={
            "run_id": optimization_run.run_id,
            "scenario_name": problem.scenario_name,
            "constraint_set_name": problem.constraint_set_name,
            "candidate_count": len(problem.candidates),
        },
    )

    return optimization_run


def persist_result(
    db: Session,
    optimization_run: OptimizationRun,
    result_json: Dict[str, Any],
    status: str = "success",
    error_text: Optional[str] = None,
) -> OptimizationRun:
    """
    Store solver result into OptimizationRun.result_json.
    
    Args:
        db: Database session
        optimization_run: OptimizationRun to update
        result_json: Structured solver output (selected initiatives, allocations, KPI achievements, gaps)
        status: Run status ("success", "failed", "timeout", etc.)
        error_text: Optional error message if status != "success"
        
    Returns:
        Updated OptimizationRun (refreshed from DB after finished_at is set)
    """
    # PRODUCTION FIX: Store result and update status atomically
    optimization_run.result_json = result_json  # type: ignore[assignment]
    optimization_run.status = status  # type: ignore[assignment]
    
    if error_text:
        optimization_run.error_text = error_text  # type: ignore[assignment]

    # PRODUCTION FIX: Set finished_at timestamp
    if optimization_run.finished_at is None:
        optimization_run.finished_at = datetime.now(timezone.utc)  # type: ignore[assignment]

    db.add(optimization_run)
    db.commit()
    db.refresh(optimization_run)

    logger.info(
        "Persisted optimization result",
        extra={
            "run_id": optimization_run.run_id,
            "status": status,
            "has_error": bool(error_text),
        },
    )

    return optimization_run


def create_run_record(
    db: Session,
    run_id: str,
    scenario_id: int,
    constraint_set_id: int,
    solver_name: Optional[str] = None,
    solver_version: Optional[str] = None,
    status: str = "queued",
    requested_by_email: Optional[str] = None,
    requested_by_ui: Optional[str] = None,
) -> OptimizationRun:
    """
    Create a new OptimizationRun record in the database.
    
    Args:
        db: Database session
        run_id: Unique run identifier (typically UUID or similar)
        scenario_id: FK to OptimizationScenario
        constraint_set_id: FK to OptimizationConstraintSet
        solver_name: Name of solver engine (e.g., "OR-Tools", "CPLEX")
        solver_version: Solver version string
        status: Initial status (default "queued")
        requested_by_email: Email of user who triggered run (for audit trail)
        requested_by_ui: UI context that triggered run (e.g., "ProductOps_Control_Tab")
        
    Returns:
        Newly created OptimizationRun
    """
    # PRODUCTION FIX: Create run with all required fields + audit trail
    run = OptimizationRun(
        run_id=run_id,
        scenario_id=scenario_id,
        constraint_set_id=constraint_set_id,
        status=status,
        solver_name=solver_name,
        solver_version=solver_version,
        requested_by_email=requested_by_email,
        requested_by_ui=requested_by_ui,
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    logger.info(
        "Created optimization run record",
        extra={
            "run_id": run_id,
            "scenario_id": scenario_id,
            "constraint_set_id": constraint_set_id,
            "status": status,
        },
    )

    return run
