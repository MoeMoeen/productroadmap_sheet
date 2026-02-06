# productroadmap_sheet_project/app/services/optimization/constraint_explainer.py
"""
Generate human-readable explanations for optimization constraint violations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Set


@dataclass(frozen=True)
class Violation:
    code: str
    message: str
    severity: str = "error"
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionEvaluation:
    selected_keys: Set[str]
    is_feasible: bool
    violations: List[Violation] = field(default_factory=list)
    totals: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RepairStep:
    action: str
    initiative_key: str
    reason: str
    impact: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RepairPlan:
    initial_selected: Set[str]
    final_selected: Set[str]
    steps: List[RepairStep]
    final_evaluation: SelectionEvaluation
    summary: Dict[str, Any] = field(default_factory=dict)


# ----------------------------
# Helpers
# ----------------------------


def _safe_float(x: Any, default: float = 0.0) -> float:
    """Convert x to float, returning default on failure."""
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _safe_float_or_none(x: Any) -> Optional[float]:
    """Convert x to float, returning None on failure."""
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _candidate_map(problem: Any) -> Dict[str, Any]:
    """Create a map from initiative_key to candidate object."""
    return {c.initiative_key: c for c in getattr(problem, "candidates", [])}


def _get_dim_value(candidate: Any, dim: str) -> Optional[str]:
    """Get the value of a dimension attribute from a candidate, handling special cases like "all"."""
    d = (dim or "").strip().lower()
    if d == "all":
        return "all"
    return getattr(candidate, d, None)


def _sum_tokens(problem: Any, selected: Set[str]) -> float:
    """Sum the engineering tokens of selected candidates."""
    cmap = _candidate_map(problem)
    return sum(_safe_float(cmap[k].engineering_tokens) for k in selected if k in cmap)


def _sum_kpi(problem: Any, selected: Set[str], kpi_key: str) -> float:
    """Sum the specified KPI contributions of selected candidates."""
    cmap = _candidate_map(problem)
    total = 0.0
    for k in selected:
        c = cmap.get(k)
        if not c:
            continue
        contribs = getattr(c, "kpi_contributions", {}) or {}
        total += _safe_float(contribs.get(kpi_key))
    return total


def _slice_selected(problem: Any, selected: Set[str], dim: str, dim_key: str, *, lower_dim_key: bool = False) -> Set[str]:
    """Filter selected candidates by dimension and dimension key.

    When lower_dim_key=True, comparison is case-insensitive (matches solver caps/floors/targets semantics).
    """
    d = (dim or "").strip().lower()
    dk = (dim_key or "").strip()
    if lower_dim_key:
        dk = dk.lower()

    if d == "all":
        if dk.lower() != "all":
            return set()
        return set(selected)

    cmap = _candidate_map(problem)
    out: Set[str] = set()
    for k in selected:
        c = cmap.get(k)
        if not c:
            continue
        v = _get_dim_value(c, d)
        if v is None:
            continue
        vs = str(v).strip()
        if lower_dim_key:
            vs = vs.lower()
        if vs == dk:
            out.add(k)
    return out


# ----------------------------
# Evaluator (2)
# ----------------------------


def evaluate_selection(problem: Any, selected_keys: Iterable[str]) -> SelectionEvaluation:
    """Evaluate the feasibility of a selection of initiatives against the problem's constraints."""
    selected: Set[str] = {str(k).strip() for k in selected_keys if str(k).strip()}
    cmap = _candidate_map(problem)

    violations: List[Violation] = []

    missing_candidates = sorted([k for k in selected if k not in cmap])
    if missing_candidates:
        violations.append(
            Violation(
                code="SELECTION_KEYS_NOT_IN_POOL",
                message="Selection contains initiative keys not present in candidate pool snapshot.",
                details={"missing_keys": missing_candidates},
            )
        )

    cs = getattr(problem, "constraint_set", None)
    if cs is None:
        return SelectionEvaluation(selected_keys=selected, is_feasible=len(violations) == 0, violations=violations)

    mandatory = set(getattr(cs, "mandatory_initiatives", []) or [])
    missing_mandatory = sorted([k for k in mandatory if k not in selected])
    if missing_mandatory:
        violations.append(
            Violation(
                code="MANDATORY_NOT_SELECTED",
                message="Mandatory initiatives are not selected.",
                details={"missing_mandatory": missing_mandatory},
            )
        )

    excluded_single = set(getattr(cs, "exclusions_initiatives", []) or [])
    selected_excluded = sorted(list(selected.intersection(excluded_single)))
    if selected_excluded:
        violations.append(
            Violation(
                code="EXCLUDED_SELECTED",
                message="Some selected initiatives are excluded (exclude_initiative).",
                details={"selected_excluded": selected_excluded},
            )
        )

    excluded_pairs = getattr(cs, "exclusions_pairs", []) or []
    violated_pairs: List[tuple] = []
    for pair in excluded_pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        a, b = str(pair[0]).strip(), str(pair[1]).strip()
        if a in selected and b in selected:
            violated_pairs.append((a, b))
    if violated_pairs:
        violations.append(
            Violation(
                code="EXCLUSION_PAIR_BOTH_SELECTED",
                message="Some exclusion pairs have both initiatives selected.",
                details={"violated_pairs": violated_pairs},
            )
        )

    prereqs = getattr(cs, "prerequisites", {}) or {}
    missing_prereqs: List[tuple] = []
    for dep, reqs in prereqs.items():
        dep_k = str(dep).strip()
        if dep_k not in selected:
            continue
        req_list = [str(r).strip() for r in (reqs or []) if str(r).strip()]
        missing = [r for r in req_list if r not in selected]
        if missing:
            missing_prereqs.append((dep_k, missing))
    if missing_prereqs:
        violations.append(
            Violation(
                code="PREREQ_MISSING",
                message="Some selected initiatives are missing required prerequisites.",
                details={"missing_prereqs": missing_prereqs},
            )
        )

    bundles = getattr(cs, "bundles", []) or []
    broken_bundles: List[Dict[str, Any]] = []
    for b in bundles:
        if not isinstance(b, dict):
            continue
        bkey = str(b.get("bundle_key", "")).strip()
        members = [str(x).strip() for x in (b.get("members") or []) if str(x).strip()]
        if len(members) < 2:
            continue
        in_sel = [m for m in members if m in selected]
        if in_sel and len(in_sel) != len(members):
            broken_bundles.append({"bundle_key": bkey, "selected_members": in_sel, "all_members": members})
    if broken_bundles:
        violations.append(
            Violation(
                code="BUNDLE_PARTIALLY_SELECTED",
                message="Some bundles are partially selected (must be all-or-nothing).",
                details={"broken_bundles": broken_bundles},
            )
        )

    caps = getattr(cs, "caps", {}) or {}
    total_cap = _safe_float_or_none(getattr(problem, "capacity_total_tokens", None))
    total_used = _sum_tokens(problem, selected)

    if total_cap is not None and total_used > float(total_cap) + 1e-9:
        violations.append(
            Violation(
                code="GLOBAL_CAP_EXCEEDED",
                message="Total selected tokens exceed global scenario capacity_total_tokens.",
                details={"used": total_used, "cap": float(total_cap), "delta": total_used - float(total_cap)},
            )
        )

    cap_violations: List[Dict[str, Any]] = []
    for dim, dim_map in caps.items():
        if not isinstance(dim_map, dict):
            continue
        for dim_key, cap_val in dim_map.items():
            cap_f = _safe_float_or_none(cap_val)
            if cap_f is None:
                continue
            slice_sel = _slice_selected(problem, selected, str(dim), str(dim_key), lower_dim_key=True)
            used = _sum_tokens(problem, slice_sel)
            if used > cap_f + 1e-9:
                cap_violations.append(
                    {
                        "dimension": str(dim).strip().lower(),
                        "dimension_key": str(dim_key).strip().lower(),
                        "used": used,
                        "cap": cap_f,
                        "delta": used - cap_f,
                        "selected_keys": sorted(slice_sel),
                    }
                )
    if cap_violations:
        violations.append(
            Violation(
                code="CAP_EXCEEDED",
                message="One or more capacity caps are exceeded.",
                details={"caps_violated": cap_violations},
            )
        )

    floors = getattr(cs, "floors", {}) or {}
    floor_violations: List[Dict[str, Any]] = []
    for dim, dim_map in floors.items():
        if not isinstance(dim_map, dict):
            continue
        for dim_key, floor_val in dim_map.items():
            floor_f = _safe_float_or_none(floor_val)
            if floor_f is None:
                continue
            if floor_f <= 0:
                continue
            slice_sel = _slice_selected(problem, selected, str(dim), str(dim_key), lower_dim_key=True)
            used = _sum_tokens(problem, slice_sel)
            if used + 1e-9 < floor_f:
                floor_violations.append(
                    {
                        "dimension": str(dim).strip().lower(),
                        "dimension_key": str(dim_key).strip().lower(),
                        "used": used,
                        "floor": floor_f,
                        "delta": floor_f - used,
                        "selected_keys": sorted(slice_sel),
                    }
                )
    if floor_violations:
        violations.append(
            Violation(
                code="FLOOR_NOT_MET",
                message="One or more capacity floors are not met.",
                details={"floors_violated": floor_violations},
            )
        )

    targets = getattr(cs, "targets", {}) or {}
    target_floor_violations: List[Dict[str, Any]] = []
    for dim, dim_map in targets.items():
        if not isinstance(dim_map, dict):
            continue
        for dim_key, kpi_map in dim_map.items():
            if not isinstance(kpi_map, dict):
                continue
            for kpi_key, spec in kpi_map.items():
                if not isinstance(spec, dict):
                    continue
                if str(spec.get("type", "")).strip().lower() != "floor":
                    continue
                floor_val = spec.get("value")
                floor_f = _safe_float_or_none(floor_val)
                if floor_f is None:
                    continue

                slice_sel = _slice_selected(problem, selected, str(dim), str(dim_key), lower_dim_key=True)
                achieved = _sum_kpi(problem, slice_sel, str(kpi_key))
                if achieved + 1e-9 < floor_f:
                    target_floor_violations.append(
                        {
                            "dimension": str(dim).strip().lower(),
                            "dimension_key": str(dim_key).strip().lower(),
                            "kpi_key": str(kpi_key),
                            "achieved": achieved,
                            "floor": floor_f,
                            "gap": floor_f - achieved,
                            "selected_keys": sorted(slice_sel),
                        }
                    )
    if target_floor_violations:
        violations.append(
            Violation(
                code="TARGET_FLOOR_NOT_MET",
                message="One or more KPI floor targets are not met.",
                details={"targets_violated": target_floor_violations},
            )
        )

    totals: Dict[str, Any] = {
        "tokens_used_total": total_used,
        "selected_count": len([k for k in selected if k in cmap]),
        "mandatory_count": len(mandatory),
        "excluded_selected_count": len(selected_excluded),
        "prereq_violations_count": len(missing_prereqs),
        "bundle_violations_count": len(broken_bundles),
        "cap_violations_count": len(cap_violations),
        "floor_violations_count": len(floor_violations),
        "target_floor_violations_count": len(target_floor_violations),
    }

    is_feasible = len(violations) == 0
    return SelectionEvaluation(selected_keys=selected, is_feasible=is_feasible, violations=violations, totals=totals)


