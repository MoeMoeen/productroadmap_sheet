# productroadmap_sheet_project/app/services/optimization/optimization_results_service.py
"""
Pure computation service for optimization results artifacts.

Transforms OptimizationRun + OptimizationProblem + OptimizationSolution
into row dicts ready for sheet publishing (Runs, Results, Gaps_and_Alerts tabs).

Key principles:
- Use frozen snapshots from OptimizationProblem.candidates (not live DB)
- Deterministic recomputation of objective contributions
- Stable per-run views (reproducible even if initiatives change later)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from app.schemas.optimization_problem import OptimizationProblem, Candidate
from app.schemas.optimization_solution import OptimizationSolution
from app.db.models.optimization import OptimizationRun

logger = logging.getLogger(__name__)

# Scaling factor used in solver (must match ortools_cp_sat_adapter.py)
KPI_SCALE = 1_000_000


def build_runs_row(
    *,
    run: OptimizationRun,
    problem: OptimizationProblem,
    solution: OptimizationSolution,
) -> Dict[str, Any]:
    """
    Build single row dict for Runs tab (one row per optimization run).
    
    Args:
        run: OptimizationRun DB model
        problem: OptimizationProblem schema (frozen snapshot)
        solution: OptimizationSolution from solver
        
    Returns:
        Dict with Runs tab columns
    """
    # Extract diagnostics from solution
    diagnostics = solution.diagnostics or {}
    
    # Compute selected count (only candidates with selected=True)
    selected_items = solution.selected or []
    selected_count = sum(1 for item in selected_items if item.selected)
    
    # Build set of selected initiative keys (only selected=True)
    selected_keys = {item.initiative_key for item in selected_items if item.selected}
    
    # Compute total capacity used (sum of engineering_tokens for selected)
    capacity_used = sum(
        float(c.engineering_tokens or 0)
        for c in problem.candidates
        if c.initiative_key in selected_keys
    )
    
    # Extract objective values from diagnostics
    # solver.ObjectiveValue() was persisted in diagnostics
    total_objective_raw = diagnostics.get("objective_value_raw", 0)
    total_objective = diagnostics.get("objective_value", 0.0)
    
    # Build gap summary string (first 3 gaps, truncated)
    gap_summary = _build_gap_summary(problem, solution)
    
    # Extract values from problem snapshot (stable/frozen)
    scenario_name = getattr(problem, "scenario_name", None) or "unknown"
    period_key = getattr(problem, "period_key", None) or "unknown"
    
    return {
        "run_id": run.run_id,
        "scenario_name": scenario_name,
        "period_key": period_key,
        "optimization_db_status": run.status or "unknown",
        "created_at": run.created_at.isoformat() if run.created_at is not None else None,
        "started_at": run.started_at.isoformat() if run.started_at is not None else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at is not None else None,
        "selected_count": selected_count,
        "capacity_used": capacity_used,
        "total_objective_raw": total_objective_raw,
        "total_objective": total_objective,
        "gap_summary": gap_summary,
        "results_tab_ref": "Results",  # Single tab with run_id filter
        "run_status": "OK" if solution.status in ("optimal", "feasible") else "FAILED",
        "updated_source": "optimization_engine",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_results_rows(
    *,
    run_id: str,
    problem: OptimizationProblem,
    solution: OptimizationSolution,
) -> List[Dict[str, Any]]:
    """
    Build N rows for Results tab (one per candidate in problem).
    
    Uses frozen snapshot from problem.candidates (not live DB).
    Recomputes objective_contribution deterministically.
    
    Args:
        run_id: Unique run identifier
        problem: OptimizationProblem schema (frozen snapshot)
        solution: OptimizationSolution from solver
        
    Returns:
        List of dicts (one per candidate)
    """
    selected_items = solution.selected or []
    selected_keys = {item.initiative_key for item in selected_items if item.selected}
    objective_spec = problem.objective
    obj_mode = str(objective_spec.mode).lower() if objective_spec.mode else "unknown"
    
    # Resolve north_star_kpi_key from problem.objective (primary) or diagnostics (fallback)
    diagnostics = solution.diagnostics or {}
    north_star_kpi_key = None
    if objective_spec and hasattr(objective_spec, "north_star_kpi_key"):
        north_star_kpi_key = objective_spec.north_star_kpi_key
    if not north_star_kpi_key:
        north_star_kpi_key = diagnostics.get("north_star_kpi_key")
    
    # For weighted_kpis, get weights and scale map from diagnostics
    weights = diagnostics.get("weights", {})
    kpi_scale_map = diagnostics.get("kpi_scale_map", {})
    
    rows = []
    for candidate in problem.candidates:
        is_selected = candidate.initiative_key in selected_keys
        allocated_tokens = float(candidate.engineering_tokens or 0) if is_selected else 0.0
        
        # Recompute objective_contribution using same logic as solver
        objective_contribution = _compute_objective_contribution(
            candidate=candidate,
            obj_mode=obj_mode,
            north_star_kpi_key=north_star_kpi_key,
            weights=weights,
            kpi_scale_map=kpi_scale_map,
        )
        
        # Extract north_star_gain (useful for cross-check in all modes)
        north_star_gain = None
        if north_star_kpi_key:
            contribs = candidate.kpi_contributions or {}
            north_star_gain = contribs.get(north_star_kpi_key, 0.0)
        
        # Extract dimension attributes from candidate snapshot
        row = {
            "run_id": run_id,
            "initiative_key": candidate.initiative_key,
            "selected": is_selected,
            "allocated_tokens": allocated_tokens,
            # Frozen dimensions from candidate snapshot
            "country": candidate.country or "",
            "department": candidate.department or "",
            "category": candidate.category or "",
            "program": candidate.program or "",
            "product": candidate.product or "",
            "segment": candidate.segment or "",
            # Objective attribution
            "objective_mode": obj_mode,
            "objective_contribution": objective_contribution,
            "north_star_gain": north_star_gain,
            # Display fields
            "active_overall_score": candidate.active_overall_score,
            "notes": "",  # PM-owned, preserve if editing supported
            "dependency_status": "",  # Future
            # System
            "run_status": "published",
            "updated_source": "optimization_engine",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(row)
    
    return rows


def build_gaps_rows(
    *,
    run_id: str,
    problem: OptimizationProblem,
    solution: OptimizationSolution,
) -> List[Dict[str, Any]]:
    """
    Build M rows for Gaps_and_Alerts tab (one per target constraint).
    
    Computes achieved vs target for each dimension/dimension_key/kpi_key slice.
    
    Args:
        run_id: Unique run identifier
        problem: OptimizationProblem schema
        solution: OptimizationSolution from solver
        
    Returns:
        List of dicts (one per target)
    """
    targets = problem.constraint_set.targets or {}
    selected_items = solution.selected or []
    selected_keys = {item.initiative_key for item in selected_items if item.selected}
    
    rows = []
    for dimension, dim_map in targets.items():
        if not isinstance(dim_map, dict):
            continue
        for dimension_key, kpi_map in dim_map.items():
            if not isinstance(kpi_map, dict):
                continue
            for kpi_key, target_spec in kpi_map.items():
                if not isinstance(target_spec, dict):
                    continue
                
                target_type = target_spec.get("type")
                if target_type != "floor":
                    continue  # Only process floor targets (constraints)
                
                target_value = target_spec.get("value", 0.0)
                try:
                    target_value = float(target_value)
                except Exception:
                    target_value = 0.0
                
                # Compute achieved: sum contributions over selected candidates in this slice
                achieved = _compute_achieved_contribution(
                    candidates=problem.candidates,
                    selected_keys=selected_keys,
                    dimension=dimension,
                    dimension_key=dimension_key,
                    kpi_key=kpi_key,
                )
                
                gap = target_value - achieved
                severity = _compute_severity(gap, target_value)
                
                row = {
                    "run_id": run_id,
                    "dimension": dimension,
                    "dimension_key": dimension_key,
                    "kpi_key": kpi_key,
                    "target": target_value,
                    "achieved": achieved,
                    "gap": gap,
                    "severity": severity,
                    "notes": "",  # PM-owned
                    "recommendation": "",  # Future
                    "run_status": "published",
                    "updated_source": "optimization_engine",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                rows.append(row)
    
    return rows


# ========== PRIVATE HELPERS ==========

def _compute_objective_contribution(
    *,
    candidate: Candidate,
    obj_mode: str,
    north_star_kpi_key: Optional[str],
    weights: Dict[str, float],
    kpi_scale_map: Dict[str, float],
) -> float:
    """
    Recompute objective contribution for a candidate (deterministic).
    
    Matches solver logic:
    - north_star: contrib_i[ns_key]
    - weighted_kpis: Σ_k w_k * contrib_i,k / scale_k
    """
    contribs = candidate.kpi_contributions or {}
    
    if obj_mode == "north_star":
        if not north_star_kpi_key:
            return 0.0
        return float(contribs.get(north_star_kpi_key, 0.0))
    
    elif obj_mode == "weighted_kpis":
        total = 0.0
        for kpi_key, weight in weights.items():
            contrib_val = contribs.get(str(kpi_key), 0.0)
            scale = kpi_scale_map.get(str(kpi_key), 1.0)
            try:
                contrib_f = float(contrib_val)
                weight_f = float(weight)
                scale_f = float(scale)
                total += weight_f * (contrib_f / scale_f)
            except Exception:
                continue
        return total
    
    else:
        # Fallback or unsupported mode
        return 0.0


def _compute_achieved_contribution(
    *,
    candidates: List[Candidate],
    selected_keys: set[str],
    dimension: str,
    dimension_key: str,
    kpi_key: str,
) -> float:
    """
    Sum KPI contributions over selected candidates matching dimension slice.
    
    Matches solver target constraint logic (case-insensitive dimension matching).
    """
    total = 0.0
    
    # Normalize dimension_key for case-insensitive comparison (matches solver)
    dim_key_lower = str(dimension_key).strip().lower()
    
    for c in candidates:
        if c.initiative_key not in selected_keys:
            continue
        
        # Check dimension match (same logic as solver - case-insensitive)
        if dimension == "all":
            # Global target: include all selected
            pass
        elif dimension == "country":
            if str(c.country or "").strip().lower() != dim_key_lower:
                continue
        elif dimension == "product":
            if str(c.product or "").strip().lower() != dim_key_lower:
                continue
        elif dimension == "department":
            if str(c.department or "").strip().lower() != dim_key_lower:
                continue
        elif dimension == "category":
            if str(c.category or "").strip().lower() != dim_key_lower:
                continue
        elif dimension == "program":
            if str(c.program or "").strip().lower() != dim_key_lower:
                continue
        elif dimension == "segment":
            if str(c.segment or "").strip().lower() != dim_key_lower:
                continue
        else:
            # Unknown dimension: skip
            continue
        
        # Add contribution
        contribs = c.kpi_contributions or {}
        contrib_val = contribs.get(kpi_key, 0.0)
        try:
            total += float(contrib_val)
        except Exception:
            continue
    
    return total


def _compute_severity(gap: float, target: float) -> str:
    """
    Compute severity level based on gap and target.
    
    Rules:
    - gap <= 0: OK (target met or exceeded)
    - gap/target <= 0.05: WARN (within 5% of target)
    - else: CRITICAL
    """
    if gap <= 0:
        return "OK"
    
    if target == 0:
        # Avoid division by zero: if target is 0 and gap > 0, it's critical
        return "CRITICAL"
    
    ratio = gap / target
    if ratio <= 0.05:
        return "WARN"
    else:
        return "CRITICAL"


def _build_gap_summary(problem: OptimizationProblem, solution: OptimizationSolution) -> str:
    """
    Build short gap summary string for Runs tab.
    
    Format: "UK GMV: -120; ALL retention: -0.01" (first 3 gaps, truncated)
    """
    targets = problem.constraint_set.targets or {}
    selected_items = solution.selected or []
    selected_keys = {item.initiative_key for item in selected_items if item.selected}
    
    gap_items = []
    for dimension, dim_map in targets.items():
        if not isinstance(dim_map, dict):
            continue
        for dimension_key, kpi_map in dim_map.items():
            if not isinstance(kpi_map, dict):
                continue
            for kpi_key, target_spec in kpi_map.items():
                if not isinstance(target_spec, dict):
                    continue
                
                target_type = target_spec.get("type")
                if target_type != "floor":
                    continue
                
                target_value = target_spec.get("value", 0.0)
                try:
                    target_value = float(target_value)
                except Exception:
                    continue
                
                achieved = _compute_achieved_contribution(
                    candidates=problem.candidates,
                    selected_keys=selected_keys,
                    dimension=dimension,
                    dimension_key=dimension_key,
                    kpi_key=kpi_key,
                )
                
                gap = target_value - achieved
                if gap > 0:  # Only include unmet targets
                    label = f"{dimension_key} {kpi_key}" if dimension != "all" else f"ALL {kpi_key}"
                    gap_items.append(f"{label}: {gap:+.2f}")
                
                if len(gap_items) >= 3:
                    break
            if len(gap_items) >= 3:
                break
        if len(gap_items) >= 3:
            break
    
    if not gap_items:
        return "All targets met"
    
    return "; ".join(gap_items)
