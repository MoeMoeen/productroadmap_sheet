# productroadmap_sheet_project/app/services/scoring/engines/wsjf.py

from __future__ import annotations

from app.services.product_ops.scoring.interfaces import ScoringFramework, ScoreInputs, ScoreResult
from app.services.product_ops.scoring.utils import safe_div


class WsjfScoringEngine:
    """WSJF scoring engine.

    WSJF formula: Cost of Delay / Job Size
    Cost of Delay (CoD) = Business Value + Time Criticality + Risk Reduction
    - Each component treated as >=0 numeric.
    - Job Size must be > 0 for meaningful score; else overall=0 with warning.
    """

    framework = ScoringFramework.WSJF

    def compute(self, inputs: ScoreInputs) -> ScoreResult:
        business_value = max(0.0, inputs.business_value or 0.0)
        time_criticality = max(0.0, inputs.time_criticality or 0.0)
        risk_reduction = max(0.0, inputs.risk_reduction or 0.0)
        job_size = max(0.0, inputs.job_size or 0.0)

        cod = business_value + time_criticality + risk_reduction
        overall, warn = safe_div(cod, job_size)
        warnings = []
        if warn:
            warnings.append(f"WSJF: {warn}")

        return ScoreResult(
            value_score=cod,
            effort_score=job_size,
            overall_score=overall,
            components={
                "business_value": business_value,
                "time_criticality": time_criticality,
                "risk_reduction": risk_reduction,
                "cost_of_delay": cod,
                "job_size": job_size,
            },
            warnings=warnings,
        )


__all__ = ["WsjfScoringEngine"]
