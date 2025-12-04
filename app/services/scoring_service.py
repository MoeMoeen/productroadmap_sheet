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
    - Update Initiative current scores in DB
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

        # Update Initiative current scores (active framework)
        initiative.value_score = result.value_score  # type: ignore[assignment]
        initiative.effort_score = result.effort_score  # type: ignore[assignment]
        initiative.overall_score = result.overall_score  # type: ignore[assignment]
        initiative.active_scoring_framework = framework.value  # type: ignore[assignment]
        initiative.updated_source = "scoring"  # type: ignore[assignment]

        # Also store per-framework scores (for multi-framework comparison and Product Ops sheet)
        if framework == ScoringFramework.RICE:
            initiative.rice_value_score = result.value_score  # type: ignore[assignment]
            initiative.rice_effort_score = result.effort_score  # type: ignore[assignment]
            initiative.rice_overall_score = result.overall_score  # type: ignore[assignment]
        elif framework == ScoringFramework.WSJF:
            initiative.wsjf_value_score = result.value_score  # type: ignore[assignment]
            initiative.wsjf_effort_score = result.effort_score  # type: ignore[assignment]
            initiative.wsjf_overall_score = result.overall_score  # type: ignore[assignment]

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

    def score_initiative_all_frameworks(
        self,
        initiative: Initiative,
        enable_history: Optional[bool] = None,
    ) -> None:
        """Score an initiative using all available frameworks.

        This computes RICE and WSJF scores separately, storing each in its own fields
        (rice_value_score, rice_effort_score, rice_overall_score, etc.). Useful for:
        - Product Ops sheet to show all frameworks side-by-side for comparison
        - Multi-framework dashboards
        - Allowing PMs to see both scores regardless of active_scoring_framework

        Side effects:
            - Updates all framework-specific score columns on Initiative
            - Does NOT change active_scoring_framework or active score fields (value_score, effort_score, overall_score)
            - Call score_initiative() separately if you want to set the active framework
        """
        if enable_history is None:
            enable_history = settings.SCORING_ENABLE_HISTORY

        for framework in ScoringFramework:
            try:
                self.score_initiative(initiative, framework, enable_history=enable_history)
            except Exception:
                logger.exception(
                    "scoring.multi_framework_error",
                    extra={
                        "initiative_key": getattr(initiative, "initiative_key", None),
                        "framework": framework.value,
                    },
                )
                # Continue with other frameworks; don't let one fail the whole pass

    def score_all(
        self,
        framework: Optional[ScoringFramework],
        commit_every: Optional[int] = None,
        only_missing_scores: bool = True,
    ) -> int:
        """Batch score multiple initiatives.

        Args:
            framework: Scoring framework override for all initiatives. If None, use per-initiative selection.
            commit_every: Commit every N initiatives; defaults to SCORING_BATCH_COMMIT_EVERY
            only_missing_scores: If True, skip initiatives already scored with this framework

        Returns:
            Count of initiatives scored
        """
        batch_size = commit_every or settings.SCORING_BATCH_COMMIT_EVERY

        # Build query
        stmt = select(Initiative).order_by(Initiative.id)
        if framework is not None:
            if only_missing_scores:
                stmt = stmt.where(
                    (Initiative.overall_score.is_(None))
                    | (Initiative.active_scoring_framework != framework.value)
                )
        else:
            # Per-initiative mode: if only_missing, only pick those lacking an overall score.
            if only_missing_scores:
                stmt = stmt.where(Initiative.overall_score.is_(None))

        initiatives = self.db.execute(stmt).scalars().all()
        total = len(initiatives)
        logger.info(
            "scoring.batch_start",
            extra={"framework": (framework.value if framework else "AUTO"), "total": total},
        )

        scored = 0
        for idx, initiative in enumerate(initiatives, start=1):
            try:
                chosen = self._resolve_framework_for_initiative(initiative, framework)
                if chosen is None:
                    logger.warning(
                        "scoring.skip_no_framework",
                        extra={
                            "initiative_key": getattr(initiative, "initiative_key", None),
                        },
                    )
                    continue

                self.score_initiative(
                    initiative,
                    chosen,
                    enable_history=settings.SCORING_ENABLE_HISTORY,
                )
                scored += 1
            except Exception:
                logger.exception(
                    "scoring.error",
                    extra={
                        "initiative_key": getattr(initiative, "initiative_key", None),
                        "framework": (framework.value if framework else "AUTO"),
                    },
                )
                # Continue processing; don't let one bad initiative stop the batch

            if batch_size and (idx % batch_size == 0):
                try:
                    self.db.commit()
                    logger.info(
                        "scoring.batch_commit",
                        extra={"count": idx, "framework": (framework.value if framework else "AUTO")},
                    )
                except Exception:
                    self.db.rollback()
                    logger.exception("scoring.batch_commit_failed")

        # Final commit
        try:
            self.db.commit()
            logger.info(
                "scoring.batch_done",
                extra={"scored": scored, "framework": (framework.value if framework else "AUTO")},
            )
        except Exception:
            self.db.rollback()
            logger.exception("scoring.final_commit_failed")

        return scored

    def score_all_frameworks(
        self,
        commit_every: Optional[int] = None,
    ) -> int:
        """Score all initiatives using ALL frameworks (both RICE and WSJF).

        This is typically called by Flow 3 after syncing Product Ops inputs:
        - Reads all initiatives from DB
        - For each initiative, computes RICE score and stores in rice_* fields
        - For each initiative, computes WSJF score and stores in wsjf_* fields
        - Does NOT change active_scoring_framework or active score fields
        - Allows Product Ops sheet to display all framework scores for comparison

        Returns:
            Count of initiatives processed (not necessarily scored if errors occurred)
        """
        batch_size = commit_every or settings.SCORING_BATCH_COMMIT_EVERY

        stmt = select(Initiative).order_by(Initiative.id)
        initiatives = self.db.execute(stmt).scalars().all()
        total = len(initiatives)
        logger.info(
            "scoring.batch_all_frameworks_start",
            extra={"total": total},
        )

        processed = 0
        for idx, initiative in enumerate(initiatives, start=1):
            try:
                self.score_initiative_all_frameworks(
                    initiative,
                    enable_history=settings.SCORING_ENABLE_HISTORY,
                )
                processed += 1
            except Exception:
                logger.exception(
                    "scoring.all_frameworks_error",
                    extra={
                        "initiative_key": getattr(initiative, "initiative_key", None),
                    },
                )
                # Continue processing

            if batch_size and (idx % batch_size == 0):
                try:
                    self.db.commit()
                    logger.info(
                        "scoring.batch_all_frameworks_commit",
                        extra={"count": idx},
                    )
                except Exception:
                    self.db.rollback()
                    logger.exception("scoring.batch_all_frameworks_commit_failed")

        # Final commit
        try:
            self.db.commit()
            logger.info(
                "scoring.batch_all_frameworks_done",
                extra={"processed": processed},
            )
        except Exception:
            self.db.rollback()
            logger.exception("scoring.batch_all_frameworks_final_commit_failed")

        return processed

    def _resolve_framework_for_initiative(
        self,
        initiative: Initiative,
        explicit_override: Optional[ScoringFramework],
    ) -> Optional[ScoringFramework]:
        """Pick framework for an initiative based on override, initiative field, or settings default.

        Returns None if no valid framework can be determined.
        """
        if explicit_override is not None:
            return explicit_override

        raw = getattr(initiative, "active_scoring_framework", None)
        if isinstance(raw, str) and raw:
            try:
                return ScoringFramework(raw.upper())
            except ValueError:
                pass

        default_raw = settings.SCORING_DEFAULT_FRAMEWORK
        if isinstance(default_raw, str) and default_raw:
            try:
                return ScoringFramework(default_raw.upper())
            except ValueError:
                return None
        return None

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
        """Build RICE inputs from Initiative using framework-prefixed fields.

        RICE needs: reach, impact, confidence, effort
        """
        # Use new framework-prefixed fields
        reach_val = cast(Optional[float], getattr(initiative, "rice_reach", None))
        reach = float(reach_val) if reach_val is not None else settings.SCORING_DEFAULT_RICE_REACH

        impact_val = cast(Optional[float], getattr(initiative, "rice_impact", None))
        impact = float(impact_val) if impact_val is not None else settings.SCORING_DEFAULT_RICE_IMPACT

        confidence_val = cast(Optional[float], getattr(initiative, "rice_confidence", None))
        confidence = float(confidence_val) if confidence_val is not None else settings.SCORING_DEFAULT_RICE_CONFIDENCE

        effort_val = cast(Optional[float], getattr(initiative, "rice_effort", None))
        effort = float(effort_val) if effort_val is not None else settings.SCORING_DEFAULT_RICE_EFFORT

        return ScoreInputs(
            reach=reach,
            impact=impact,
            confidence=confidence,
            effort=effort,
        )

    def _build_wsjf_inputs(self, initiative: Initiative) -> ScoreInputs:
        """Build WSJF inputs from Initiative using framework-prefixed fields.

        WSJF needs: business_value, time_criticality, risk_reduction, job_size
        """
        # Use new framework-prefixed fields directly
        business_value_val = cast(Optional[float], getattr(initiative, "wsjf_business_value", None))
        business_value = float(business_value_val) if business_value_val is not None else settings.SCORING_DEFAULT_WSJF_BUSINESS_VALUE

        time_criticality_val = cast(Optional[float], getattr(initiative, "wsjf_time_criticality", None))
        time_criticality = float(time_criticality_val) if time_criticality_val is not None else settings.SCORING_DEFAULT_WSJF_TIME_CRITICALITY

        risk_reduction_val = cast(Optional[float], getattr(initiative, "wsjf_risk_reduction", None))
        risk_reduction = float(risk_reduction_val) if risk_reduction_val is not None else settings.SCORING_DEFAULT_WSJF_RISK_REDUCTION

        job_size_val = cast(Optional[float], getattr(initiative, "wsjf_job_size", None))
        job_size = float(job_size_val) if job_size_val is not None else settings.SCORING_DEFAULT_WSJF_JOB_SIZE

        return ScoreInputs(
            business_value=business_value,
            time_criticality=time_criticality,
            risk_reduction=risk_reduction,
            job_size=job_size,
        )


__all__ = ["ScoringService"]
