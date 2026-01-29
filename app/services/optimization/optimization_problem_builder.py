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
from typing import Any, Dict, List, Literal, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.models.initiative import Initiative
from app.db.models.optimization import OptimizationScenario, OptimizationConstraintSet, OrganizationMetricConfig
from app.utils.periods import parse_period_key
from app.services.optimization.feasibility_filters import is_deadline_feasible
from app.schemas.optimization_problem import (
    OptimizationProblem,
    ObjectiveSpec,
    RunScope,
    Candidate,
    ConstraintSetPayload,
)

logger = logging.getLogger(__name__)

ScopeType = Literal["selected_only", "all_candidates"]


def _resolve_active_north_star_kpi_key(db: Session) -> str:
    """
    Resolve the single active North Star KPI key from OrganizationMetricConfig.
    
    Production rule (Phase 5):
      - Exactly one row with kpi_level="north_star" AND is_active=True required
    
    Returns:
        The kpi_key of the active north_star KPI
        
    Raises:
        ValueError: If zero or multiple active north_star KPIs found
    """
    rows = db.scalars(select(OrganizationMetricConfig)).all()
    
    north_stars = [
        r for r in rows
        if str(r.kpi_level).strip().lower() == "north_star" and bool(r.is_active)
    ]
    
    if len(north_stars) == 0:
        all_ns = [r for r in rows if str(r.kpi_level).strip().lower() == "north_star"]
        raise ValueError(
            f"No active north_star KPI found in OrganizationMetricConfig. "
            f"Found {len(all_ns)} north_star KPIs total (all inactive or is_active=False). "
            f"Please set is_active=True for exactly 1 north_star KPI."
        )
    
    if len(north_stars) > 1:
        keys = [str(r.kpi_key) for r in north_stars]
        raise ValueError(
            f"Expected exactly 1 active north_star KPI, found {len(north_stars)}: {keys}. "
            f"Please ensure only 1 KPI has kpi_level='north_star' AND is_active=True."
        )
    
    kpi_key = str(north_stars[0].kpi_key).strip()
    logger.info(f"Resolved north_star KPI: {kpi_key} (is_active=True)")
    return kpi_key


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
        # Use modern SQLAlchemy select() syntax
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

    # Warn if candidate pool is unexpectedly empty
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
            # Fail fast with clear message
            raise ValueError(
                f"Missing engineering_tokens for candidate '{i.initiative_key}'. "
                f"All candidates must have engineering_tokens defined for optimization."
            )

        # Convert Decimal to float (SQLAlchemy may return Decimal from JSON)
        if isinstance(tokens, Decimal):
            tokens = float(tokens)

        # Validate tokens >= 0 (caught early before solver)
        if float(tokens) < 0:  # type: ignore[arg-type]
            raise ValueError(
                f"Invalid engineering_tokens for candidate '{i.initiative_key}': "
                f"must be >= 0, got {tokens}"
            )

        # KPI contributions are stored on Initiative.kpi_contribution_json
        kpi_contrib = i.kpi_contribution_json or {}
        
        # Ensure numeric floats, handle Decimal/string creep
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
                    # Log warning but don't fail - skip non-numeric contributions
                    logger.warning(
                        "Skipping non-numeric KPI contribution",
                        extra={
                            "initiative_key": i.initiative_key,
                            "kpi_key": k,
                            "value": v,
                        },
                    )
                    continue

        # Correct field mapping from Initiative to Candidate
        # Note: SQLAlchemy ORM instance attributes return Python values, not Column objects
        # type: ignore comments suppress false positives from Pylance static analysis
        candidates.append(
            Candidate(
                initiative_key=str(i.initiative_key),  # type: ignore[arg-type]
                engineering_tokens=float(tokens),  # type: ignore[arg-type]
                # Dimension mapping (Use correct Initiative fields)
                country=i.country,  # type: ignore[arg-type]
                department=i.department,  # type: ignore[arg-type]
                category=i.category,  # type: ignore[arg-type]
                program=i.program_key,  # type: ignore[arg-type]  # Initiative.program_key → Candidate.program
                product=i.product_area,  # type: ignore[arg-type]  # Initiative.product_area → Candidate.product
                segment=i.customer_segment,  # type: ignore[arg-type]  # Initiative.customer_segment → Candidate.segment
                # KPI contributions (cleaned)
                kpi_contributions=cleaned_contrib,
                # Optional display fields
                title=i.title,  # type: ignore[arg-type]
                active_overall_score=i.overall_score,  # type: ignore[arg-type]
            )
        )

    # --- 6) Build ObjectiveSpec ---
    # Ensure objective_mode is properly typed
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
    )
    
    # Step 6.1: Resolve north_star_kpi_key if mode is "north_star"
    if objective.mode == "north_star":
        try:
            objective.north_star_kpi_key = _resolve_active_north_star_kpi_key(db)
            logger.info(
                "Resolved north_star_kpi_key for objective",
                extra={"north_star_kpi_key": objective.north_star_kpi_key}
            )
        except ValueError as e:
            raise ValueError(
                f"Failed to resolve north_star_kpi_key for scenario '{scenario.name}': {e}"
            ) from e
    
    # Step 6.2: Validate weighted_kpis KPI keys against OrganizationMetricConfig
    elif objective.mode == "weighted_kpis":
        if not objective.weights:
            raise ValueError(
                f"objective.weights is required when objective.mode='weighted_kpis' for scenario '{scenario.name}'"
            )
        
        # Load active KPIs from OrganizationMetricConfig
        all_kpi_rows = db.scalars(select(OrganizationMetricConfig)).all()
        active_kpis = {
            str(r.kpi_key).strip(): str(r.kpi_level).strip().lower()
            for r in all_kpi_rows
            if bool(r.is_active)
        }
        
        # Validate each weighted KPI exists and is active
        invalid_kpis: List[str] = []
        non_strategic_kpis: List[str] = []
        
        for kpi_key in objective.weights.keys():
            kpi_key_str = str(kpi_key).strip()
            if kpi_key_str not in active_kpis:
                invalid_kpis.append(kpi_key_str)
            else:
                level = active_kpis[kpi_key_str]
                # Allow north_star and strategic KPIs only (immediate KPIs are too granular for portfolio optimization)
                if level not in ("north_star", "strategic"):
                    non_strategic_kpis.append(f"{kpi_key_str} (level={level})")
        
        if invalid_kpis:
            raise ValueError(
                f"Invalid KPI keys in objective.weights for scenario '{scenario.name}': {invalid_kpis}. "
                f"These KPIs are not active in OrganizationMetricConfig."
            )
        
        if non_strategic_kpis:
            raise ValueError(
                f"Invalid KPI levels in objective.weights for scenario '{scenario.name}': {non_strategic_kpis}. "
                f"Only 'north_star' and 'strategic' KPIs are allowed in weighted_kpis objective."
            )
        
        logger.info(
            "Validated weighted_kpis objective KPI keys",
            extra={
                "weights_count": len(objective.weights),
                "kpi_keys": list(objective.weights.keys())
            }
        )

    # --- 7) Build ConstraintSetPayload from DB JSON fields ---
    # Governance rules come ONLY from cset.*_json, not from Initiative
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

    # --- 8) Validate/filter constraints based on scope policy ---
    # CRITICAL: Different validation strategy based on scope type
    #
    # scope_type="all_candidates": STRICT validation
    #   - Constraints are authoritative for full portfolio
    #   - Any missing reference is a configuration error → FAIL FAST
    #
    # scope_type="selected_only": FILTER + WARN (subset sandbox mode)
    #   - User explicitly selected subset for quick test
    #   - Filter constraints to only apply to selected pool
    #   - Log warnings for auditability, mark run as sandboxed
    
    candidate_keys = {c.initiative_key for c in candidates}
    
    # Initialize variables for metadata tracking
    warnings: List[str] = []
    counts: Dict[str, int] = {}
    total_dropped = 0
    
    if scope_type == "all_candidates":
        # Strict validation: fail if any constraint references missing initiative
        _validate_constraints_references_strict(constraint_payload, candidate_keys)
        
        logger.info(
            "opt_problem_builder.strict_validation_passed",
            extra={
                "scope_type": scope_type,
                "candidate_count": len(candidates),
            }
        )
    
    elif scope_type == "selected_only":
        # Filter mode: apply constraints only to selected pool, log warnings
        filtered_payload, warnings, counts = _filter_constraints_for_pool(
            constraint_payload,
            candidate_keys
        )
        
        # Replace payload with filtered version
        constraint_payload = filtered_payload
        
        # Log detailed warnings
        total_dropped = sum(counts.values())
        if total_dropped > 0:
            logger.warning(
                "opt_problem_builder.constraints_filtered_for_subset",
                extra={
                    "scope_type": scope_type,
                    "total_dropped": total_dropped,
                    "counts_by_type": counts,
                    "warning_samples": warnings[:10],
                }
            )
        
        logger.info(
            "opt_problem_builder.filter_mode_applied",
            extra={
                "scope_type": scope_type,
                "candidate_count": len(candidates),
                "constraints_dropped": total_dropped,
            }
        )

    # --- 9) RunScope ---
    scope = RunScope(
        type=scope_type,
        initiative_keys=selected_initiative_keys if scope_type == "selected_only" else None,
    )

    # --- 10) Pack OptimizationProblem with diagnostic metadata ---
    # SQLAlchemy ORM attributes return Python values at runtime
    metadata_dict: Dict[str, Any] = {
        "deadline_filter_period_end": period_end_date.isoformat(),
        "excluded_due_to_deadline": excluded_deadline,
        "candidate_count_before_deadline_filter": len(initiatives),
        "candidate_count_after_deadline_filter": len(candidates),
        "scenario_id": scenario.id,
        "constraint_set_id": cset.id,
    }
    
    # Add constraint filtering metadata for selected_only runs
    if scope_type == "selected_only":
        metadata_dict["scope_is_sandboxed_subset"] = True
        metadata_dict["constraint_filter_applied"] = True
        if total_dropped > 0:
            metadata_dict["constraint_filter_warnings"] = warnings[:50]  # Store first 50 for auditability
            metadata_dict["constraint_filter_counts"] = counts
            metadata_dict["constraint_filter_total_dropped"] = total_dropped
    
    problem = OptimizationProblem(
        scenario_name=str(scenario.name),  # type: ignore[arg-type]
        constraint_set_name=str(cset.name),  # type: ignore[arg-type]
        period_key=scenario.period_key,  # type: ignore[arg-type]
        capacity_total_tokens=scenario.capacity_total_tokens,  # type: ignore[arg-type]
        objective=objective,
        candidates=candidates,
        constraint_set=constraint_payload,
        scope=scope,
        metadata=metadata_dict,
    )

    logger.info(
        "Built optimization problem successfully",
        extra={
            "scenario_name": scenario_name,
            "constraint_set_name": constraint_set_name,
            "scope_type": scope_type,
            "candidate_count": len(candidates),
            "excluded_deadline_count": len(excluded_deadline),
        },
    )

    return problem


