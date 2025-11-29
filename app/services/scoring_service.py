# productroadmap_sheet_project/app/services/scoring_service.py

from __future__ import annotations

import logging
from typing import Optional, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeScore
from app.services.scoring import ScoringFramework, ScoreInputs, get_engine

logger = logging.getLogger(__name__)


class ScoringService:
    """Service layer for computing and persisting initiative scores.

    Responsibilities:
    - Map Initiative fields -> ScoreInputs
    - Delegate to pluggable scoring engines
    - Update Initiative current scores
    - Optionally write InitiativeScore history rows
    - Support batch scoring with commit control
    """

    def __init__(self, db: Session):
        self.db = db

    def score_initiative(
        self,
        initiative: Initiative,
        framework: ScoringFramework,
        enable_history: Optional[bool] = None,
    ) -> Optional[InitiativeScore]:
        """Compute and persist scores for a single initiative.

        Args:
            initiative: Initiative ORM instance
            framework: Scoring framework to use
            enable_history: Override global SCORING_ENABLE_HISTORY; if None, use setting

        Returns:
            InitiativeScore instance if history enabled, else None

        Side effects:
            - Updates initiative.value_score, effort_score, overall_score, active_scoring_framework
            - May add InitiativeScore row to session (no commit)
        """
        if enable_history is None:
            enable_history = settings.SCORING_ENABLE_HISTORY

        # Build inputs from Initiative fields
        inputs = self._build_score_inputs(initiative, framework)

        # Compute scores
        engine = get_engine(framework)
        result = engine.compute(inputs)

        # Update Initiative current scores
        initiative.value_score = result.value_score  # type: ignore[assignment]
        initiative.effort_score = result.effort_score  # type: ignore[assignment]
        initiative.overall_score = result.overall_score  # type: ignore[assignment]
        initiative.active_scoring_framework = framework.value  # type: ignore[assignment]
        initiative.updated_source = "scoring"  # type: ignore[assignment]

        # Log warnings
        for warn in result.warnings:
            logger.warning(
                "scoring.warning",
                extra={
                    "initiative_key": initiative.initiative_key,
                    "framework": framework.value,
                    "warning": warn,
                },
            )

        # Optional history row
        history_row: Optional[InitiativeScore] = None
        if enable_history:
            history_row = InitiativeScore(
                initiative_id=initiative.id,
                framework_name=framework.value,
                value_score=result.value_score,
                effort_score=result.effort_score,
                overall_score=result.overall_score,
                inputs_json=inputs.model_dump(),
                components_json=result.components,
                warnings_json=result.warnings,
                llm_suggested=False,
                approved_by_user=False,
            )
            self.db.add(history_row)

        logger.debug(
            "scoring.computed",
            extra={
                "initiative_key": initiative.initiative_key,
                "framework": framework.value,
                "overall_score": result.overall_score,
            },
        )

        return history_row

    def score_all(
        self,
        framework: ScoringFramework,
        commit_every: Optional[int] = None,
        only_missing_scores: bool = True,
    ) -> int:
        """Batch score multiple initiatives.

        Args:
            framework: Scoring framework
            commit_every: Commit every N initiatives; defaults to SCORING_BATCH_COMMIT_EVERY
            only_missing_scores: If True, skip initiatives already scored with this framework

        Returns:
            Count of initiatives scored
        """
        batch_size = commit_every or settings.SCORING_BATCH_COMMIT_EVERY

        # Build query
        stmt = select(Initiative).order_by(Initiative.id)
        if only_missing_scores:
            stmt = stmt.where(
                (Initiative.overall_score.is_(None))
                | (Initiative.active_scoring_framework != framework.value)
            )

        initiatives = self.db.execute(stmt).scalars().all()
        total = len(initiatives)
        logger.info("scoring.batch_start", extra={"framework": framework.value, "total": total})

        scored = 0
        for idx, initiative in enumerate(initiatives, start=1):
            try:
                self.score_initiative(initiative, framework, enable_history=settings.SCORING_ENABLE_HISTORY)
                scored += 1
            except Exception:
                logger.exception(
                    "scoring.error",
                    extra={
                        "initiative_key": getattr(initiative, "initiative_key", None),
                        "framework": framework.value,
                    },
                )
                # Continue processing; don't let one bad initiative stop the batch

            if batch_size and (idx % batch_size == 0):
                try:
                    self.db.commit()
                    logger.info(
                        "scoring.batch_commit",
                        extra={"count": idx, "framework": framework.value},
                    )
                except Exception:
                    self.db.rollback()
                    logger.exception("scoring.batch_commit_failed")

        # Final commit
        try:
            self.db.commit()
            logger.info("scoring.batch_done", extra={"scored": scored, "framework": framework.value})
        except Exception:
            self.db.rollback()
            logger.exception("scoring.final_commit_failed")

        return scored

    def _build_score_inputs(self, initiative: Initiative, framework: ScoringFramework) -> ScoreInputs:
        """Map Initiative fields to ScoreInputs based on framework requirements.

        This is the normalization layer that bridges domain model to engine contract.
        """
        if framework == ScoringFramework.RICE:
            return self._build_rice_inputs(initiative)
        elif framework == ScoringFramework.WSJF:
            return self._build_wsjf_inputs(initiative)
        else:
            raise ValueError(f"Unsupported framework: {framework}")

    def _build_rice_inputs(self, initiative: Initiative) -> ScoreInputs:
        """Build RICE inputs from Initiative.

        RICE needs: reach, impact, confidence, effort
        """
        # Reach: could come from traffic estimates, user base, etc.
        impact_expected_val = cast(Optional[float], initiative.impact_expected)
        reach = float(impact_expected_val) if impact_expected_val is not None else 1.0

        # Impact: scale 0-3 (minimal/low/medium/high)
        impact = float(impact_expected_val) if impact_expected_val is not None else 1.0

        # Confidence: 0-1 (we might not have explicit confidence; default to medium)
        confidence = 0.8  # default confidence if not tracked

        # Effort: engineering days
        eng_days_val = cast(Optional[float], initiative.effort_engineering_days)
        effort = float(eng_days_val) if eng_days_val is not None else 1.0

        return ScoreInputs(
            reach=reach,
            impact=impact,
            confidence=confidence,
            effort=effort,
        )

    def _build_wsjf_inputs(self, initiative: Initiative) -> ScoreInputs:
        """Build WSJF inputs from Initiative.

        WSJF needs: business_value, time_criticality, risk_reduction, job_size
        """
        # Business value: might map from impact or strategic priority
        impact_expected_val = cast(Optional[float], initiative.impact_expected)
        impact_val = float(impact_expected_val) if impact_expected_val is not None else 0.0
        
        priority_coef_val = cast(Optional[float], initiative.strategic_priority_coefficient)
        priority_coef = float(priority_coef_val) if priority_coef_val is not None else 1.0
        
        business_value = impact_val * priority_coef

        # Time criticality: could derive from deadline urgency or time_sensitivity field
        time_sens_val = cast(Optional[str], initiative.time_sensitivity)
        time_criticality = 5.0 if time_sens_val else 3.0  # simple heuristic

        # Risk reduction: if we track risk level, map it numerically
        risk_map = {"low": 1.0, "medium": 3.0, "high": 5.0}
        risk_level_val = cast(Optional[str], initiative.risk_level)
        risk_level_str = str(risk_level_val).lower() if risk_level_val else ""
        risk_reduction = risk_map.get(risk_level_str, 2.0)

        # Job size: engineering effort
        eng_days_val = cast(Optional[float], initiative.effort_engineering_days)
        job_size = float(eng_days_val) if eng_days_val is not None else 1.0

        return ScoreInputs(
            business_value=business_value,
            time_criticality=time_criticality,
            risk_reduction=risk_reduction,
            job_size=job_size,
        )


__all__ = ["ScoringService"]
