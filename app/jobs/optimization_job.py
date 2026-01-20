# productroadmap_sheet_project/app/jobs/optimization_job.py
"""
Flow 5 (Phase 5) - Optimization run orchestration.

This job orchestrates the complete optimization pipeline:
1. Build OptimizationProblem
2. Create OptimizationRun record
3. Persist inputs snapshot
4. Run FeasibilityChecker
5. Persist feasibility report
6. If feasible -> run solver (currently Step 1: capacity caps only)
7. Persist solver result

No sheets writing yet. Just DB artifacts.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from typing_extensions import Literal

from app.schemas.feasibility import FeasibilityReport
from app.schemas.optimization_solution import OptimizationSolution

from app.services.optimization_problem_builder import build_optimization_problem
from app.services.optimization_run_persistence import (
    create_run_record,
    persist_inputs_snapshot,
    persist_result,
)
from app.services.feasibility_checker import FeasibilityChecker
from app.services.feasibility_persistence import persist_feasibility_report

from app.services.solvers.ortools_cp_sat_adapter import (
    OrtoolsCpSatSolverAdapter,
    CpSatConfig,
)

logger = logging.getLogger(__name__)

ScopeType = Literal["selected_only", "all_candidates"]


def run_flow5_optimization_step1(
    *,
    db: Session,
    scenario_name: str,
    constraint_set_name: str,
    scope_type: ScopeType,
    selected_initiative_keys: Optional[list[str]] = None,
    run_id: Optional[str] = None,
    solver_config: Optional[CpSatConfig] = None,
) -> Dict[str, Any]:
    """
    Flow 5 (Phase 5) - Optimization run orchestration.

    Step 1 ONLY:
    - Binary selection + capacity caps (global and by dimension)
    - No objective yet (feasibility-only solve)

    Writes durable artifacts:
    - OptimizationRun.inputs_snapshot_json
    - OptimizationRun.result_json (feasibility report and/or solver output)
    
    Args:
        db: Database session
        scenario_name: Name of optimization scenario
        constraint_set_name: Name of constraint set
        scope_type: "selected_only" or "all_candidates"
        selected_initiative_keys: Required if scope_type="selected_only"
        run_id: Unique run identifier (required)
        solver_config: Optional CP-SAT configuration
        
    Returns:
        Dict with run results (run_id, status, selected_count, etc.)
        
    Raises:
        ValueError: If run_id is missing or configuration is invalid
    """

    if not run_id:
        raise ValueError("run_id is required")

    logger.info(
        "Starting Flow 5 optimization (Step 1)",
        extra={
            "run_id": run_id,
            "scenario": scenario_name,
            "constraint_set": constraint_set_name,
            "scope_type": scope_type,
        },
    )

    # 1) Build OptimizationProblem (includes deadline pre-filter; includes scenario_id/constraint_set_id in metadata)
    problem = build_optimization_problem(
        db=db,
        scenario_name=scenario_name,
        constraint_set_name=constraint_set_name,
        scope_type=scope_type,
        selected_initiative_keys=selected_initiative_keys,
    )

    # 2) Create OptimizationRun record (domain artifact)
    # Create as 'pending' per model default conventions; started_at will be set when we persist snapshot.
    scenario_id_val = problem.metadata.get("scenario_id")
    constraint_set_id_val = problem.metadata.get("constraint_set_id")
    
    if scenario_id_val is None:
        raise ValueError(f"scenario_id not found in problem.metadata for {scenario_name}")
    if constraint_set_id_val is None:
        raise ValueError(f"constraint_set_id not found in problem.metadata for {constraint_set_name}")
    
    scenario_id = int(scenario_id_val)
    constraint_set_id = int(constraint_set_id_val)

    opt_run = create_run_record(
        db=db,
        run_id=run_id,
        scenario_id=scenario_id,
        constraint_set_id=constraint_set_id,
        solver_name="OR-Tools CP-SAT",
        solver_version=None,
        status="pending",
    )

    # 3) Persist inputs snapshot (also stamps started_at if missing)
    opt_run = persist_inputs_snapshot(
        db=db,
        optimization_run=opt_run,
        problem=problem,
        extra_snapshot_metadata={
            "flow": "flow5.optimization",
            "step": "step1_capacity_only",
        },
    )

    # Mark run as running once snapshot is persisted (explicit is clearer than implicit)
    # Note: Use getattr to avoid SQLAlchemy Column comparison type issues
    db.refresh(opt_run)
    current_status = getattr(opt_run, "status", None)
    if current_status != "running":
        opt_run.status = "running"  # type: ignore[assignment]
        db.add(opt_run)
        db.commit()
        db.refresh(opt_run)

    # 4) Feasibility check (pure, deterministic)
    checker = FeasibilityChecker()
    feasibility: FeasibilityReport = checker.check(problem)

    # Persist feasibility report to result_json under stable key.
    # If infeasible: set OptimizationRun.status="infeasible" and stamp finished_at (solver will not run).
    opt_run = persist_feasibility_report(
        db,
        opt_run,
        feasibility,
        status_on_infeasible="infeasible",
        status_on_feasible=None,  # keep 'running' until solver result is persisted
    )

    if not feasibility.is_feasible:
        logger.warning(
            "Optimization problem is infeasible - solver will not run",
            extra={
                "run_id": opt_run.run_id,
                "scenario": scenario_name,
                "constraint_set": constraint_set_name,
                "errors_count": len(feasibility.errors),
            },
        )
        return {
            "run_id": opt_run.run_id,
            "scenario_name": scenario_name,
            "constraint_set_name": constraint_set_name,
            "scope_type": scope_type,
            "solver_step": "step1_capacity_only",
            "status": opt_run.status,
            "feasibility_summary": feasibility.summary,
            "errors_count": len(feasibility.errors),
            "warnings_count": len(feasibility.warnings),
        }

    # 5) Solve (Step 1 only: capacity caps)
    logger.info("Problem is feasible, running solver", extra={"run_id": opt_run.run_id})
    adapter = OrtoolsCpSatSolverAdapter(config=solver_config)
    solution: OptimizationSolution = adapter.solve_step1_capacity_only(problem)

    # 6) Persist solver result_json + terminal status + finished_at
    # Treat OPTIMAL/FEASIBLE as success; others as failed.
    solver_ok = solution.status in {"optimal", "feasible"}

    result_payload: Dict[str, Any] = {
        "solver_step": "step1_capacity_only",
        "solution": solution.model_dump(),
    }

    opt_run = persist_result(
        db=db,
        optimization_run=opt_run,
        result_json=result_payload,
        status=("success" if solver_ok else "failed"),
        error_text=(None if solver_ok else f"solver_status={solution.status}"),
    )

    selected_count = sum(1 for item in solution.selected if item.selected)

    logger.info(
        "Flow 5 optimization completed",
        extra={
            "run_id": opt_run.run_id,
            "status": opt_run.status,
            "solver_status": solution.status,
            "selected_count": selected_count,
            "capacity_used": solution.capacity_used_tokens,
        },
    )

    return {
        "run_id": opt_run.run_id,
        "scenario_name": scenario_name,
        "constraint_set_name": constraint_set_name,
        "scope_type": scope_type,
        "solver_step": "step1_capacity_only",
        "status": opt_run.status,
        "selected_count": selected_count,
        "capacity_used_tokens": solution.capacity_used_tokens,
        "solver_status": solution.status,
        "feasibility_warnings_count": len(feasibility.warnings),
    }