def _validate_constraints_references_strict(
    constraint_payload: ConstraintSetPayload,
    candidate_keys: set[str],
) -> None:
    """
    STRICT validation: Ensure all governance constraint references
    point to initiatives that exist in the candidate pool.
    
    Use this for scope_type="all_candidates" runs where constraints
    are authoritative and mismatches indicate configuration errors.
    
    Raises:
        ValueError: If any governance constraint references non-existent candidates
    """
    errors: List[str] = []
    
    # Check mandatory initiatives
    missing_mandatory = [k for k in constraint_payload.mandatory_initiatives if k not in candidate_keys]
    if missing_mandatory:
        errors.append(f"Mandatory initiatives not in candidate pool: {missing_mandatory}")
    
    # Check bundles
    for bundle in constraint_payload.bundles:
        bundle_key = bundle.get("bundle_key", "")
        members = bundle.get("members", [])
        missing_members = [m for m in members if m not in candidate_keys]
        if missing_members:
            errors.append(f"Bundle '{bundle_key}' references missing initiatives: {missing_members}")
    
    # Check prerequisites
    for dependent, prereqs in constraint_payload.prerequisites.items():
        if dependent not in candidate_keys:
            errors.append(f"Prerequisite dependent '{dependent}' not in candidate pool")
        missing_prereqs = [p for p in prereqs if p not in candidate_keys]
        if missing_prereqs:
            errors.append(f"Prerequisites for '{dependent}' reference missing initiatives: {missing_prereqs}")
    
    # Check single-initiative exclusions
    missing_exclusions = [k for k in constraint_payload.exclusions_initiatives if k not in candidate_keys]
    if missing_exclusions:
        errors.append(f"Exclusion initiatives not in candidate pool: {missing_exclusions}")
    
    # Check exclusion pairs
    for pair in constraint_payload.exclusions_pairs:
        if len(pair) == 2:
            a, b = pair
            if a not in candidate_keys or b not in candidate_keys:
                errors.append(f"Exclusion pair ({a}, {b}) references missing initiatives")
    
    # Check synergy bonuses
    for pair in constraint_payload.synergy_bonuses:
        if len(pair) == 2:
            a, b = pair
            if a not in candidate_keys or b not in candidate_keys:
                errors.append(f"Synergy bonus pair ({a}, {b}) references missing initiatives")
    
    if errors:
        error_msg = "Governance constraints reference initiatives not in candidate pool:\\n" + "\\n".join(errors[:10])
        if len(errors) > 10:
            error_msg += f"\\n... and {len(errors) - 10} more errors"
        raise ValueError(error_msg)


