# app/services/solvers/ortools_cp_sat_adapter.py
"""
OR-Tools CP-SAT solver adapter for Phase 5 optimization.

Implements constraints in order:
1. ✅ Binary selection variables (x_i ∈ {0,1} for each candidate)
2. ✅ Mandatory initiatives (x_i = 1 for each mandatory)
3. ✅ Exclusions (single: x_i = 0, pair: x_a + x_b <= 1)
4. ✅ Prerequisites (x_dep <= x_req for each prerequisite edge)
5. ✅ Bundles (all-or-nothing: x_m1 = x_m2 = ... = x_mk)
6. ✅ Capacity caps (sum(tokens_i * x_i) <= max_tokens for global and per-dimension)
7. ✅ Capacity floors (sum(tokens_i * x_i) >= min_tokens for each dimension slice)
8. ✅ Target floors (sum(contrib_i * x_i) >= floor for each KPI floor target)
9. TODO: Objective modes (north_star, weighted_kpis, lexicographic)

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
KPI_SCALE = 1_000_000  # preserve up to 6 decimals (good for rates like conversion)


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

def _get_candidate_dim_value_for_targets(c: "Candidate", dimension: str) -> Optional[str]:
    """
    Extract dimension value from candidate for target matching.
    Lowercases the result to match target compiler's lowercasing behavior.
    """
    v = _get_candidate_dim_value(c, dimension)
    if v is None:
        return None
    return str(v).strip().lower()


class OrtoolsCpSatSolverAdapter:
    """
    Phase 5 v1 solver adapter using OR-Tools CP-SAT.

    This adapter translates OptimizationProblem -> CP-SAT model.
    We'll implement constraints in the agreed order.

    Step 1 (this file now): binary selection + capacity caps (global and by dimension)
    """

    def __init__(self, config: Optional[CpSatConfig] = None) -> None:
        self.config = config or CpSatConfig()

    def solve(self, problem: "OptimizationProblem") -> "OptimizationSolution":
        """
        STEP 1-8: Build and solve CP-SAT model with all constraints
        
        Step 1: Binary decision variables x_i ∈ {0,1}
        Step 2: Mandatory initiatives (x_i = 1 for each mandatory)
        Step 3: Exclusions (single: x_i = 0, pairs: x_a + x_b <= 1)
        Step 4: Prerequisites (x_dep <= x_req for each prerequisite edge)
        Step 5: Bundles (all-or-nothing: x_m1 = x_m2 = ... = x_mk)
        Step 6: Capacity caps (global and per-dimension token limits)
        Step 6.5: Capacity floors (per-dimension minimum token allocations)
        Step 7: Target floors (sum(contrib_i * x_i) >= floor for each KPI floor target)
        Step 8: Objective function (north_star, weighted_kpis, or lexicographic)

        Returns:
            OptimizationSolution with status and which initiatives were selected.
        """
        from app.schemas.optimization_solution import OptimizationSolution, SelectedItem
        
        logger.info(
            "Building CP-SAT model: Steps 1-8 (decision vars, mandatory, exclusions, prerequisites, bundles, capacity caps/floors, target floors, objective)",
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

        # ---- Mandatory initiatives (Step 2) ----
        mandatory = set(problem.constraint_set.mandatory_initiatives or [])
        mandatory_applied = 0
        mandatory_missing: List[str] = []

        for key in sorted(mandatory):
            var = x.get(key)
            if var is None:
                # Should already be caught by feasibility checker, but keep solver defensive
                mandatory_missing.append(key)
                continue
            model.Add(var == 1)  # type: ignore[attr-defined]  # x_i = 1
            mandatory_applied += 1

        if mandatory_missing:
            logger.error(
                "Mandatory initiatives missing from candidate pool (solver defensive guard)",
                extra={"missing": mandatory_missing[:10]},
            )
            return OptimizationSolution(
                status="model_invalid",
                diagnostics={
                    "error": "mandatory_not_in_candidates",
                    "missing_mandatory": mandatory_missing,
                },
            )

        logger.info(
            "Mandatory constraints applied",
            extra={"mandatory_count": len(mandatory), "mandatory_applied": mandatory_applied},
        )

        # ---- Exclusions (Step 3A: exclude_initiative) ----
        excluded_single = set(problem.constraint_set.exclusions_initiatives or [])
        excluded_applied = 0
        excluded_missing: List[str] = []

        for key in sorted(excluded_single):
            var = x.get(key)
            if var is None:
                # Usually fine: exclusion may reference something not in candidate pool depending on scope
                excluded_missing.append(key)
                continue
            model.Add(var == 0)  # type: ignore[attr-defined]  # x_i = 0
            excluded_applied += 1

        if excluded_missing:
            logger.info(
                "Excluded initiatives not present in candidate pool (ignored)",
                extra={"count": len(excluded_missing), "examples": excluded_missing[:10]},
            )

        logger.info(
            "Exclude-initiative constraints applied",
            extra={"excluded_count": len(excluded_single), "excluded_applied": excluded_applied},
        )

        # ---- Exclusions (Step 3B: exclude_pair) ----
        excluded_pairs = problem.constraint_set.exclusions_pairs or []
        pairs_applied = 0
        pairs_skipped_missing = 0
        pairs_invalid = 0

        for pair in excluded_pairs:
            if not isinstance(pair, list) or len(pair) != 2:
                pairs_invalid += 1
                continue

            a, b = str(pair[0]).strip(), str(pair[1]).strip()
            if not a or not b or a == b:
                pairs_invalid += 1
                continue

            va = x.get(a)
            vb = x.get(b)

            # If one side is not in candidates, the pair is irrelevant for this run
            if va is None or vb is None:
                pairs_skipped_missing += 1
                continue

            model.Add(va + vb <= 1)  # type: ignore[attr-defined]  # x_a + x_b <= 1
            pairs_applied += 1

        if pairs_invalid:
            logger.warning(
                "Invalid exclude_pair rows encountered (ignored)",
                extra={"count": pairs_invalid},
            )

        logger.info(
            "Exclude-pair constraints applied",
            extra={
                "pairs_total": len(excluded_pairs),
                "pairs_applied": pairs_applied,
                "pairs_skipped_missing": pairs_skipped_missing,
                "pairs_invalid": pairs_invalid,
            },
        )

        # ---- Prerequisites (Step 4) ----
        prereqs = problem.constraint_set.prerequisites or {}
        prereq_edges_applied = 0
        prereq_missing_dependents = 0
        prereq_missing_prereqs = 0
        prereq_invalid = 0

        for dep_raw, req_list in prereqs.items():
            dep = str(dep_raw).strip()
            if not dep:
                prereq_invalid += 1
                continue

            v_dep = x.get(dep)
            if v_dep is None:
                # dep not in candidate pool for this run (likely selection scope)
                prereq_missing_dependents += 1
                continue

            if not isinstance(req_list, list) or not req_list:
                prereq_invalid += 1
                continue

            for req_raw in req_list:
                req = str(req_raw).strip()
                if not req or req == dep:
                    prereq_invalid += 1
                    continue

                v_req = x.get(req)
                if v_req is None:
                    # prereq not in candidate pool => prereq constraint irrelevant in this run
                    # (feasibility checker should have flagged this as error if dep is in candidates)
                    prereq_missing_prereqs += 1
                    continue

                # x_dep <= x_req
                model.Add(v_dep <= v_req)  # type: ignore[attr-defined]
                prereq_edges_applied += 1

        if prereq_invalid:
            logger.warning(
                "Invalid prerequisite entries encountered (ignored)",
                extra={"count": prereq_invalid},
            )

        logger.info(
            "Prerequisite constraints applied",
            extra={
                "dependent_count": len(prereqs),
                "edges_applied": prereq_edges_applied,
                "missing_dependents": prereq_missing_dependents,
                "missing_prereqs": prereq_missing_prereqs,
                "invalid_entries": prereq_invalid,
            },
        )

        # ---- Bundles (Step 5: all-or-nothing) ----
        bundles = problem.constraint_set.bundles or []
        bundles_applied = 0
        bundle_edges_applied = 0
        bundle_skipped_missing = 0
        bundle_invalid = 0

        for b in bundles:
            if not isinstance(b, dict):
                bundle_invalid += 1
                continue

            bundle_key = str(b.get("bundle_key", "")).strip()
            members_raw = b.get("members") or []

            if not bundle_key or not isinstance(members_raw, list):
                bundle_invalid += 1
                continue

            members = [str(x).strip() for x in members_raw if str(x).strip()]
            # Need at least 2 members to enforce all-or-nothing meaningfully
            if len(members) < 2:
                bundle_invalid += 1
                continue

            # Remove duplicates while preserving order
            seen = set()
            deduped: List[str] = []
            for m in members:
                if m not in seen:
                    seen.add(m)
                    deduped.append(m)
            members = deduped

            # If any member is not in the candidate pool, we cannot enforce this bundle in this run.
            # Feasibility checker should have caught this if bundle members are expected to exist.
            vars_in_bundle = [x.get(m) for m in members]
            if any(v is None for v in vars_in_bundle):
                bundle_skipped_missing += 1
                continue

            base = x[members[0]]
            # Enforce equality between base and each other member: x_mi == x_base
            for m in members[1:]:
                model.Add(x[m] == base)  # type: ignore[attr-defined]
                bundle_edges_applied += 1

            bundles_applied += 1
            logger.debug(
                "Bundle applied",
                extra={"bundle_key": bundle_key, "members_count": len(members)},
            )

        if bundle_invalid:
            logger.warning("Invalid bundle entries encountered (ignored)", extra={"count": bundle_invalid})

        logger.info(
            "Bundle constraints applied",
            extra={
                "bundles_total": len(bundles),
                "bundles_applied": bundles_applied,
                "bundle_edges_applied": bundle_edges_applied,
                "bundles_skipped_missing_refs": bundle_skipped_missing,
                "invalid_entries": bundle_invalid,
            },
        )

        # ---- Capacity caps (Step 6) ----
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

        # ---- Capacity floors (Step 6.5) ----
        floors = problem.constraint_set.floors or {}
        floors_total = 0
        floors_applied = 0
        floors_invalid = 0
        floors_empty_slice = 0
        floors_skipped_trivial = 0

        for dim, dim_map in floors.items():
            dim_s = str(dim).strip().lower()
            if not isinstance(dim_map, dict):
                floors_invalid += 1
                continue

            for dim_key, min_tokens in (dim_map or {}).items():
                if min_tokens is None:
                    floors_invalid += 1
                    continue

                try:
                    floor_val = float(min_tokens)
                except Exception:
                    floors_invalid += 1
                    continue

                floors_total += 1
                floor_int = _scaled_int(floor_val, TOKEN_SCALE)

                # Trivial floors (<= 0) don't need a constraint
                if floor_int <= 0:
                    floors_skipped_trivial += 1
                    continue

                dkey_s = str(dim_key).strip()

                # Build slice token sum
                slice_keys: List[str] = []
                for c in problem.candidates:
                    v = _get_candidate_dim_value(c, dim_s)
                    if v is None:
                        continue

                    if dim_s == "all":
                        if dkey_s != "all":
                            continue
                        slice_keys.append(c.initiative_key)
                    else:
                        # Floors match exact dimension_key (same semantics as caps)
                        if str(v) == dkey_s:
                            slice_keys.append(c.initiative_key)

                if not slice_keys:
                    floors_empty_slice += 1
                    logger.warning(
                        "Capacity floor has no candidates in slice (immediately infeasible)",
                        extra={
                            "dimension": dim_s,
                            "dimension_key": dkey_s,
                            "min_tokens": floor_val,
                        },
                    )
                    return OptimizationSolution(
                        status="infeasible",
                        diagnostics={
                            "error": "capacity_floor_empty_slice",
                            "dimension": dim_s,
                            "dimension_key": dkey_s,
                            "min_tokens": floor_val,
                        },
                    )

                # Enforce: sum(tokens_i * x_i) >= floor
                model.Add(sum(token_cost[k] * x[k] for k in slice_keys) >= floor_int)  # type: ignore[attr-defined]
                floors_applied += 1

        if floors_invalid:
            logger.warning(
                "Invalid capacity floor entries encountered (ignored)",
                extra={"count": floors_invalid},
            )

        logger.info(
            "Capacity floors processed",
            extra={
                "floors_total": floors_total,
                "floors_applied": floors_applied,
                "floors_skipped_trivial": floors_skipped_trivial,
                "floors_invalid": floors_invalid,
                "floors_empty_slice": floors_empty_slice,
                "token_scale": TOKEN_SCALE,
            },
        )

        # ---- Target floors (Step 7) ----
        targets = problem.constraint_set.targets or {}
        target_floors_total = 0
        target_floors_applied = 0
        target_floors_skipped = 0
        target_floors_invalid = 0
        target_floors_empty_slice = 0

        # targets shape: {dimension: {dimension_key: {kpi_key: {type,value,notes?}}}}
        for dim, dim_map in targets.items():
            dim_s = str(dim).strip().lower()
            if not isinstance(dim_map, dict):
                target_floors_invalid += 1
                continue

            for dim_key, kpi_map in dim_map.items():
                dim_key_s = str(dim_key).strip().lower()
                if not isinstance(kpi_map, dict):
                    target_floors_invalid += 1
                    continue

                for kpi_key, spec in kpi_map.items():
                    if not isinstance(spec, dict):
                        target_floors_invalid += 1
                        continue

                    ttype = str(spec.get("type", "")).strip().lower()
                    if ttype != "floor":
                        # Step 6 is floors only; goals handled later (Step 7 objective policy)
                        continue

                    raw_val = spec.get("value", None)
                    if raw_val is None:
                        target_floors_invalid += 1
                        continue

                    try:
                        floor_val = float(raw_val)
                    except Exception:
                        target_floors_invalid += 1
                        continue

                    target_floors_total += 1

                    # Build linear expression for this slice and KPI
                    terms = []
                    for c in problem.candidates:
                        # Slice membership check
                        c_dim_val = _get_candidate_dim_value_for_targets(c, dim_s)
                        if c_dim_val is None:
                            continue
                        if dim_s == "all":
                            # only accept all/all
                            if dim_key_s != "all":
                                continue
                        else:
                            if c_dim_val != dim_key_s:
                                continue

                        # Contribution lookup
                        contrib = c.kpi_contributions.get(str(kpi_key))
                        if contrib is None:
                            continue
                        try:
                            contrib_int = _scaled_int(float(contrib), KPI_SCALE)
                        except Exception:
                            continue
                        if contrib_int == 0:
                            continue

                        terms.append(contrib_int * x[c.initiative_key])

                    floor_int = _scaled_int(floor_val, KPI_SCALE)

                    # If no terms contribute and floor > 0, the model is infeasible.
                    # We can either let solver find infeasible, or short-circuit.
                    # Production-friendly: short-circuit with a clear infeasible result.
                    if not terms and floor_int > 0:
                        target_floors_empty_slice += 1
                        logger.warning(
                            "Target floor has no contributing candidates in slice (immediately infeasible)",
                            extra={
                                "dimension": dim_s,
                                "dimension_key": dim_key_s,
                                "kpi_key": str(kpi_key),
                                "floor_value": floor_val,
                            },
                        )
                        return OptimizationSolution(
                            status="infeasible",
                            diagnostics={
                                "error": "target_floor_empty_slice",
                                "dimension": dim_s,
                                "dimension_key": dim_key_s,
                                "kpi_key": str(kpi_key),
                                "floor_value": floor_val,
                            },
                        )

                    # Apply constraint: sum(contrib_i * x_i) >= floor
                    if terms:
                        model.Add(sum(terms) >= floor_int)  # type: ignore[attr-defined]
                        target_floors_applied += 1
                    else:
                        # floor_int <= 0 is trivially satisfied
                        target_floors_skipped += 1

        if target_floors_invalid:
            logger.warning(
                "Invalid target floor entries encountered (ignored)",
                extra={"count": target_floors_invalid},
            )

        logger.info(
            "Target floor constraints processed",
            extra={
                "floors_total": target_floors_total,
                "floors_applied": target_floors_applied,
                "floors_skipped_trivial": target_floors_skipped,
                "floors_invalid": target_floors_invalid,
                "floors_empty_slice": target_floors_empty_slice,
                "kpi_scale": KPI_SCALE,
            },
        )

        # ---- Step 8: Objective function ----
        # Objective modes: north_star, weighted_kpis, lexicographic
        
        obj_mode = getattr(problem.objective, "mode", None)
        obj_mode_str = str(obj_mode or "").strip().lower()
        
        if obj_mode_str == "north_star":
            # Step 8.1: North Star objective - maximize contribution to single north_star KPI
            ns_key = getattr(problem.objective, "north_star_kpi_key", None)
            ns_key_str = str(ns_key or "").strip() if ns_key else ""
            
            if not ns_key_str:
                logger.error("north_star objective mode requires north_star_kpi_key")
                return OptimizationSolution(
                    status="model_invalid",
                    diagnostics={"error": "north_star_kpi_key_missing", "objective_mode": "north_star"},
                )
            
            # Build objective: Maximize sum(contrib_i[north_star_kpi_key] * x_i)
            terms = []
            missing_contrib_count = 0
            
            for c in problem.candidates:
                contrib_val = (c.kpi_contributions or {}).get(ns_key_str)
                if contrib_val is None:
                    missing_contrib_count += 1
                    continue
                
                try:
                    contrib_float = float(contrib_val)
                    contrib_int = _scaled_int(contrib_float, KPI_SCALE)
                except (TypeError, ValueError) as e:
                    logger.warning(
                        f"Invalid north_star contribution for {c.initiative_key}: {contrib_val}",
                        extra={"initiative_key": c.initiative_key, "contrib_val": contrib_val, "error": str(e)}
                    )
                    continue
                
                if contrib_int == 0:
                    continue
                
                terms.append(contrib_int * x[c.initiative_key])
            
            # If nobody contributes, objective is 0; still solve feasibility
            objective_expr = sum(terms) if terms else 0
            model.Maximize(objective_expr)  # type: ignore[attr-defined]
            
            logger.info(
                "Step 8 objective: maximize north_star",
                extra={
                    "north_star_kpi_key": ns_key_str,
                    "contributing_candidates": len(terms),
                    "missing_contrib": missing_contrib_count,
                    "total_candidates": len(problem.candidates),
                }
            )
        
        else:
            # Fallback: temporary objective (maximize capacity usage)
            # TODO: Implement weighted_kpis (Step 8.2) and lexicographic (Step 8.3)
            model.Maximize(sum(token_cost[k] * x[k] for k in x.keys()))  # type: ignore[attr-defined]
            logger.info(
                "Step 8 objective fallback: maximize capacity usage (temporary)",
                extra={"objective_mode": obj_mode_str or "not_specified"}
            )
        
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
                "mandatory_count": len(problem.constraint_set.mandatory_initiatives or []),
                "mandatory_applied": mandatory_applied,
                "excluded_initiatives_count": len(problem.constraint_set.exclusions_initiatives or []),
                "excluded_pairs_count": len(problem.constraint_set.exclusions_pairs or []),
                "prereq_dependents_count": len(problem.constraint_set.prerequisites or {}),
                "bundles_count": len(problem.constraint_set.bundles or []),
                "capacity_floors_total": floors_total,
                "capacity_floors_applied": floors_applied,
                "target_floors_total": target_floors_total,
                "target_floors_applied": target_floors_applied,
                "kpi_scale": KPI_SCALE,
                "caps_dimensions": list((problem.constraint_set.caps or {}).keys()),
                "solver_wall_time_seconds": solver.WallTime(),
            },
        )
