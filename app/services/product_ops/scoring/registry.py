# productroadmap_sheet_project/app/services/scoring/registry.py
"""
Registry for scoring frameworks and their engines. This module defines available scoring frameworks,
their required input fields, and provides access to their scoring engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.services.product_ops.scoring.interfaces import ScoringFramework, ScoringEngine
from app.services.product_ops.scoring.engines import MathModelScoringEngine, RiceScoringEngine, WsjfScoringEngine


@dataclass(frozen=True)
class FrameworkInfo:
    name: ScoringFramework
    label: str
    description: str
    required_fields: List[str]
    engine: ScoringEngine


SCORING_FRAMEWORKS: Dict[ScoringFramework, FrameworkInfo] = {
    ScoringFramework.RICE: FrameworkInfo(
        name=ScoringFramework.RICE,
        label="RICE",
        description="Reach * Impact * Confidence / Effort",
        required_fields=["reach", "impact", "confidence", "effort"],
        engine=RiceScoringEngine(),
    ),
    ScoringFramework.WSJF: FrameworkInfo(
        name=ScoringFramework.WSJF,
        label="WSJF",
        description="(Business Value + Time Criticality + Risk Reduction) / Job Size",
        required_fields=["business_value", "time_criticality", "risk_reduction", "job_size"],
        engine=WsjfScoringEngine(),
    ),
    ScoringFramework.MATH_MODEL: FrameworkInfo(
        name=ScoringFramework.MATH_MODEL,
        label="MATH_MODEL",
        description="Per-initiative math model evaluated via safe_eval",
        required_fields=[],
        engine=MathModelScoringEngine(),
    ),
}


def get_engine(framework: ScoringFramework) -> ScoringEngine:
    info = SCORING_FRAMEWORKS.get(framework)
    if not info:
        raise ValueError(f"Unknown scoring framework: {framework}")
    return info.engine


__all__ = [
    "FrameworkInfo",
    "SCORING_FRAMEWORKS",
    "get_engine",
]