def _filter_constraints_for_pool(
    constraint_payload: ConstraintSetPayload,
    candidate_keys: set[str],
) -> tuple[ConstraintSetPayload, List[str], Dict[str, int]]:
    """
    FILTER mode: Return new constraint payload with only references
    that exist in candidate pool. Used for scope_type="selected_only" subset runs.
    
    This is a PURE function - does not mutate input payload.
    
    Args:
        constraint_payload: Original constraint set
        candidate_keys: Set of initiative keys in selected pool
    
    Returns:
        Tuple of:
        - New filtered ConstraintSetPayload
        - List of warning messages (all dropped constraints)
        - Dict of counts per constraint type dropped
    """
    warnings: List[str] = []
    counts: Dict[str, int] = {
        "mandatory": 0,
        "bundles": 0,
        "prerequisites": 0,
        "exclusions_initiatives": 0,
        "exclusions_pairs": 0,
        "synergy_bonuses": 0,
    }
    
    # Filter mandatory initiatives - keep only those in pool
    filtered_mandatory = []
    for key in constraint_payload.mandatory_initiatives:
        if key in candidate_keys:
            filtered_mandatory.append(key)
        else:
            warnings.append(f"Mandatory initiative '{key}' not in selected pool (dropped)")
            counts["mandatory"] += 1
    
    # Filter bundles - keep only bundles where ALL members are in pool
    filtered_bundles = []
    for bundle in constraint_payload.bundles:
        bundle_key = bundle.get("bundle_key", "")
        members = bundle.get("members", [])
        missing_members = [m for m in members if m not in candidate_keys]
        if missing_members:
            warnings.append(f"Bundle '{bundle_key}' dropped (members not in pool: {', '.join(missing_members)})")
            counts["bundles"] += 1
        else:
            filtered_bundles.append(bundle)
    
    # Filter prerequisites - keep only where both dependent and all prereqs are in pool
    filtered_prereqs = {}
    for dependent, prereqs in constraint_payload.prerequisites.items():
        if dependent not in candidate_keys:
            warnings.append(f"Prerequisite for '{dependent}' dropped (dependent not in pool)")
            counts["prerequisites"] += 1
            continue
        valid_prereqs = [p for p in prereqs if p in candidate_keys]
        missing_prereqs = [p for p in prereqs if p not in candidate_keys]
        if missing_prereqs:
            warnings.append(f"Prerequisites for '{dependent}' partially dropped (missing: {', '.join(missing_prereqs)})")
            counts["prerequisites"] += len(missing_prereqs)
        if valid_prereqs:
            filtered_prereqs[dependent] = valid_prereqs
    
    # Filter single-initiative exclusions - keep only those in pool
    filtered_exclusions = []
    for key in constraint_payload.exclusions_initiatives:
        if key in candidate_keys:
            filtered_exclusions.append(key)
        else:
            warnings.append(f"Exclusion initiative '{key}' dropped (not in pool)")
            counts["exclusions_initiatives"] += 1
    
    # Filter exclusion pairs - keep only pairs where BOTH are in pool
    filtered_exclusion_pairs = []
    for pair in constraint_payload.exclusions_pairs:
        if len(pair) == 2:
            a, b = pair
            if a not in candidate_keys or b not in candidate_keys:
                warnings.append(f"Exclusion pair ({a}, {b}) dropped (not both in pool)")
                counts["exclusions_pairs"] += 1
            else:
                filtered_exclusion_pairs.append(pair)
    
    # Filter synergy bonuses - keep only pairs where BOTH are in pool
    filtered_synergy = []
    for pair in constraint_payload.synergy_bonuses:
        if len(pair) == 2:
            a, b = pair
            if a not in candidate_keys or b not in candidate_keys:
                warnings.append(f"Synergy bonus ({a}, {b}) dropped (not both in pool)")
                counts["synergy_bonuses"] += 1
            else:
                filtered_synergy.append(pair)
    
    # Create new payload (immutable pattern)
    filtered_payload = ConstraintSetPayload(
        floors=constraint_payload.floors,
        caps=constraint_payload.caps,
        targets=constraint_payload.targets,
        mandatory_initiatives=filtered_mandatory,
        bundles=filtered_bundles,
        exclusions_initiatives=filtered_exclusions,
        exclusions_pairs=filtered_exclusion_pairs,
        prerequisites=filtered_prereqs,
        synergy_bonuses=filtered_synergy,
        notes=constraint_payload.notes,
    )
    
    return filtered_payload, warnings, counts
