# productroadmap_sheet_project/app/services/scoring/interfaces.py

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field


class ScoringFramework(str, Enum):
    """Supported scoring framework identifiers."""
    RICE = "RICE"
    WSJF = "WSJF"
    # CUSTOM = "CUSTOM"  # reserved for future custom / AI frameworks


class ScoreInputs(BaseModel):
    """Normalized numeric inputs for scoring engines.

    A single container for all potential framework inputs; engines only use
    the subset they require. All normalization (type coercion, defaults) will
    be performed by the higher-level ScoringService in a later phase.
    """
    # RICE-style inputs
    reach: Optional[float] = None
    impact: Optional[float] = None  # expected impact multiplier (e.g. 0-3 scale)
    confidence: Optional[float] = None  # 0-1
    effort: Optional[float] = None

    # WSJF-style inputs
    business_value: Optional[float] = None
    time_criticality: Optional[float] = None
    risk_reduction: Optional[float] = None
    job_size: Optional[float] = None

    # Generic extension slot (custom frameworks / AI derived components)
    extra: Dict[str, Any] = Field(default_factory=dict)


class ScoreResult(BaseModel):
    """Result returned by a scoring engine.

    value_score: expresses benefit / desirability (framework-specific)
    effort_score: expresses cost / size (framework-specific)
    overall_score: the primary prioritization metric (sortable)
    components: raw components used to derive scores (for audit / transparency)
    warnings: non-fatal computation notes (e.g., division by zero guarded)
    """
    value_score: Optional[float] = None
    effort_score: Optional[float] = None
    overall_score: Optional[float] = None

    components: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class ScoringEngine(Protocol):
    """Protocol that all scoring engines must satisfy."""

    framework: ScoringFramework  # identifier of the engine

    def compute(self, inputs: ScoreInputs) -> ScoreResult:  # pragma: no cover - interface only
        ...



__all__ = [
    "ScoringFramework",
    "ScoreInputs",
    "ScoreResult",
    "ScoringEngine",
]
