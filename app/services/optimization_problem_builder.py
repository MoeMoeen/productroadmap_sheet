# app/services/optimization_problem_builder.py
"""
Builder service for OptimizationProblem objects.

Responsibilities:
1. Load scenario + constraint set from DB
2. Load candidate initiatives (scoped by selection or period)
3. Apply pre-solver deadline feasibility filtering
4. Project Initiative → Candidate
5. Validate governance constraints reference valid candidates
6. Return clean, solver-ready OptimizationProblem

CRITICAL Phase 5 rule: Deadlines enforced PRE-SOLVER via feasibility filtering.
Solver never sees time-infeasible candidates.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.models.initiative import Initiative
from app.db.models.optimization import OptimizationScenario, OptimizationConstraintSet
from app.utils.periods import parse_period_key
from app.services.feasibility_filters import is_deadline_feasible
from app.schemas.optimization_problem import (
    OptimizationProblem,
    ObjectiveSpec,
    RunScope,
    Candidate,
    ConstraintSetPayload,
)

logger = logging.getLogger(__name__)

ScopeType = Literal["selected_only", "all_candidates"]


def build_optimization_problem(
    db: Session,
    scenario_name: str,
    constraint_set_name: str,
    scope_type: ScopeType,
    selected_initiative_keys: Optional[List[str]] = None,
    period_end_date: Optional[date] = None,
) -> OptimizationProblem:
    """
    Build a complete OptimizationProblem ready for solver.
    
    Args:
        db: Database session
        scenario_name: Name of the optimization scenario
        constraint_set_name: Name of the constraint set to use
        scope_type: How to select candidates ("selected_only" or "all_candidates")
        selected_initiative_keys: Required if scope_type="selected_only"
        period_end_date: Period end date for deadline filtering (auto-computed if None)
        
    Returns:
        OptimizationProblem with all constraints compiled and candidates filtered
        
    Raises:
        ValueError: If scenario/constraint set not found, or configuration invalid
    """
    # --- 1) Load scenario ---
    scenario = (
        db.query(OptimizationScenario)
        .filter(OptimizationScenario.name == scenario_name.strip())
        .first()
    )
    if not scenario:
        raise ValueError(f"Scenario not found: {scenario_name}")

    # Determine period end date for deadline feasibility filtering
    if period_end_date is None:
        if scenario.period_key:  # type: ignore[truthy-value]
            # PRODUCTION FIX: Use robust period parser
            try:
                period_end_date = parse_period_key(str(scenario.period_key)).end
            except ValueError as e:
                raise ValueError(
                    f"Invalid period_key '{scenario.period_key}' in scenario '{scenario.name}': {e}"
                ) from e
        else:
            # PRODUCTION FIX: Fail fast with clear message
            raise ValueError(
                f"Scenario '{scenario.name}' has no period_key. "
                "period_key is required for deadline feasibility filtering."
            )

    logger.info(
        "Building optimization problem",
        extra={
            "scenario_name": scenario_name,
            "constraint_set_name": constraint_set_name,
            "scope_type": scope_type,
            "period_key": scenario.period_key,
            "period_end_date": period_end_date.isoformat(),
        },
    )

    # --- 2) Load constraint set ---
    cset = (
        db.query(OptimizationConstraintSet)
        .filter(
            OptimizationConstraintSet.scenario_id == scenario.id,
            OptimizationConstraintSet.name == constraint_set_name.strip(),
        )
        .first()
    )
    if not cset:
        raise ValueError(
            f"Constraint set '{constraint_set_name}' not found for scenario '{scenario.name}'"
        )

    # --- 3) Build candidate query based on scope ---
    if scope_type == "selected_only":
        if not selected_initiative_keys:
            raise ValueError(
                "selected_initiative_keys is required when scope_type='selected_only'"
            )
        # PRODUCTION FIX: Use modern SQLAlchemy select() syntax
        stmt = select(Initiative).where(
            Initiative.initiative_key.in_(selected_initiative_keys)
        )
    else:
        # all_candidates => period-scoped candidate pool
        stmt = select(Initiative).where(
            Initiative.is_optimization_candidate.is_(True),
            Initiative.candidate_period_key == scenario.period_key,
        )

    initiatives: List[Initiative] = list(db.execute(stmt).scalars().all())

    # PRODUCTION FIX: Warn if candidate pool is unexpectedly empty
    if not initiatives:
        logger.warning(
            "No candidates found for optimization problem",
            extra={
                "scenario_name": scenario_name,
                "period_key": scenario.period_key,
                "scope_type": scope_type,
                "selected_count": len(selected_initiative_keys) if selected_initiative_keys else 0,
            },
        )

    # --- 4) Pre-solver deadline filter (Phase 5 lock) ---
    feasible: List[Initiative] = []
    excluded_deadline: List[str] = []
    for i in initiatives:
        if is_deadline_feasible(i, period_end_date):
            feasible.append(i)
        else:
            excluded_deadline.append(str(i.initiative_key))  # type: ignore[arg-type]
            logger.debug(
                "Excluding initiative due to deadline",
                extra={
                    "initiative_key": i.initiative_key,
                    "deadline_date": i.deadline_date.isoformat() if i.deadline_date else None,  # type: ignore[union-attr]
                    "period_end_date": period_end_date.isoformat(),
                },
            )

    if excluded_deadline:
        logger.info(
            "Excluded initiatives due to deadline infeasibility",
            extra={
                "count": len(excluded_deadline),
                "excluded_keys": excluded_deadline[:10],  # Log first 10
            },
        )

    # --- 5) Project initiatives -> Candidate objects ---
    candidates: List[Candidate] = []
    for i in feasible:
        tokens = i.engineering_tokens
        if tokens is None:
            # PRODUCTION FIX: Fail fast with clear message
            raise ValueError(
                f"Missing engineering_tokens for candidate '{i.initiative_key}'. "
                f"All candidates must have engineering_tokens defined for optimization."
            )

        # PRODUCTION FIX: Convert Decimal to float (SQLAlchemy may return Decimal from JSON)
        if isinstance(tokens, Decimal):
            tokens = float(tokens)

        # PRODUCTION FIX: Validate tokens >= 0 (caught early before solver)
        if float(tokens) < 0:  # type: ignore[arg-type]
            raise ValueError(
                f"Invalid engineering_tokens for candidate '{i.initiative_key}': "
                f"must be >= 0, got {tokens}"
            )

        # KPI contributions are stored on Initiative.kpi_contribution_json
        kpi_contrib = i.kpi_contribution_json or {}
        
        # PRODUCTION FIX: Ensure numeric floats, handle Decimal/string creep
        cleaned_contrib: Dict[str, float] = {}
        if isinstance(kpi_contrib, dict):
            for k, v in kpi_contrib.items():
                try:
                    # Convert Decimal to float if needed
                    if isinstance(v, Decimal):
                        cleaned_contrib[str(k)] = float(v)
                    else:
                        cleaned_contrib[str(k)] = float(v)
                except (TypeError, ValueError):
                    # PRODUCTION FIX: Log warning but don't fail - skip non-numeric contributions
                    logger.warning(
                        "Skipping non-numeric KPI contribution",
                        extra={
                            "initiative_key": i.initiative_key,
                            "kpi_key": k,
                            "value": v,
                        },
                    )
                    continue

        # PRODUCTION FIX: Correct field mapping from Initiative to Candidate
        # Note: SQLAlchemy ORM instance attributes return Python values, not Column objects
        # type: ignore comments suppress false positives from Pylance static analysis
        candidates.append(
            Candidate(
                initiative_key=str(i.initiative_key),  # type: ignore[arg-type]
                engineering_tokens=float(tokens),  # type: ignore[arg-type]
                # Dimension mapping (PRODUCTION FIX: Use correct Initiative fields)
                country=i.country,  # type: ignore[arg-type]
                department=i.department,  # type: ignore[arg-type]
                category=i.category,  # type: ignore[arg-type]
                program=i.program_key,  # type: ignore[arg-type]  # Initiative.program_key → Candidate.program
                product=i.product_area,  # type: ignore[arg-type]  # Initiative.product_area → Candidate.product
                segment=i.customer_segment,  # type: ignore[arg-type]  # Initiative.customer_segment → Candidate.segment
                region=None,  # PRODUCTION FIX: region doesn't exist on Initiative model
                # KPI contributions (cleaned)
                kpi_contributions=cleaned_contrib,
                # Optional display fields
                title=i.title,  # type: ignore[arg-type]
                active_overall_score=i.overall_score,  # type: ignore[arg-type]
            )
        )

    # --- 6) Build ObjectiveSpec ---
    # PRODUCTION FIX: Ensure objective_mode is properly typed
    obj_mode = str(scenario.objective_mode or "north_star").strip()
    if obj_mode not in ("north_star", "weighted_kpis", "lexicographic"):
        raise ValueError(
            f"Invalid objective_mode '{obj_mode}' in scenario '{scenario.name}'. "
            f"Must be one of: north_star, weighted_kpis, lexicographic"
        )

    objective = ObjectiveSpec(
        mode=obj_mode,  # type: ignore[arg-type]
        weights=scenario.objective_weights_json or None,  # type: ignore[arg-type]
        normalization="targets",
        # PRODUCTION FIX: Could add north_star_kpi_key if stored somewhere. We are supposed to persist metrics including north star
        # in OrganizationMetricsConfig.kpi_key,	OrganizationMetricsConfig.kpi_name, OrganizationMetricsConfig.kpi_level, etc.
        # north_star_kpi_key="north_star_gmv",
    )

    # --- 7) Build ConstraintSetPayload from DB JSON fields ---
    # PRODUCTION FIX: Governance rules come ONLY from cset.*_json, not from Initiative
    # SQLAlchemy ORM attributes return Python dicts/lists, not Column objects
    constraint_payload = ConstraintSetPayload(
        floors=cset.floors_json or {},  # type: ignore[arg-type]
        caps=cset.caps_json or {},  # type: ignore[arg-type]
        targets=cset.targets_json or {},  # type: ignore[arg-type]
        mandatory_initiatives=cset.mandatory_initiatives_json or [],  # type: ignore[arg-type]
        bundles=cset.bundles_json or [],  # type: ignore[arg-type]
        exclusions_initiatives=cset.exclusions_initiatives_json or [],  # type: ignore[arg-type]
        exclusions_pairs=cset.exclusions_pairs_json or [],  # type: ignore[arg-type]
        prerequisites=cset.prerequisites_json or {},  # type: ignore[arg-type]
        synergy_bonuses=cset.synergy_bonuses_json or [],  # type: ignore[arg-type]
        notes=cset.notes,  # type: ignore[arg-type]
    )

    # --- 8) Post-build validation: governance constraints must reference valid candidates ---
    # PRODUCTION FIX: Catch governance mismatches early
    candidate_keys = {c.initiative_key for c in candidates}
    _validate_governance_references(constraint_payload, candidate_keys)

    # --- 9) RunScope ---
    scope = RunScope(
        type=scope_type,
        initiative_keys=selected_initiative_keys if scope_type == "selected_only" else None,
    )

    # --- 10) Pack OptimizationProblem with diagnostic metadata ---
    # SQLAlchemy ORM attributes return Python values at runtime
    problem = OptimizationProblem(
        scenario_name=str(scenario.name),  # type: ignore[arg-type]
        constraint_set_name=str(cset.name),  # type: ignore[arg-type]
        period_key=scenario.period_key,  # type: ignore[arg-type]
        capacity_total_tokens=scenario.capacity_total_tokens,  # type: ignore[arg-type]
        objective=objective,
        candidates=candidates,
        constraint_set=constraint_payload,
        scope=scope,
        metadata={
            "deadline_filter_period_end": period_end_date.isoformat(),
            "excluded_due_to_deadline": excluded_deadline,
            "candidate_count_before_deadline_filter": len(initiatives),
            "candidate_count_after_deadline_filter": len(candidates),
            "scenario_id": scenario.id,
            "constraint_set_id": cset.id,
        },
    )

    logger.info(
        "Built optimization problem successfully",
        extra={
            "scenario_name": scenario_name,
            "constraint_set_name": constraint_set_name,
            "candidate_count": len(candidates),
            "excluded_deadline_count": len(excluded_deadline),
        },
    )

    return problem


def _validate_governance_references(
    constraint_payload: ConstraintSetPayload,
    candidate_keys: set[str],
) -> None:
    """
    PRODUCTION FIX: Validate that all governance constraint references
    point to initiatives that exist in the candidate pool.
    
    This catches configuration errors early before solver runs.
    
    Raises:
        ValueError: If governance constraints reference non-existent candidates
    """
    errors: List[str] = []

    # Check mandatory initiatives
    for key in constraint_payload.mandatory_initiatives:
        if key not in candidate_keys:
            errors.append(
                f"Mandatory initiative '{key}' is not in candidate pool"
            )

    # Check bundle members
    for bundle in constraint_payload.bundles:
        bundle_key = bundle.get("bundle_key", "")
        members = bundle.get("members", [])
        for member in members:
            if member not in candidate_keys:
                errors.append(
                    f"Bundle '{bundle_key}' member '{member}' is not in candidate pool"
                )

    # Check prerequisite references
    for dependent, prereqs in constraint_payload.prerequisites.items():
        if dependent not in candidate_keys:
            errors.append(
                f"Prerequisite dependent '{dependent}' is not in candidate pool"
            )
        for prereq in prereqs:
            if prereq not in candidate_keys:
                errors.append(
                    f"Prerequisite '{prereq}' (for '{dependent}') is not in candidate pool"
                )

    # Check exclusion pairs
    for pair in constraint_payload.exclusions_pairs:
        if len(pair) == 2:
            a, b = pair
            if a not in candidate_keys:
                errors.append(
                    f"Exclusion pair member '{a}' is not in candidate pool"
                )
            if b not in candidate_keys:
                errors.append(
                    f"Exclusion pair member '{b}' is not in candidate pool"
                )

    # Check synergy pairs
    for pair in constraint_payload.synergy_bonuses:
        if len(pair) == 2:
            a, b = pair
            if a not in candidate_keys:
                errors.append(
                    f"Synergy pair member '{a}' is not in candidate pool"
                )
            if b not in candidate_keys:
                errors.append(
                    f"Synergy pair member '{b}' is not in candidate pool"
                )

    if errors:
        # PRODUCTION FIX: Fail fast with clear, actionable error message
        error_msg = (
            "Governance constraints reference initiatives not in candidate pool:\n"
            + "\n".join(f"  - {e}" for e in errors[:10])  # Show first 10
        )
        if len(errors) > 10:
            error_msg += f"\n  ... and {len(errors) - 10} more errors"
        raise ValueError(error_msg)
