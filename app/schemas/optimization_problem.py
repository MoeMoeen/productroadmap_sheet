# app/schemas/optimization_problem.py
"""
Frozen solver-facing problem schema (Phase 5).

CRITICAL RULE: Time feasibility (deadlines etc.) must be applied BEFORE 
candidates enter OptimizationProblem. The solver should never see 
time-infeasible candidates.

This schema defines the exact contract between problem builder and solver adapter.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


ObjectiveMode = Literal["north_star", "weighted_kpis", "lexicographic"]
NormalizationMode = Literal["targets"]  # Phase 5 lock: normalize by Targets in weighted_kpis
ScopeType = Literal["selected_only", "all_candidates"]


class ObjectiveSpec(BaseModel):
    """
    Defines the optimization objective function configuration.
    
    Modes:
    - north_star: Maximize single north star KPI
    - weighted_kpis: Maximize weighted sum of multiple KPIs
    - lexicographic: Prioritize KPIs in strict order (future)
    """
    model_config = ConfigDict(extra="ignore")

    mode: ObjectiveMode
    weights: Optional[Dict[str, float]] = None  # Required when mode == weighted_kpis
    normalization: Optional[NormalizationMode] = "targets"
    north_star_kpi_key: Optional[str] = None  # Optional for debugging/reporting

    @model_validator(mode="after")
    def _validate_objective(self) -> "ObjectiveSpec":
        """PRODUCTION FIX: Validate objective configuration consistency."""
        if self.mode == "weighted_kpis":
            if not self.weights:
                raise ValueError("objective.weights is required when objective.mode='weighted_kpis'")
            
            # PRODUCTION FIX: Clean + validate non-negative weights
            cleaned: Dict[str, float] = {}
            for k, v in self.weights.items():
                try:
                    fv = float(v)
                except (TypeError, ValueError) as e:
                    raise ValueError(f"objective.weights['{k}'] must be numeric, got {v!r}") from e
                
                if fv < 0:
                    raise ValueError(f"objective.weights['{k}'] must be >= 0, got {fv}")
                cleaned[str(k)] = fv
            
            if sum(cleaned.values()) == 0:
                raise ValueError("objective.weights must not sum to zero (at least one weight must be positive)")
            
            self.weights = cleaned
            
            # PRODUCTION FIX: Set default normalization
            if self.normalization is None:
                self.normalization = "targets"
        
        return self


class Candidate(BaseModel):
    """
    A single initiative candidate for optimization.
    
    IMPORTANT: This candidate has already passed deadline feasibility filtering.
    Solver should assume all candidates are time-feasible for the period.
    """
    model_config = ConfigDict(extra="ignore")

    initiative_key: str

    # Primary capacity unit for Phase 5 portfolio optimization
    engineering_tokens: float = Field(..., ge=0)

    # Dimensions used by floors/caps/targets slicing
    # All dimensions optional (not all initiatives have all dimensions)
    country: Optional[str] = None
    segment: Optional[str] = None  # Maps from Initiative.customer_segment
    product: Optional[str] = None  # Maps from Initiative.product_area
    department: Optional[str] = None
    category: Optional[str] = None
    program: Optional[str] = None  # Maps from Initiative.program_key

    # KPI contributions in native units (normalization happens per objective policy)
    kpi_contributions: Dict[str, float] = Field(default_factory=dict)

    # Optional debug/display (not required for solver math)
    title: Optional[str] = None
    active_overall_score: Optional[float] = None


class ConstraintSetPayload(BaseModel):
    """
    Compiled constraint set JSON payload (matches DB structure).
    All governance constraints come from OptimizationConstraintSet, 
    NOT from Initiative-level fields (those have been removed).
    """
    model_config = ConfigDict(extra="ignore")

    # Capacity bounds: {dimension: {dimension_key: value}}
    floors: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    caps: Dict[str, Dict[str, float]] = Field(default_factory=dict)

    # Targets: {dimension: {dimension_key: {kpi_key: {type, value, notes?}}}}
    targets: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = Field(default_factory=dict)

    # Governance constraints
    mandatory_initiatives: List[str] = Field(default_factory=list)
    bundles: List[Dict[str, Any]] = Field(default_factory=list)  # [{bundle_key, members: [...]}]
    exclusions_initiatives: List[str] = Field(default_factory=list)
    exclusions_pairs: List[List[str]] = Field(default_factory=list)  # [[a,b], ...]
    prerequisites: Dict[str, List[str]] = Field(default_factory=dict)  # {dependent: [prereq1, ...]}
    synergy_bonuses: List[List[str]] = Field(default_factory=list)  # [[a,b], ...]

    notes: Optional[str] = None


class RunScope(BaseModel):
    """
    Defines how the candidate pool was selected.
    - selected_only: PM explicitly selected candidates on Candidates sheet 
    - all_candidates: All DB candidates for period (is_optimization_candidate=True and period_key matches)
    """
    model_config = ConfigDict(extra="ignore")

    type: ScopeType
    initiative_keys: Optional[List[str]] = None  # Required when type=selected_only

    @model_validator(mode="after")
    def _validate_scope(self) -> "RunScope":
        """PRODUCTION FIX: Validate scope consistency."""
        if self.type == "selected_only" and not self.initiative_keys:
            raise ValueError("scope.initiative_keys is required when scope.type='selected_only'")
        return self


class OptimizationProblem(BaseModel):
    """
    Complete solver-facing problem object (Phase 5).
    
    This object is persisted to OptimizationRun.inputs_snapshot_json for
    full reproducibility and audit trail.
    """
    model_config = ConfigDict(extra="ignore")

    # Identity / lineage
    scenario_name: str
    constraint_set_name: str
    period_key: Optional[str] = None

    # Scenario config
    capacity_total_tokens: Optional[float] = None
    objective: ObjectiveSpec

    # Candidates (already filtered for deadline feasibility)
    candidates: List[Candidate]

    # Compiled constraint set payload
    constraint_set: ConstraintSetPayload

    # Scope used to build candidates list
    scope: RunScope

    # Debuggable, snapshot-friendly metadata
    # PRODUCTION FIX: Store diagnostic info here (excluded candidates, filter stats, etc.)
    metadata: Dict[str, Any] = Field(default_factory=dict)
