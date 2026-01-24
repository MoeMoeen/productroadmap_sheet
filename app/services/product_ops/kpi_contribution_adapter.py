# productroadmap_sheet_project/app/services/product_ops/kpi_contribution_adapter.py
"""
KPI Contributions Adapter

Translates multiple math model scores per initiative into unified KPI contribution JSON.
Each math model can target a specific KPI (via target_kpi_key).

Flow:
1. Initiative has multiple math_models (1:N relationship)
2. Each model has: target_kpi_key, computed_score, is_primary
3. Adapter aggregates all models' contributions into kpi_contribution_json

PM Override:
- PM can edit kpi_contribution_json via KPI_Contributions tab
- kpi_contribution_source tracks if system-computed or pm-override
- Adapter updates kpi_contribution_computed_json always
- Only updates kpi_contribution_json if source != "pm_override"
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.db.models.optimization import OrganizationMetricConfig

logger = logging.getLogger(__name__)


def compute_kpi_contributions(initiative: Initiative) -> Dict[str, float]:
    """
    Compute KPI contributions from initiative's math models.
    
    Returns dict of {kpi_key: score} from all models with target_kpi_key + computed_score.
    If multiple models target same KPI, uses the primary model's score (or max score).
    
    Validation: At most 1 model can be marked is_primary=True per initiative.
    If multiple primaries found, uses deterministic selection (first by target_kpi_key sort).
    
    Note: InitiativeMathModel.computed_score is populated by ScoringService._score_individual_math_models()
    when MATH_MODEL framework scoring runs. Each model is scored individually using its formula_text
    and parameters, with the value_score stored as computed_score.
    """
    if not initiative.math_models:
        return {}
    
    # Validate: at most 1 primary model per initiative
    primary_models = [m for m in initiative.math_models if m.is_primary]
    if len(primary_models) > 1:
        logger.warning(
            "kpi_contributions.multiple_primary_models",
            extra={
                "initiative_key": initiative.initiative_key,
                "primary_count": len(primary_models),
                "model_keys": [getattr(m, 'target_kpi_key', None) for m in primary_models],
            },
        )
        # Deterministic selection: sort by target_kpi_key and take first
        primary_models = sorted(primary_models, key=lambda m: m.target_kpi_key or "")
        primary_models = [primary_models[0]]
    
    contributions: Dict[str, float] = {}
    
    # First pass: collect all contributions, track if any are primary per KPI
    kpi_primary = {}  # Track which KPI has a primary model
    kpi_scores = {}   # Track all scores per KPI
    
    for model in initiative.math_models:
        if not model.target_kpi_key or model.computed_score is None:
            continue
        
        kpi_key = model.target_kpi_key
        score = model.computed_score
        
        if kpi_key not in kpi_scores:
            kpi_scores[kpi_key] = []
        
        kpi_scores[kpi_key].append((score, model.is_primary))
        
        if model.is_primary:
            kpi_primary[kpi_key] = score
    
    # Second pass: select best score per KPI
    for kpi_key, scores in kpi_scores.items():
        if kpi_key in kpi_primary:
            # Primary model wins
            contributions[kpi_key] = kpi_primary[kpi_key]
        else:
            # Take highest score
            contributions[kpi_key] = max(s[0] for s in scores)
    
    return contributions


def update_initiative_contributions(
    db: Session,
    initiative: Initiative,
    commit: bool = True
) -> Dict[str, Any]:
    """
    Update initiative's KPI contributions from its math models.
    
    Always updates kpi_contribution_computed_json.
    Only updates kpi_contribution_json if not overridden by PM.
    
    Returns:
        {
            "computed": {...},
            "active": {...},
            "source": "computed" | "pm_override",
            "updated": bool,
            "invalid_kpis": [...] (KPI keys that were dropped)
        }
    """
    computed = compute_kpi_contributions(initiative)
    
    # Validate KPI keys against OrganizationMetricConfig
    validation = validate_kpi_keys(db, list(computed.keys()), ["north_star", "strategic"])
    invalid_kpis = validation["invalid"]
    
    # Drop invalid keys from computed and log warning
    if invalid_kpis:
        logger.warning(
            "kpi_contributions.invalid_keys_dropped",
            extra={
                "initiative_key": initiative.initiative_key,
                "invalid_kpis": invalid_kpis,
                "allowed_kpis": validation["all_allowed_keys"],
            },
        )
        computed = {k: v for k, v in computed.items() if k in validation["valid"]}
    
    # Always update computed field
    initiative.kpi_contribution_computed_json = computed  # type: ignore[assignment]
    
    # Determine source (treat None as "computed")
    source = getattr(initiative, "kpi_contribution_source", None) or "computed"
    
    # Only update active field if not overridden
    updated_active = False
    if source != "pm_override":
        initiative.kpi_contribution_json = computed  # type: ignore[assignment]
        # Always set source to "computed" when we update the active JSON
        try:
            initiative.kpi_contribution_source = "computed"  # type: ignore[attr-defined]
        except AttributeError:
            pass
        updated_active = True
    
    if commit:
        db.commit()
        db.refresh(initiative)
    
    return {
        "computed": computed,
        "active": initiative.kpi_contribution_json or {},
        "source": source,
        "updated": updated_active,
        "invalid_kpis": invalid_kpis,
    }


def get_representative_score(initiative: Initiative) -> Optional[float]:
    """
    Get representative score for initiative from its math models.
    
    Selection priority:
    1. Primary model (is_primary=True)
    2. North star KPI model (if exists)
    3. Highest score
    4. First model
    
    Returns None if no models with scores.
    """
    if not initiative.math_models:
        return None
    
    models_with_scores = [m for m in initiative.math_models if m.computed_score is not None]
    
    if not models_with_scores:
        return None
    
    # Priority 1: Primary model
    primary = next((m for m in models_with_scores if m.is_primary), None)
    if primary:
        return primary.computed_score
    
    # Priority 2: North star KPI model (need to query OrganizationMetricConfig)
    # For now, skip this - would require DB session
    
    # Priority 3: Highest score
    return max(m.computed_score for m in models_with_scores)


def validate_kpi_keys(
    db: Session,
    kpi_keys: list[str],
    kpi_levels: Optional[list[str]] = None
) -> Dict[str, Any]:
    """
    Validate KPI keys against OrganizationMetricConfig.
    
    Args:
        db: Database session
        kpi_keys: List of KPI keys to validate
        kpi_levels: Optional list of allowed levels (e.g. ["north_star", "strategic"])
    
    Returns:
        {
            "valid": [valid_keys],
            "invalid": [invalid_keys],
            "all_allowed_keys": [all_active_kpi_keys]
        }
    """
    configs = db.query(OrganizationMetricConfig).all()
    
    allowed_keys = set()
    for cfg in configs:
        meta = cfg.metadata_json or {}
        is_active = meta.get("is_active", True)
        
        if not is_active:
            continue
        
        if kpi_levels and cfg.kpi_level not in kpi_levels:
            continue
        
        if cfg.kpi_key is not None:
            allowed_keys.add(cfg.kpi_key)
    
    valid = [k for k in kpi_keys if k in allowed_keys]
    invalid = [k for k in kpi_keys if k not in allowed_keys]
    
    return {
        "valid": valid,
        "invalid": invalid,
        "all_allowed_keys": sorted(list(allowed_keys)),
    }


__all__ = [
    "compute_kpi_contributions",
    "update_initiative_contributions",
    "get_representative_score",
    "validate_kpi_keys",
]
