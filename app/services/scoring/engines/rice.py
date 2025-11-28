# productroadmap_sheet_project/app/services/scoring/engines/rice.py

from __future__ import annotations

from app.services.scoring.interfaces import ScoringFramework, ScoreInputs, ScoreResult
from app.services.scoring.utils import safe_div, clamp


class RiceScoringEngine:
    """RICE scoring engine.

    RICE formula: (Reach * Impact * Confidence) / Effort
    - Reach: numeric (>=0)
    - Impact: clamped to [0, 3] (example convention)
    - Confidence: clamped to [0, 1]
    - Effort: numeric (>=0)
    """

    framework = ScoringFramework.RICE

    def compute(self, inputs: ScoreInputs) -> ScoreResult:
        reach = max(0.0, inputs.reach or 0.0)
        impact = clamp(inputs.impact, 0.0, 3.0)
        confidence = clamp(inputs.confidence, 0.0, 1.0)
        effort = max(0.0, inputs.effort or 0.0)

        value = reach * impact * confidence
        overall, warn = safe_div(value, effort)
        warnings = []
        if warn:
            warnings.append(f"RICE: {warn}")

        return ScoreResult(
            value_score=value,
            effort_score=effort,
            overall_score=overall,
            components={
                "reach": reach,
                "impact": impact,
                "confidence": confidence,
                "effort": effort,
                "value_raw": value,
            },
            warnings=warnings,
        )


__all__ = ["RiceScoringEngine"]