# ----------------------------
# Greedy repair (3)
# ----------------------------


def suggest_repairs(
    problem: Any,
    selected_keys: Iterable[str],
    *,
    max_steps: int = 30,
    allow_additions: bool = True,
) -> RepairPlan:
    """Suggest a repair plan greedily to fix constraint violations in the selected initiatives."""
    selected: Set[str] = {str(k).strip() for k in selected_keys if str(k).strip()}
    steps: List[RepairStep] = []

    cmap = _candidate_map(problem)
    cs = getattr(problem, "constraint_set", None)
    mandatory = set(getattr(cs, "mandatory_initiatives", []) or []) if cs is not None else set()
    prereqs_map = getattr(cs, "prerequisites", {}) or {} if cs is not None else {}

    # Build reverse map: prereq -> list[dependents]
    dependents_map: Dict[str, List[str]] = {}
    for dep, reqs in prereqs_map.items():
        for r in reqs or []:
            rk = str(r).strip()
            if rk:
                dependents_map.setdefault(rk, []).append(str(dep).strip())

    def penalty(ev: SelectionEvaluation) -> float:
        p = 0.0
        for v in ev.violations:
            if v.code in {"MANDATORY_NOT_SELECTED", "PREREQ_MISSING", "BUNDLE_PARTIALLY_SELECTED"}:
                p += 50.0
            elif v.code in {"EXCLUDED_SELECTED", "EXCLUSION_PAIR_BOTH_SELECTED"}:
                p += 40.0
            elif v.code in {"GLOBAL_CAP_EXCEEDED", "CAP_EXCEEDED"}:
                delta = 0.0
                if v.code == "GLOBAL_CAP_EXCEEDED":
                    delta = _safe_float(v.details.get("delta"), 0.0)
                p += 20.0 + delta
            elif v.code in {"FLOOR_NOT_MET", "TARGET_FLOOR_NOT_MET"}:
                p += 30.0
            else:
                p += 10.0
        return p

    # First, try adding missing mandatory/prereq/bundle items
    if allow_additions and cs is not None:
        for _ in range(max_steps):
            ev = evaluate_selection(problem, selected)
            if ev.is_feasible:
                break

            # If bundles are partially selected, consider fixing by removal (instead of completing) to avoid expanding selection
            bun_viols = [v for v in ev.violations if v.code == "BUNDLE_PARTIALLY_SELECTED"]
            if bun_viols:
                broken = bun_viols[0].details.get("broken_bundles", [])
                if broken:
                    b = broken[0]
                    sel_members = [m for m in b.get("selected_members", []) if m in selected and m in cmap and m not in mandatory]
                    if sel_members:
                        trial = set(selected)
                        for m in sel_members:
                            trial.discard(m)
                        trial_ev = evaluate_selection(problem, trial)
                        if penalty(trial_ev) < penalty(ev) - 1e-9:
                            for m in sel_members:
                                selected.discard(m)
                                steps.append(
                                    RepairStep(
                                        action="remove",
                                        initiative_key=m,
                                        reason=f"remove_bundle_member_{b.get('bundle_key','')}",
                                    )
                                )
                            continue

            mand_viols = [v for v in ev.violations if v.code == "MANDATORY_NOT_SELECTED"]
            if mand_viols:
                missing = mand_viols[0].details.get("missing_mandatory", [])
                added_any = False
                for k in missing:
                    kk = str(k).strip()
                    if kk and kk not in selected and kk in cmap:
                        selected.add(kk)
                        steps.append(RepairStep(action="add", initiative_key=kk, reason="add_missing_mandatory"))
                        added_any = True
                if added_any:
                    continue

            pre_viols = [v for v in ev.violations if v.code == "PREREQ_MISSING"]
            if pre_viols:
                items = pre_viols[0].details.get("missing_prereqs", [])
                added_any = False
                for dep, missing_list in items:
                    for m in missing_list:
                        mm = str(m).strip()
                        if mm and mm not in selected and mm in cmap:
                            selected.add(mm)
                            steps.append(RepairStep(action="add", initiative_key=mm, reason=f"add_prereq_for_{dep}"))
                            added_any = True
                if added_any:
                    continue

            bun_viols = [v for v in ev.violations if v.code == "BUNDLE_PARTIALLY_SELECTED"]
            if bun_viols:
                broken = bun_viols[0].details.get("broken_bundles", [])
                added_any = False
                for b in broken:
                    members = b.get("all_members", [])
                    for m in members:
                        mm = str(m).strip()
                        if mm and mm not in selected and mm in cmap:
                            selected.add(mm)
                            steps.append(RepairStep(action="add", initiative_key=mm, reason=f"complete_bundle_{b.get('bundle_key','')}"))
                            added_any = True
                if added_any:
                    continue

            break

    # Next, try removing items to reduce violations
    for _ in range(max_steps):
        ev = evaluate_selection(problem, selected)
        if ev.is_feasible:
            break

        removable = [k for k in selected if k in cmap and k not in mandatory]
        if not removable:
            break

        base_pen = penalty(ev)

        best_k: Optional[str] = None
        best_pen = base_pen
        best_eval: Optional[SelectionEvaluation] = None

        for k in removable:
            # If removing k would force removal of a mandatory dependent, skip this candidate
            mandatory_dependents = [dep for dep in dependents_map.get(k, []) if dep in selected and dep in mandatory]
            if mandatory_dependents:
                continue
            trial = set(selected)
            trial.remove(k)
            # If k is a prerequisite for any currently selected dependents, remove those dependents as well
            for dep in dependents_map.get(k, []):
                if dep in trial:
                    trial.remove(dep)
            trial_ev = evaluate_selection(problem, trial)
            trial_pen = penalty(trial_ev)
            if trial_pen < best_pen - 1e-9:
                best_pen = trial_pen
                best_k = k
                best_eval = trial_ev

        if best_k is None:
            break

        selected.remove(best_k)
        steps.append(
            RepairStep(
                action="remove",
                initiative_key=best_k,
                reason="greedy_remove_to_reduce_violations",
                impact={"penalty_before": base_pen, "penalty_after": best_pen},
            )
        )
        # Remove non-mandatory dependents that relied on the removed prerequisite
        for dep in dependents_map.get(best_k, []):
            if dep in selected and dep not in mandatory:
                selected.remove(dep)
                steps.append(
                    RepairStep(
                        action="remove",
                        initiative_key=dep,
                        reason=f"remove_dependent_of_{best_k}",
                    )
                )
    
    # Final evaluation
    final_eval = evaluate_selection(problem, selected)
    action_summary: Dict[str, Any] = {
        "added_count": sum(1 for s in steps if s.action == "add"),
        "removed_count": sum(1 for s in steps if s.action == "remove"),
        "reason_counts": dict(Counter(s.reason for s in steps)),
    }

    return RepairPlan(
        initial_selected={str(k).strip() for k in selected_keys if str(k).strip()},
        final_selected=set(selected),
        steps=steps,
        final_evaluation=final_eval,
        summary=action_summary,
    )
