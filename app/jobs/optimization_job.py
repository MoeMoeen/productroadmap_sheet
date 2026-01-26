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

from app.services.optimization.optimization_problem_builder import build_optimization_problem
from app.services.optimization.optimization_run_persistence import (
    create_run_record,
    persist_inputs_snapshot,
    persist_result,
)
from app.services.optimization.feasibility_checker import FeasibilityChecker
from app.services.optimization.feasibility_persistence import persist_feasibility_report
from app.services.optimization import optimization_results_service
from app.sheets.optimization_center_writers import OptimizationCenterWriter
from app.sheets.client import SheetsClient, get_sheets_service
from app.config import settings

from app.services.solvers.ortools_cp_sat_adapter import (
    OrtoolsCpSatSolverAdapter,
    CpSatConfig,
)

logger = logging.getLogger(__name__)

ScopeType = Literal["selected_only", "all_candidates"]


def run_flow5_optimization(
    *,
    db: Session,
    scenario_name: str,
    constraint_set_name: str,
    scope_type: ScopeType,
    selected_initiative_keys: Optional[list[str]] = None,
    run_id: Optional[str] = None,
    solver_config: Optional[CpSatConfig] = None,
    requested_by_email: Optional[str] = None,
    requested_by_ui: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Flow 5 (Phase 5) - Complete optimization run orchestration.

    Step 1+2+3+4+5+6+6.5+7+8:
    - Binary selection + capacity caps (global and by dimension)
    - Mandatory initiatives (x_i = 1 for each mandatory)
    - Exclusions (x_i = 0 for each excluded, x_a + x_b <= 1 for each excluded pair)
    - Prerequisites (x_dep <= x_req for each prerequisite edge)
    - Bundles (x_m1 = x_m2 = ... = x_mk for each bundle, all-or-nothing)
    - Capacity floors (sum(tokens_i * x_i) >= min_tokens for each dimension slice)
    - Target floors (sum(contrib_i * x_i) >= floor for each floor target)
    - Objective function:
      * Step 8.1: north_star mode (maximize single north_star KPI contribution)
      * Step 8.2: weighted_kpis mode (maximize weighted sum of normalized KPI contributions)
        - Normalization: prefers targets["all"]["all"][kpi]["value"], else max aggregation across dimensions
      * Fallback: maximize capacity usage (temporary for unsupported modes)

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
        requested_by_email: Email of user who triggered run (for audit trail)
        requested_by_ui: UI context that triggered run (e.g., "ProductOps_Control_Tab")
        
    Returns:
        Dict with run results (run_id, status, selected_count, candidate_count, etc.)
        
    Raises:
        ValueError: If run_id is missing or configuration is invalid
    """

    if not run_id:
        raise ValueError("run_id is required")

    logger.info(
        "Starting Flow 5 optimization (Steps 1-8: all constraints + objective)",
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
        requested_by_email=requested_by_email,
        requested_by_ui=requested_by_ui,
    )

    # 3) Persist inputs snapshot (also stamps started_at if missing)
    opt_run = persist_inputs_snapshot(
        db=db,
        optimization_run=opt_run,
        problem=problem,
        extra_snapshot_metadata={
            "flow": "flow5.optimization",
            "step": "steps_1_to_8_all_constraints_and_objective",
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
        
        # Publish infeasible run to sheets (if configured)
        _publish_results_to_sheets(
            db=db,
            opt_run=opt_run,
            problem=problem,
            solution=None,  # No solution for infeasible case
            feasibility=feasibility,  # Include feasibility context
        )
        
        return {
            "run_id": opt_run.run_id,
            "scenario_name": scenario_name,
            "constraint_set_name": constraint_set_name,
            "scope_type": scope_type,
            "solver_step": "steps_1_to_8_all_constraints_and_objective",
            "status": opt_run.status,
            "candidate_count": len(problem.candidates),
            "feasibility_summary": feasibility.summary,
            "errors_count": len(feasibility.errors),
            "warnings_count": len(feasibility.warnings),
        }

    # 5) Solve (Steps 1-8: all constraints + objective function)
    logger.info("Problem is feasible, running solver", extra={"run_id": opt_run.run_id})
    adapter = OrtoolsCpSatSolverAdapter(config=solver_config)
    solution: OptimizationSolution = adapter.solve(problem)

    # 6) Persist solver result_json + terminal status + finished_at
    # Treat OPTIMAL/FEASIBLE as success; others as failed.
    solver_ok = solution.status in {"optimal", "feasible"}

    result_payload: Dict[str, Any] = {
        "solver_step": "steps_1_to_8_all_constraints_and_objective",
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
    
    # Publish results to Optimization Center sheet (if configured)
    _publish_results_to_sheets(
        db=db,
        opt_run=opt_run,
        problem=problem,
        solution=solution,
        feasibility=None,  # Not needed for feasible runs
    )

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
        "solver_step": "steps_1_to_8_all_constraints_and_objective",
        "status": opt_run.status,
        "candidate_count": len(problem.candidates),
        "selected_count": selected_count,
        "capacity_used_tokens": solution.capacity_used_tokens,
        "solver_status": solution.status,
        "feasibility_warnings_count": len(feasibility.warnings),
    }


def _publish_results_to_sheets(
    *,
    db: Session,
    opt_run,
    problem,
    solution: Optional[OptimizationSolution],
    feasibility: Optional[FeasibilityReport] = None,
) -> None:
    """
    Publish optimization results to Optimization Center sheet.
    
    Writes to three tabs:
    - Runs: Single row with run summary
    - Results: N rows (one per candidate)
    - Gaps_and_Alerts: M rows (one per target constraint)
    
    Args:
        db: Database session
        opt_run: OptimizationRun DB model
        problem: OptimizationProblem schema (frozen snapshot)
        solution: OptimizationSolution (None for infeasible runs)
        feasibility: FeasibilityReport (for infeasible runs to show why)
    """
    # Check if Optimization Center is configured
    if not settings.OPTIMIZATION_CENTER:
        logger.info("OPTIMIZATION_CENTER not configured - skipping results publishing")
        return
    
    config = settings.OPTIMIZATION_CENTER
    
    try:
        # Initialize sheets client and writer
        service = get_sheets_service()
        client = SheetsClient(service=service)
        writer = OptimizationCenterWriter(client=client)
        
        # For infeasible runs: create empty solution with failed status and feasibility diagnostics
        if solution is None:
            from app.schemas.optimization_solution import OptimizationSolution
            
            # Include feasibility summary and errors in diagnostics for visibility
            infeasible_diagnostics = {}
            if feasibility:
                infeasible_diagnostics["feasibility_summary"] = feasibility.summary
                infeasible_diagnostics["feasibility_errors_count"] = len(feasibility.errors)
                infeasible_diagnostics["feasibility_warnings_count"] = len(feasibility.warnings)
                # Truncate error list to first 5 for readability
                if feasibility.errors:
                    infeasible_diagnostics["feasibility_errors"] = [
                        {"code": err.code, "message": err.message}
                        for err in feasibility.errors[:5]
                    ]
            
            solution = OptimizationSolution(
                status="infeasible",
                selected=[],
                capacity_used_tokens=0.0,
                diagnostics=infeasible_diagnostics,
            )
        
        # Build row data using service
        runs_row = optimization_results_service.build_runs_row(
            run=opt_run,
            problem=problem,
            solution=solution,
        )
        
        results_rows = optimization_results_service.build_results_rows(
            run_id=opt_run.run_id,
            problem=problem,
            solution=solution,
        )
        
        gaps_rows = optimization_results_service.build_gaps_rows(
            run_id=opt_run.run_id,
            problem=problem,
            solution=solution,
        )
        
        # Publish to sheets
        logger.info(
            "Publishing results to Optimization Center sheet",
            extra={
                "run_id": opt_run.run_id,
                "spreadsheet_id": config.spreadsheet_id,
                "results_count": len(results_rows),
                "gaps_count": len(gaps_rows),
            },
        )
        
        writer.append_runs_row(
            spreadsheet_id=config.spreadsheet_id,
            tab_name=config.runs_tab,
            row=runs_row,
        )
        
        writer.append_results_rows(
            spreadsheet_id=config.spreadsheet_id,
            tab_name=config.results_tab,
            rows=results_rows,
        )
        
        writer.append_gaps_rows(
            spreadsheet_id=config.spreadsheet_id,
            tab_name=config.gaps_and_alerts_tab,
            rows=gaps_rows,
        )
        
        logger.info(
            "Successfully published results to Optimization Center",
            extra={
                "run_id": opt_run.run_id,
                "runs_published": 1,
                "results_published": len(results_rows),
                "gaps_published": len(gaps_rows),
            },
        )
        
    except Exception as e:
        logger.error(
            f"Failed to publish results to Optimization Center: {e}",
            exc_info=True,
            extra={"run_id": opt_run.run_id},
        )
        # Don't fail the optimization run if publishing fails
        # Results are already persisted to DB

