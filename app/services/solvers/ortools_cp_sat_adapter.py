# app/services/solvers/ortools_cp_sat_adapter.py
"""
OR-Tools CP-SAT solver adapter for Phase 5 optimization.

Implements constraints in order:
1. ✅ Binary selection + capacity caps (global and by dimension)
2. TODO: Mandatory initiatives
3. TODO: Exclusions (single + pair)
4. TODO: Prerequisites
5. TODO: Bundles (all-or-nothing)
6. TODO: Target floors
7. TODO: Objective modes (north_star, weighted_kpis, lexicographic)

CP-SAT is integer-based, so we scale floats by TOKEN_SCALE.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

from ortools.sat.python import cp_model

if TYPE_CHECKING:
    from app.schemas.optimization_problem import OptimizationProblem, Candidate
    from app.schemas.optimization_solution import OptimizationSolution

logger = logging.getLogger(__name__)

# Scale factor for converting floats to integers (3 decimal places preserved)
TOKEN_SCALE = 1000


@dataclass(frozen=True)
class CpSatConfig:
    """Configuration for OR-Tools CP-SAT solver."""
    
    max_time_seconds: float = 10.0
    num_workers: int = 8
    log_search_progress: bool = False


def _scaled_int(value: float, scale: int) -> int:
    """
    Convert float to scaled integer (production-friendly: deterministic rounding).
    
    Args:
        value: Float value to scale
        scale: Scale factor (e.g., 1000 for 3 decimal places)
        
    Returns:
        Scaled integer value
    """
    return int(round(float(value) * scale))


def _get_candidate_dim_value(c: "Candidate", dimension: str) -> Optional[str]:
    """
    Map constraint dimensions to Candidate attributes.
    Keep this centralized to avoid "stringly-typed" bugs.
    
    Args:
        c: Candidate to extract dimension value from
        dimension: Dimension name (country, department, category, etc.)
        
    Returns:
        Dimension value or None if dimension not supported
    """
    dim = dimension.strip().lower()
    if dim == "all":
        return "all"
    if dim == "country":
        return c.country
    if dim == "department":
        return c.department
    if dim == "category":
        return c.category
    if dim == "program":
        return c.program
    if dim == "product":
        return c.product
    if dim == "segment":
        return c.segment
    # Unknown dimension => not supported in v1
    return None


class OrtoolsCpSatSolverAdapter:
    """
    Phase 5 v1 solver adapter using OR-Tools CP-SAT.

    This adapter translates OptimizationProblem -> CP-SAT model.
    We'll implement constraints in the agreed order.

    Step 1 (this file now): binary selection + capacity caps (global and by dimension)
    """

    def __init__(self, config: Optional[CpSatConfig] = None) -> None:
        self.config = config or CpSatConfig()

    def solve_step1_capacity_only(self, problem: "OptimizationProblem") -> "OptimizationSolution":
        """
        STEP 1 ONLY:
        - binary decision x_i ∈ {0,1}
        - capacity caps: global cap and per-dimension caps from constraint_set.caps
        - no objective yet (satisfy constraints only -> CP-SAT finds any feasible solution)

        Returns:
            OptimizationSolution with status and which initiatives were selected.
        """
        from app.schemas.optimization_solution import OptimizationSolution, SelectedItem
        
        logger.info(
            "Building CP-SAT model (Step 1: capacity caps only)",
            extra={
                "candidate_count": len(problem.candidates),
                "scenario": problem.scenario_name,
                "constraint_set": problem.constraint_set_name,
            },
        )

        # ---- Build model ----
        model = cp_model.CpModel()

        # decision vars
        x: Dict[str, cp_model.IntVar] = {}
        token_cost: Dict[str, int] = {}

        for c in problem.candidates:
            key = c.initiative_key
            x[key] = model.NewBoolVar(f"x_{key}")  # type: ignore[attr-defined]

            # tokens must be non-negative and already validated upstream, but keep it safe
            cost = _scaled_int(c.engineering_tokens, TOKEN_SCALE)
            if cost < 0:
                logger.error(
                    "Negative engineering_tokens detected",
                    extra={"initiative_key": key, "tokens": c.engineering_tokens},
                )
                return OptimizationSolution(
                    status="model_invalid",
                    diagnostics={"error": f"Negative engineering_tokens for {key}"},
                )
            token_cost[key] = cost

        # ---- Capacity caps ----
        # We may have both:
        #  - scenario.capacity_total_tokens
        #  - caps["all"]["all"]
        # In v1: enforce BOTH if present (most conservative, avoids surprises).
        caps = problem.constraint_set.caps or {}

        # 1) Scenario global cap (capacity_total_tokens)
        if problem.capacity_total_tokens is not None:
            global_cap = _scaled_int(problem.capacity_total_tokens, TOKEN_SCALE)
            model.Add(sum(token_cost[k] * x[k] for k in x.keys()) <= global_cap)  # type: ignore[attr-defined]
            logger.info(
                "Added global capacity cap",
                extra={"capacity_total_tokens": problem.capacity_total_tokens},
            )

        # 2) Caps from constraint_set.caps (including all/all)
        caps_applied = 0
        for dim, dim_map in caps.items():
            for dim_key, max_tokens in (dim_map or {}).items():
                if max_tokens is None:
                    continue
                cap_val = _scaled_int(float(max_tokens), TOKEN_SCALE)
                dim_s = str(dim).strip().lower()
                dkey_s = str(dim_key).strip()

                # Determine which candidates are in this slice
                in_slice: List[str] = []
                for c in problem.candidates:
                    v = _get_candidate_dim_value(c, dim_s)
                    if v is None:
                        continue
                    # For targets you lowercase country; for caps you decided not to lowercase dimension_key.
                    # Keep exact match semantics.
                    if str(v) == dkey_s:
                        in_slice.append(c.initiative_key)

                # If cap is defined for a slice but no candidates match, that's okay; cap is vacuously satisfied.
                if not in_slice:
                    logger.debug(
                        "Cap defined but no candidates match slice",
                        extra={"dimension": dim_s, "dimension_key": dkey_s},
                    )
                    continue

                model.Add(sum(token_cost[k] * x[k] for k in in_slice) <= cap_val)  # type: ignore[attr-defined]
                caps_applied += 1
                logger.debug(
                    "Added dimension cap",
                    extra={
                        "dimension": dim_s,
                        "dimension_key": dkey_s,
                        "max_tokens": max_tokens,
                        "candidates_in_slice": len(in_slice),
                    },
                )

        logger.info(
            "Capacity caps applied",
            extra={
                "caps_count": caps_applied,
                "has_global_cap": problem.capacity_total_tokens is not None,
            },
        )

        # ---- No objective yet: find any feasible solution ----
        # TODO Step 7: Add objective when implementing objective modes
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(self.config.max_time_seconds)
        solver.parameters.num_search_workers = int(self.config.num_workers)
        solver.parameters.log_search_progress = bool(self.config.log_search_progress)

        logger.info(
            "Running CP-SAT solver",
            extra={
                "max_time_seconds": self.config.max_time_seconds,
                "num_workers": self.config.num_workers,
            },
        )

        status = solver.Solve(model)

        status_map = {
            cp_model.OPTIMAL: "optimal",
            cp_model.FEASIBLE: "feasible",
            cp_model.INFEASIBLE: "infeasible",
            cp_model.MODEL_INVALID: "model_invalid",
        }
        out_status = status_map.get(status, "unknown")

        logger.info(
            "CP-SAT solver completed",
            extra={
                "status": out_status,
                "wall_time_seconds": solver.WallTime(),
            },
        )

        # Build result
        selected_items: List[SelectedItem] = []
        used_tokens_int = 0

        for c in problem.candidates:
            key = c.initiative_key
            is_sel = bool(solver.Value(x[key])) if out_status in {"optimal", "feasible"} else False
            if is_sel:
                used_tokens_int += token_cost[key]
            selected_items.append(
                SelectedItem(
                    initiative_key=key,
                    selected=is_sel,
                    allocated_tokens=float(c.engineering_tokens) if is_sel else 0.0,
                )
            )

        used_tokens = used_tokens_int / TOKEN_SCALE if out_status in {"optimal", "feasible"} else None

        selected_count = sum(1 for item in selected_items if item.selected)
        logger.info(
            "Solution built",
            extra={
                "selected_count": selected_count,
                "capacity_used_tokens": used_tokens,
            },
        )

        return OptimizationSolution(
            status=out_status,  # type: ignore[arg-type]
            selected=selected_items,
            capacity_used_tokens=used_tokens,
            diagnostics={
                "token_scale": TOKEN_SCALE,
                "candidate_count": len(problem.candidates),
                "caps_dimensions": list((problem.constraint_set.caps or {}).keys()),
                "solver_wall_time_seconds": solver.WallTime(),
            },
        )
