# app/services/feasibility_checker.py
"""
Fast, deterministic feasibility checks BEFORE calling the solver.
Operates purely on OptimizationProblem + optional PeriodWindow.

This catches hard contradictions (mandatory+excluded, prerequisite cycles, etc.)
and cheap capacity/target impossibilities that would cause solver failure.

Phase 5 scope: Portfolio selection, not scheduling.
Time constraints (deadlines) are enforced pre-solver via feasibility_filters.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

from app.schemas.optimization_problem import OptimizationProblem
from app.schemas.feasibility import FeasibilityIssue, FeasibilityReport


@dataclass(frozen=True)
class PeriodWindow:
    """Time period with start and end dates (for future time-aware checks)."""
    start: date
    end: date


class FeasibilityChecker:
    """
    Fast, deterministic feasibility checks BEFORE calling the solver.
    Operates purely on OptimizationProblem + optional PeriodWindow.
    """

    def check(self, problem: OptimizationProblem, period_window: Optional[PeriodWindow] = None) -> FeasibilityReport:
        """
        Run all feasibility checks and return structured report.
        
        Args:
            problem: The optimization problem to check
            period_window: Optional period window (for future time-aware checks)
            
        Returns:
            FeasibilityReport with errors and warnings
        """
        issues: List[FeasibilityIssue] = []

        candidate_keys = {c.initiative_key for c in problem.candidates}

        # --- 1) Basic candidate sanity ---
        issues.extend(self._check_candidate_tokens(problem))

        # --- 2) Governance contradictions ---
        issues.extend(self._check_mandatory_references(problem, candidate_keys))
        issues.extend(self._check_exclusions(problem, candidate_keys))
        issues.extend(self._check_bundles(problem, candidate_keys))
        issues.extend(self._check_prerequisites(problem, candidate_keys))
        issues.extend(self._check_synergy_pairs(problem, candidate_keys))

        # --- 3) Capacity feasibility (cheap necessary conditions) ---
        issues.extend(self._check_capacity_bounds(problem, candidate_keys))

        # --- 4) Target feasibility (cheap necessary condition when possible) ---
        # Only checks "floor" targets against max achievable using candidates (ignores capacity and other constraints)
        issues.extend(self._check_target_floors_upper_bound(problem))

        # Optional: if you later add time-aware info to candidates, period_window could be used.
        # In Phase 5 we enforce deadlines pre-solver, so no time checks here.

        return FeasibilityReport.from_issues(issues)

    # -------------------------
    # Candidate sanity
    # -------------------------

    def _check_candidate_tokens(self, problem: OptimizationProblem) -> List[FeasibilityIssue]:
        """Check that all candidates have valid engineering_tokens."""
        issues: List[FeasibilityIssue] = []
        for c in problem.candidates:
            if c.engineering_tokens is None:
                issues.append(
                    FeasibilityIssue(
                        severity="error",
                        code="CANDIDATE_MISSING_TOKENS",
                        message=f"Candidate {c.initiative_key} is missing engineering_tokens.",
                        initiative_keys=[c.initiative_key],
                    )
                )
            elif c.engineering_tokens < 0:
                issues.append(
                    FeasibilityIssue(
                        severity="error",
                        code="CANDIDATE_NEGATIVE_TOKENS",
                        message=f"Candidate {c.initiative_key} has negative engineering_tokens.",
                        initiative_keys=[c.initiative_key],
                        details={"engineering_tokens": c.engineering_tokens},
                    )
                )
        if not problem.candidates:
            issues.append(
                FeasibilityIssue(
                    severity="error",
                    code="NO_CANDIDATES",
                    message="No candidates provided to optimizer after pre-solver filtering.",
                )
            )
        return issues

    # -------------------------
    # Governance checks
    # -------------------------

    def _check_mandatory_references(self, problem: OptimizationProblem, candidate_keys: Set[str]) -> List[FeasibilityIssue]:
        """Check that all mandatory initiatives exist in candidate pool."""
        issues: List[FeasibilityIssue] = []
        mandatory = set(problem.constraint_set.mandatory_initiatives or [])
        missing = sorted([k for k in mandatory if k not in candidate_keys])
        if missing:
            # Not necessarily infeasible by itself, but usually indicates mismatch between selection scope and constraints.
            issues.append(
                FeasibilityIssue(
                    severity="error",
                    code="MANDATORY_NOT_IN_CANDIDATES",
                    message="Mandatory initiative(s) are not present in the candidate set.",
                    initiative_keys=missing,
                )
            )
        return issues

    def _check_exclusions(self, problem: OptimizationProblem, candidate_keys: Set[str]) -> List[FeasibilityIssue]:
        """Check for contradictions between mandatory and exclusions."""
        issues: List[FeasibilityIssue] = []

        mandatory = set(problem.constraint_set.mandatory_initiatives or [])
        excluded_single = set(problem.constraint_set.exclusions_initiatives or [])
        excluded_pairs = problem.constraint_set.exclusions_pairs or []

        # mandatory ∧ excluded_single
        both = sorted(list(mandatory.intersection(excluded_single)))
        if both:
            issues.append(
                FeasibilityIssue(
                    severity="error",
                    code="MANDATORY_EXCLUDED",
                    message="Initiative(s) marked mandatory are also excluded (exclude_initiative).",
                    initiative_keys=both,
                )
            )

        # mandatory ∧ excluded_pair
        for pair in excluded_pairs:
            if len(pair) != 2:
                continue
            a, b = pair[0], pair[1]
            if a in mandatory and b in mandatory:
                issues.append(
                    FeasibilityIssue(
                        severity="error",
                        code="MANDATORY_EXCLUSION_PAIR",
                        message=f"Both initiatives in an exclusion pair are mandatory: {a} and {b}.",
                        initiative_keys=[a, b],
                    )
                )

        # Warn about exclusion refs not in candidates (not fatal)
        dangling = sorted([k for k in excluded_single if k not in candidate_keys])
        if dangling:
            issues.append(
                FeasibilityIssue(
                    severity="warning",
                    code="EXCLUSION_REF_NOT_IN_CANDIDATES",
                    message="Some excluded initiatives are not present in candidate set (may be OK depending on scope).",
                    initiative_keys=dangling,
                )
            )

        return issues

    def _check_bundles(self, problem: OptimizationProblem, candidate_keys: Set[str]) -> List[FeasibilityIssue]:
        """Check bundle constraint validity."""
        issues: List[FeasibilityIssue] = []
        mandatory = set(problem.constraint_set.mandatory_initiatives or [])
        bundles = problem.constraint_set.bundles or []

        for b in bundles:
            bundle_key = str(b.get("bundle_key", "")).strip()
            members = [str(x).strip() for x in (b.get("members") or []) if str(x).strip()]
            if not bundle_key or not members:
                issues.append(
                    FeasibilityIssue(
                        severity="warning",
                        code="BUNDLE_EMPTY",
                        message="Bundle has empty bundle_key or members.",
                        details={"bundle": b},
                    )
                )
                continue

            missing = sorted([m for m in members if m not in candidate_keys])
            if missing:
                issues.append(
                    FeasibilityIssue(
                        severity="error",
                        code="BUNDLE_MEMBER_NOT_IN_CANDIDATES",
                        message=f"Bundle '{bundle_key}' contains members not present in candidate set.",
                        initiative_keys=missing,
                        details={"bundle_key": bundle_key},
                    )
                )

            # Mandatory subset rule:
            # If any member is mandatory, bundle semantics imply all members must be selected.
            # That's feasible only if all are in candidates (already checked) and not excluded. We check exclusion separately.
            any_mandatory = [m for m in members if m in mandatory]
            if any_mandatory:
                issues.append(
                    FeasibilityIssue(
                        severity="warning",
                        code="MANDATORY_IMPLICIT_BUNDLE",
                        message=f"Bundle '{bundle_key}' contains mandatory member(s); bundle implies all members must be selected.",
                        initiative_keys=sorted(any_mandatory),
                        details={"bundle_key": bundle_key, "members": members},
                    )
                )

        return issues

    def _check_prerequisites(self, problem: OptimizationProblem, candidate_keys: Set[str]) -> List[FeasibilityIssue]:
        """Check prerequisite constraint validity and detect cycles."""
        issues: List[FeasibilityIssue] = []
        prereqs = problem.constraint_set.prerequisites or {}
        mandatory = set(problem.constraint_set.mandatory_initiatives or [])

        # 1) Reference validity
        for dep, reqs in prereqs.items():
            dep = str(dep).strip()
            if not dep:
                continue
            if dep not in candidate_keys:
                issues.append(
                    FeasibilityIssue(
                        severity="warning",
                        code="PREREQ_DEP_NOT_IN_CANDIDATES",
                        message=f"Prerequisite dependent initiative not in candidates: {dep}.",
                        initiative_keys=[dep],
                    )
                )
            cleaned = [str(r).strip() for r in (reqs or []) if str(r).strip()]
            missing = sorted([r for r in cleaned if r not in candidate_keys])
            if missing:
                issues.append(
                    FeasibilityIssue(
                        severity="error",
                        code="PREREQ_MEMBER_NOT_IN_CANDIDATES",
                        message=f"Prerequisites for {dep} include initiatives not in candidate set.",
                        initiative_keys=[dep] + missing,
                        details={"dependent": dep, "missing_prereqs": missing},
                    )
                )

        # 2) Cycle detection (error)
        cycles = self._detect_prereq_cycles(prereqs)
        for cycle in cycles:
            issues.append(
                FeasibilityIssue(
                    severity="error",
                    code="PREREQ_CYCLE",
                    message=f"Prerequisite cycle detected: {' -> '.join(cycle)}",
                    initiative_keys=cycle,
                )
            )

        # 3) Mandatory with unmet prereqs (if mandatory is dependent, its prereqs must be selectable)
        for dep in mandatory:
            if dep in prereqs:
                reqs = [str(r).strip() for r in prereqs.get(dep) or [] if str(r).strip()]
                missing = [r for r in reqs if r not in candidate_keys]
                if missing:
                    issues.append(
                        FeasibilityIssue(
                            severity="error",
                            code="MANDATORY_PREREQ_MISSING",
                            message=f"Mandatory initiative {dep} has prerequisite(s) missing from candidates.",
                            initiative_keys=[dep] + missing,
                        )
                    )

        return issues

    def _check_synergy_pairs(self, problem: OptimizationProblem, candidate_keys: Set[str]) -> List[FeasibilityIssue]:
        """Check synergy bonus constraint validity."""
        issues: List[FeasibilityIssue] = []
        pairs = problem.constraint_set.synergy_bonuses or []
        for pair in pairs:
            if len(pair) != 2:
                issues.append(
                    FeasibilityIssue(
                        severity="warning",
                        code="SYNERGY_PAIR_INVALID",
                        message="Synergy pair does not have exactly 2 initiatives.",
                        details={"pair": pair},
                    )
                )
                continue
            a, b = pair[0], pair[1]
            if a not in candidate_keys or b not in candidate_keys:
                issues.append(
                    FeasibilityIssue(
                        severity="warning",
                        code="SYNERGY_REF_NOT_IN_CANDIDATES",
                        message="Synergy pair references initiative(s) not in candidate set.",
                        initiative_keys=[x for x in [a, b] if x not in candidate_keys],
                        details={"pair": [a, b]},
                    )
                )
        return issues

    # -------------------------
    # Capacity feasibility checks
    # -------------------------

    def _check_capacity_bounds(self, problem: OptimizationProblem, candidate_keys: Set[str]) -> List[FeasibilityIssue]:
        """
        Cheap necessary conditions:
        - sum of floors (where applicable) must not exceed scenario capacity_total_tokens (if present)
        - any floor for a slice must not exceed total available tokens among candidates in that slice (upper bound)
        """
        issues: List[FeasibilityIssue] = []

        total_cap = problem.capacity_total_tokens
        floors = problem.constraint_set.floors or {}
        caps = problem.constraint_set.caps or {}

        # 1) Global cap consistency (if both provided)
        # If caps["all"]["all"] exists and scenario capacity exists, they should not conflict badly.
        cap_all = None
        if "all" in caps and "all" in caps["all"]:
            try:
                cap_all = float(caps["all"]["all"])
            except Exception:
                cap_all = None

        if total_cap is not None and cap_all is not None and cap_all != float(total_cap):
            issues.append(
                FeasibilityIssue(
                    severity="warning",
                    code="GLOBAL_CAP_MISMATCH",
                    message="Scenario capacity_total_tokens differs from caps['all']['all']. Solver will enforce both if adapter implements both.",
                    details={"capacity_total_tokens": total_cap, "caps_all_all": cap_all},
                )
            )

        # 2) Sum of explicit floors vs total capacity (necessary condition, not sufficient)
        if total_cap is not None:
            try:
                sum_floors = 0.0
                for dim, dim_map in floors.items():
                    # Only include meaningful floors. For "all/all" it's global anyway; still counts.
                    for _, v in (dim_map or {}).items():
                        sum_floors += float(v)
                if sum_floors > float(total_cap) + 1e-9:
                    issues.append(
                        FeasibilityIssue(
                            severity="error",
                            code="FLOORS_EXCEED_TOTAL_CAPACITY",
                            message="Sum of all capacity floors exceeds total capacity_total_tokens.",
                            details={"sum_floors": sum_floors, "capacity_total_tokens": float(total_cap)},
                        )
                    )
            except Exception:
                # If parsing fails, let solver adapter / validation handle; add warning
                issues.append(
                    FeasibilityIssue(
                        severity="warning",
                        code="FLOORS_PARSE_WARNING",
                        message="Could not compute sum of floors due to non-numeric values.",
                    )
                )

        # 3) Floor upper bound per slice (based on candidates only)
        # For each floor on (dimension, dimension_key), maximum available is sum(tokens of candidates matching that slice).
        # If floor > max available, infeasible.
        # We only implement this for common dimensions present on Candidate objects.
        slice_max = self._compute_slice_token_totals(problem)
        for dim, dim_map in floors.items():
            for dkey, min_tokens in (dim_map or {}).items():
                key = (str(dim), str(dkey))
                max_available = slice_max.get(key)
                if max_available is None:
                    # Unknown dimension for this candidate model; warn
                    issues.append(
                        FeasibilityIssue(
                            severity="warning",
                            code="FLOOR_DIMENSION_UNKNOWN",
                            message="Capacity floor uses a dimension not available on candidates (cannot pre-check).",
                            dimension=str(dim),
                            dimension_key=str(dkey),
                            details={"dimension": dim, "dimension_key": dkey},
                        )
                    )
                    continue
                if float(min_tokens) > float(max_available) + 1e-9:
                    issues.append(
                        FeasibilityIssue(
                            severity="error",
                            code="FLOOR_EXCEEDS_MAX_AVAILABLE",
                            message="Capacity floor exceeds maximum tokens available from candidates in that slice.",
                            dimension=str(dim),
                            dimension_key=str(dkey),
                            details={"floor": float(min_tokens), "max_available": float(max_available)},
                        )
                    )

        return issues

    def _compute_slice_token_totals(self, problem: OptimizationProblem) -> Dict[Tuple[str, str], float]:
        """
        Compute sum(tokens) per (dimension, dimension_key) based on candidate attributes.
        Supports the dimensions present on Candidate: country, department, category, program, segment, product, all.
        """
        totals: Dict[Tuple[str, str], float] = {("all", "all"): 0.0}
        for c in problem.candidates:
            t = float(c.engineering_tokens)
            totals[("all", "all")] += t

            for dim, attr_val in [
                ("country", c.country),
                ("department", c.department),
                ("category", c.category),
                ("program", c.program),
                ("segment", c.segment),
                ("product", c.product),
            ]:
                if attr_val:
                    totals[(dim, str(attr_val))] = totals.get((dim, str(attr_val)), 0.0) + t
        return totals

    # -------------------------
    # Target floor feasibility checks
    # -------------------------

    def _check_target_floors_upper_bound(self, problem: OptimizationProblem) -> List[FeasibilityIssue]:
        """
        Necessary condition check for FLOOR targets:
        - Compute an optimistic upper bound of achievable KPI contributions for each (dimension, dimension_key, kpi_key)
          by summing all candidate contributions that match that slice.
        - If upper bound < target floor => infeasible.

        This ignores capacity/governance, so it can only prove infeasibility, not feasibility.
        """
        issues: List[FeasibilityIssue] = []
        targets = problem.constraint_set.targets or {}
        if not targets:
            return issues

        # Precompute optimistic sums
        optimistic = self._compute_optimistic_kpi_totals(problem)

        for dim, dim_map in targets.items():
            for dim_key, kpi_map in (dim_map or {}).items():
                for kpi_key, spec in (kpi_map or {}).items():
                    try:
                        ttype = str(spec.get("type", "")).strip().lower()
                        if ttype != "floor":
                            continue
                        raw_value = spec.get("value")
                        if raw_value is None:
                            continue
                        floor_value = float(raw_value)
                    except Exception:
                        continue

                    key = (str(dim), str(dim_key), str(kpi_key))
                    ub = optimistic.get(key, 0.0)
                    if ub + 1e-9 < floor_value:
                        issues.append(
                            FeasibilityIssue(
                                severity="error",
                                code="TARGET_FLOOR_UNACHIEVABLE",
                                message="Floor target is unachievable even if selecting all candidates (upper bound check).",
                                dimension=str(dim),
                                dimension_key=str(dim_key),
                                details={"kpi_key": str(kpi_key), "target_floor": floor_value, "upper_bound": ub},
                            )
                        )

        return issues

    def _compute_optimistic_kpi_totals(self, problem: OptimizationProblem) -> Dict[Tuple[str, str, str], float]:
        """
        Optimistic sum of KPI contributions by slice:
        { (dimension, dimension_key, kpi_key): total_contribution }
        """
        totals: Dict[Tuple[str, str, str], float] = {}

        def add(dim: str, dim_key: str, kpi_key: str, val: float) -> None:
            k = (dim, dim_key, kpi_key)
            totals[k] = totals.get(k, 0.0) + val

        for c in problem.candidates:
            for kpi_key, val in (c.kpi_contributions or {}).items():
                try:
                    v = float(val)
                except Exception:
                    continue

                # all/all always gets the candidate contribution
                add("all", "all", str(kpi_key), v)

                # dimension-specific slices
                if c.country:
                    add("country", str(c.country).lower(), str(kpi_key), v)
                if c.department:
                    add("department", str(c.department), str(kpi_key), v)
                if c.category:
                    add("category", str(c.category), str(kpi_key), v)
                if c.program:
                    add("program", str(c.program), str(kpi_key), v)
                if c.segment:
                    add("segment", str(c.segment), str(kpi_key), v)
                if c.product:
                    add("product", str(c.product), str(kpi_key), v)

        return totals

    # -------------------------
    # Prereq cycle detection
    # -------------------------

    def _detect_prereq_cycles(self, prereqs: Dict[str, List[str]]) -> List[List[str]]:
        """
        Detect cycles in prerequisite graph.
        Returns list of cycles (each cycle is list of nodes in traversal order).
        """
        graph: Dict[str, List[str]] = {}
        for dep, reqs in (prereqs or {}).items():
            dep_s = str(dep).strip()
            if not dep_s:
                continue
            graph[dep_s] = [str(r).strip() for r in (reqs or []) if str(r).strip()]

        visited: Set[str] = set()
        stack: Set[str] = set()
        path: List[str] = []
        cycles: List[List[str]] = []

        def dfs(node: str) -> None:
            if node in stack:
                # cycle found: slice path from first occurrence
                if node in path:
                    idx = path.index(node)
                    cycles.append(path[idx:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            path.append(node)
            for nxt in graph.get(node, []):
                dfs(nxt)
            path.pop()
            stack.remove(node)

        for n in list(graph.keys()):
            if n not in visited:
                dfs(n)
        return cycles
