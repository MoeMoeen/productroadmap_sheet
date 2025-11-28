# productroadmap_sheet_project/app/services/scoring/registry.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.services.scoring.interfaces import ScoringFramework, ScoringEngine
from app.services.scoring.engines import RiceScoringEngine, WsjfScoringEngine


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
