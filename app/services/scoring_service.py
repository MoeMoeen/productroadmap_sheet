# productroadmap_sheet_project/app/services/scoring_service.py

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Dict, Optional, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeParam
from app.db.models.scoring import InitiativeScore
from app.services.scoring import ScoringFramework, ScoreInputs, get_engine
from app.utils.provenance import Provenance, token

logger = logging.getLogger("app.services.scoring")


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
        activate: bool = False,
    ) -> Optional[InitiativeScore]:
        """Compute and persist scores for a single initiative.

        Args:
            initiative: Initiative ORM instance
            framework: Scoring framework to use
            enable_history: Override global SCORING_ENABLE_HISTORY; if None, use setting
            activate: If True, also update active fields (value_score/effort_score/overall_score)
                      and active_scoring_framework. If False, only per-framework fields are updated.

        Returns:
            InitiativeScore instance if history enabled, else None

        Side effects:
            - Always updates per-framework score fields (rice_*, wsjf_*, math_*) for the selected framework
            - If activate=True, also updates active fields and active_scoring_framework
            - May add InitiativeScore row to session (no commit)
        """
        if enable_history is None:
            enable_history = settings.SCORING_ENABLE_HISTORY

        # Build inputs from Initiative fields
        inputs = self._build_score_inputs(initiative, framework)

        # Compute scores
        engine = get_engine(framework)
        result = engine.compute(inputs)

        # Always mark source when we run scoring
        prov = Provenance.FLOW2_ACTIVATE if activate else Provenance.FLOW3_COMPUTE_ALL_FRAMEWORKS
        now = datetime.now(timezone.utc)
        initiative.updated_source = token(prov)  # type: ignore[assignment]
        initiative.scoring_updated_source = token(prov)  # type: ignore[assignment]
        initiative.scoring_updated_at = now  # type: ignore[assignment]

        # Also store per-framework scores (for multi-framework comparison and Product Ops sheet)
        if framework == ScoringFramework.RICE:
            initiative.rice_value_score = result.value_score  # type: ignore[assignment]
            initiative.rice_effort_score = result.effort_score  # type: ignore[assignment]
            initiative.rice_overall_score = result.overall_score  # type: ignore[assignment]
        elif framework == ScoringFramework.WSJF:
            initiative.wsjf_value_score = result.value_score  # type: ignore[assignment]
            initiative.wsjf_effort_score = result.effort_score  # type: ignore[assignment]
            initiative.wsjf_overall_score = result.overall_score  # type: ignore[assignment]
        elif framework == ScoringFramework.MATH_MODEL:
            initiative.math_value_score = result.value_score  # type: ignore[assignment]
            initiative.math_effort_score = result.effort_score  # type: ignore[assignment]
            initiative.math_overall_score = result.overall_score  # type: ignore[assignment]

        # If activating, update active fields and provenance flags
        if activate:
            initiative.value_score = result.value_score  # type: ignore[assignment]
            initiative.effort_score = result.effort_score  # type: ignore[assignment]
            initiative.overall_score = result.overall_score  # type: ignore[assignment]
            initiative.active_scoring_framework = framework.value  # type: ignore[assignment]

            if framework == ScoringFramework.MATH_MODEL:
                initiative.score_llm_suggested = bool(inputs.extra.get("math_model_llm_suggested", False))  # type: ignore[assignment]
                initiative.score_approved_by_user = bool(inputs.extra.get("math_model_approved", False))  # type: ignore[assignment]

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

        # Ensure DB state reflects attribute updates for callers that refresh without commit
        try:
            self.db.flush()
        except Exception:
            logger.debug("scoring.flush_failed")

        # Optional history row
        history_row: Optional[InitiativeScore] = None
        if enable_history:
            llm_suggested = False
            approved_by_user = False
            if framework == ScoringFramework.MATH_MODEL:
                llm_suggested = bool(inputs.extra.get("math_model_llm_suggested", False))
                approved_by_user = bool(inputs.extra.get("math_model_approved", False))

            history_row = InitiativeScore(
                initiative_id=initiative.id,
                framework_name=framework.value,
                value_score=result.value_score,
                effort_score=result.effort_score,
                overall_score=result.overall_score,
                inputs_json=inputs.model_dump(),
                components_json=result.components,
                warnings_json=result.warnings,
                llm_suggested=llm_suggested,
                approved_by_user=approved_by_user,
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

    def _compute_framework_scores_only(
        self,
        initiative: Initiative,
        framework: ScoringFramework,
        enable_history: bool,
    ) -> Optional[InitiativeScore]:
        """Compute per-framework scores without touching active fields.

        This is used by Flow 3 to populate the per-framework score columns
        (rice_* and wsjf_*). It intentionally avoids mutating the active
        scoring fields so it cannot override the framework chosen elsewhere
        (e.g., Product Ops decision or Flow 2 run).
        """

        inputs = self._build_score_inputs(initiative, framework)
        engine = get_engine(framework)
        result = engine.compute(inputs)

        now = datetime.now(timezone.utc)
        initiative.updated_source = token(Provenance.FLOW3_COMPUTE_ALL_FRAMEWORKS)  # type: ignore[assignment]
        initiative.scoring_updated_source = token(Provenance.FLOW3_COMPUTE_ALL_FRAMEWORKS)  # type: ignore[assignment]
        initiative.scoring_updated_at = now  # type: ignore[assignment]

        if framework == ScoringFramework.RICE:
            initiative.rice_value_score = result.value_score  # type: ignore[assignment]
            initiative.rice_effort_score = result.effort_score  # type: ignore[assignment]
            initiative.rice_overall_score = result.overall_score  # type: ignore[assignment]
        elif framework == ScoringFramework.WSJF:
            initiative.wsjf_value_score = result.value_score  # type: ignore[assignment]
            initiative.wsjf_effort_score = result.effort_score  # type: ignore[assignment]
            initiative.wsjf_overall_score = result.overall_score  # type: ignore[assignment]
        elif framework == ScoringFramework.MATH_MODEL:
            initiative.math_value_score = result.value_score  # type: ignore[assignment]
            initiative.math_effort_score = result.effort_score  # type: ignore[assignment]
            initiative.math_overall_score = result.overall_score  # type: ignore[assignment]
            # Store warnings for ProductOps sheet visibility
            initiative.math_warnings = "; ".join(result.warnings) if result.warnings else None  # type: ignore[assignment]

        for warn in result.warnings:
            logger.warning(
                "scoring.warning",
                extra={
                    "initiative_key": initiative.initiative_key,
                    "framework": framework.value,
                    "warning": warn,
                },
            )

        # Ensure DB state reflects attribute updates for callers that refresh without commit
        try:
            self.db.flush()
        except Exception:
            logger.debug("scoring.flush_failed_per_framework")

        history_row: Optional[InitiativeScore] = None
        if enable_history:
            llm_suggested = False
            approved_by_user = False
            if framework == ScoringFramework.MATH_MODEL:
                llm_suggested = bool(inputs.extra.get("math_model_llm_suggested", False))
                approved_by_user = bool(inputs.extra.get("math_model_approved", False))

            history_row = InitiativeScore(
                initiative_id=initiative.id,
                framework_name=framework.value,
                value_score=result.value_score,
                effort_score=result.effort_score,
                overall_score=result.overall_score,
                inputs_json=inputs.model_dump(),
                components_json=result.components,
                warnings_json=result.warnings,
                llm_suggested=llm_suggested,
                approved_by_user=approved_by_user,
            )
            self.db.add(history_row)

        logger.debug(
            "scoring.computed_per_framework",
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

        This computes RICE, WSJF, and Math Model scores separately, storing each in its
        own fields (rice_*, wsjf_*, math_*). Useful for:
        - Product Ops sheet (the scoring tab) to show all frameworks side-by-side for comparison
        - Multi-framework dashboards
        - Allowing PMs to see all scores regardless of active_scoring_framework

        Side effects:
            - Updates all framework-specific score columns on Initiative
            - Does NOT change active_scoring_framework or active score fields (value_score, effort_score, overall_score)
            - Call score_initiative() separately if you want to set the active framework
        """
        if enable_history is None:
            enable_history = settings.SCORING_ENABLE_HISTORY

        for framework in ScoringFramework:
            try:
                self._compute_framework_scores_only(
                    initiative,
                    framework,
                    enable_history=enable_history,
                )
            except Exception:
                logger.exception(
                    "scoring.multi_framework_error",
                    extra={
                        "initiative_key": getattr(initiative, "initiative_key", None),
                        "framework": framework.value,
                    },
                )
                # Continue with other frameworks; don't let one fail the whole pass

    def activate_all(
        self,
        framework: Optional[ScoringFramework] = None,
        commit_every: Optional[int] = None,
        only_missing_active: bool = True,
    ) -> int:
        """Activate frameworks for multiple initiatives (Flow 2).

        Does NOT compute scores. Assumes per-framework scores already exist (from Flow 3).
        Copies the chosen framework's scores into active fields (value_score, effort_score, overall_score).

        Args:
            framework: Force all initiatives to use this framework. If None, use per-initiative active_scoring_framework.
            commit_every: Commit every N initiatives; defaults to SCORING_BATCH_COMMIT_EVERY
            only_missing_active: If True, skip initiatives that already have active scores set

        Returns:
            Count of initiatives activated
        """
        batch_size = commit_every or settings.SCORING_BATCH_COMMIT_EVERY

        # Build query
        stmt = select(Initiative).order_by(Initiative.id)
        if framework is not None:
            if only_missing_active:
                stmt = stmt.where(
                    (Initiative.overall_score.is_(None))
                    | (Initiative.active_scoring_framework != framework.value)
                )
        else:
            # Per-initiative mode: if only_missing, only pick those lacking an overall score.
            if only_missing_active:
                stmt = stmt.where(Initiative.overall_score.is_(None))

        initiatives = self.db.execute(stmt).scalars().all()
        total = len(initiatives)
        logger.info(
            "flow2.activate_batch_start",
            extra={"framework": (framework.value if framework else "AUTO"), "total": total},
        )

        activated = 0
        for idx, initiative in enumerate(initiatives, start=1):
            try:
                chosen = self._resolve_framework_for_initiative(initiative, framework)
                if chosen is None:
                    logger.warning(
                        "flow2.skip_no_framework",
                        extra={
                            "initiative_key": getattr(initiative, "initiative_key", None),
                        },
                    )
                    continue

                # Flow 2 activation: copy per-framework scores to active fields
                # Per-framework scores were already computed by Flow 3
                self.activate_initiative_framework(
                    initiative,
                    chosen,
                    enable_history=settings.SCORING_ENABLE_HISTORY,
                )
                activated += 1
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
                        "flow2.activate_batch_commit",
                        extra={"count": idx, "framework": (framework.value if framework else "AUTO")},
                    )
                except Exception:
                    self.db.rollback()
                    logger.exception("flow2.activate_batch_commit_failed")

        # Final commit
        try:
            self.db.commit()
            logger.info(
                "flow2.activate_batch_done",
                extra={"activated": activated, "framework": (framework.value if framework else "AUTO")},
            )
        except Exception:
            self.db.rollback()
            logger.exception("flow2.activate_final_commit_failed")

        return activated

    def compute_all_frameworks(
        self,
        commit_every: Optional[int] = None,
    ) -> int:
        """Compute scores for all frameworks (Flow 3 Phase 1).

        For each initiative in the database:
        - Computes RICE score and stores in rice_* fields
        - Computes WSJF score and stores in wsjf_* fields
        - Computes Math Model score and stores in math_* fields

        Does NOT change active_scoring_framework or active score fields. PM chooses active framework
        in ProductOps sheet; Flow 2 activates them afterward.

        Allows Product Ops sheet (the scoring tab) to display all framework scores for comparison.

        Returns:
            Count of initiatives processed (not necessarily scored if errors occurred)
        """
        batch_size = commit_every or settings.SCORING_BATCH_COMMIT_EVERY

        stmt = select(Initiative).order_by(Initiative.id)
        initiatives = self.db.execute(stmt).scalars().all()
        total = len(initiatives)
        logger.info(
            "flow3.compute_all_frameworks_start",
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
                        "flow3.compute_all_frameworks_commit",
                        extra={"count": idx},
                    )
                except Exception:
                    self.db.rollback()
                    logger.exception("flow3.compute_all_frameworks_commit_failed")

        # Final commit
        try:
            self.db.commit()
            logger.info(
                "flow3.compute_all_frameworks_done",
                extra={"processed": processed},
            )
        except Exception:
            self.db.rollback()
            logger.exception("flow3.compute_all_frameworks_final_commit_failed")

        return processed

    def compute_for_initiatives(
        self,
        initiative_keys: list[str],
        commit_every: Optional[int] = None,
    ) -> int:
        """Compute scores for all frameworks for selected initiatives only.

        Mirrors compute_all_frameworks but filters the DB query to the provided keys.
        Does not change active fields; only per-framework scores are updated.
        """
        if not initiative_keys:
            return 0
        batch_size = commit_every or settings.SCORING_BATCH_COMMIT_EVERY

        stmt = select(Initiative).where(Initiative.initiative_key.in_(initiative_keys)).order_by(Initiative.id)
        initiatives = self.db.execute(stmt).scalars().all()
        total = len(initiatives)
        logger.info(
            "flow3.compute_selected_start",
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
                    "scoring.selected_all_frameworks_error",
                    extra={
                        "initiative_key": getattr(initiative, "initiative_key", None),
                    },
                )
                # Continue processing

            if batch_size and (idx % batch_size == 0):
                try:
                    self.db.commit()
                    logger.info(
                        "flow3.compute_selected_commit",
                        extra={"count": idx},
                    )
                except Exception:
                    self.db.rollback()
                    logger.exception("flow3.compute_selected_commit_failed")

        # Final commit
        try:
            self.db.commit()
            logger.info(
                "flow3.compute_selected_done",
                extra={"processed": processed},
            )
        except Exception:
            self.db.rollback()
            logger.exception("flow3.compute_selected_final_commit_failed")

        return processed

    def activate_initiative_framework(
        self,
        initiative: Initiative,
        framework: ScoringFramework,
        enable_history: Optional[bool] = None,
    ) -> Optional[InitiativeScore]:
        """Activate a framework for an initiative by copying per-framework scores.

        This does NOT recompute scores unless the selected framework's per-framework
        scores are missing. If missing, it computes them first (without changing
        active fields) and then copies into active fields.

        Side effects:
        - Sets `active_scoring_framework` to the selected framework
        - Copies per-framework scores into `value_score`, `effort_score`, `overall_score`
        - Updates provenance flags for Math Model based on model properties
        - May add a history row ONLY if a compute was required and history enabled

        Returns:
        - InitiativeScore history row if a compute was performed and history was enabled; otherwise None
        """
        if enable_history is None:
            enable_history = settings.SCORING_ENABLE_HISTORY

        # Ensure per-framework scores exist; compute if missing
        need_compute = False
        if framework == ScoringFramework.RICE:
            need_compute = (
                getattr(initiative, "rice_value_score", None) is None
                or getattr(initiative, "rice_effort_score", None) is None
                or getattr(initiative, "rice_overall_score", None) is None
            )
        elif framework == ScoringFramework.WSJF:
            need_compute = (
                getattr(initiative, "wsjf_value_score", None) is None
                or getattr(initiative, "wsjf_effort_score", None) is None
                or getattr(initiative, "wsjf_overall_score", None) is None
            )
        elif framework == ScoringFramework.MATH_MODEL:
            need_compute = (
                getattr(initiative, "math_value_score", None) is None
                or getattr(initiative, "math_effort_score", None) is None
                or getattr(initiative, "math_overall_score", None) is None
            )
        else:
            raise ValueError(f"Unsupported framework: {framework}")

        history_row: Optional[InitiativeScore] = None
        if need_compute:
            history_row = self._compute_framework_scores_only(
                initiative,
                framework,
                enable_history=bool(enable_history),
            )

        # Copy per-framework into active fields
        if framework == ScoringFramework.RICE:
            initiative.value_score = getattr(initiative, "rice_value_score", None)  # type: ignore[assignment]
            initiative.effort_score = getattr(initiative, "rice_effort_score", None)  # type: ignore[assignment]
            initiative.overall_score = getattr(initiative, "rice_overall_score", None)  # type: ignore[assignment]
            initiative.score_llm_suggested = False  # type: ignore[assignment]
            initiative.score_approved_by_user = False  # type: ignore[assignment]
        elif framework == ScoringFramework.WSJF:
            initiative.value_score = getattr(initiative, "wsjf_value_score", None)  # type: ignore[assignment]
            initiative.effort_score = getattr(initiative, "wsjf_effort_score", None)  # type: ignore[assignment]
            initiative.overall_score = getattr(initiative, "wsjf_overall_score", None)  # type: ignore[assignment]
            initiative.score_llm_suggested = False  # type: ignore[assignment]
            initiative.score_approved_by_user = False  # type: ignore[assignment]
        elif framework == ScoringFramework.MATH_MODEL:
            initiative.value_score = getattr(initiative, "math_value_score", None)  # type: ignore[assignment]
            initiative.effort_score = getattr(initiative, "math_effort_score", None)  # type: ignore[assignment]
            initiative.overall_score = getattr(initiative, "math_overall_score", None)  # type: ignore[assignment]
            model = getattr(initiative, "math_model", None)
            initiative.score_llm_suggested = bool(getattr(model, "suggested_by_llm", False))  # type: ignore[assignment]
            initiative.score_approved_by_user = bool(getattr(model, "approved_by_user", False))  # type: ignore[assignment]

        now = datetime.now(timezone.utc)
        initiative.active_scoring_framework = framework.value  # type: ignore[assignment]
        initiative.updated_source = token(Provenance.FLOW2_ACTIVATE)  # type: ignore[assignment]
        initiative.scoring_updated_source = token(Provenance.FLOW2_ACTIVATE)  # type: ignore[assignment]
        initiative.scoring_updated_at = now  # type: ignore[assignment]

        logger.debug(
            "scoring.activated",
            extra={
                "initiative_key": getattr(initiative, "initiative_key", None),
                "framework": framework.value,
                "overall_score": getattr(initiative, "overall_score", None),
            },
        )

        return history_row

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
        elif framework == ScoringFramework.MATH_MODEL:
            return self._build_math_model_inputs(initiative)
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

    def _build_math_model_inputs(self, initiative: Initiative) -> ScoreInputs:
        """Build Math Model inputs using approved parameters and stored formula."""

        model = getattr(initiative, "math_model", None)
        params_env: Dict[str, float] = {}
        for p in getattr(initiative, "params", []) or []:
            if not isinstance(p, InitiativeParam):
                continue
            if getattr(p, "framework", None) != ScoringFramework.MATH_MODEL.value:
                continue
            if not getattr(p, "approved", False):
                continue
            param_value = getattr(p, "value", None)
            if param_value is None:
                continue
            try:
                param_name = str(p.param_name) if p.param_name is not None else ""
                params_env[param_name] = float(param_value)
            except Exception:
                continue

        extra = {
            "use_math_model": bool(getattr(initiative, "use_math_model", False)),
            "formula_text": getattr(model, "formula_text", None),
            "math_model_approved": bool(getattr(model, "approved_by_user", False)),
            "math_model_llm_suggested": bool(getattr(model, "suggested_by_llm", False)),
            "math_model_assumptions": getattr(model, "assumptions_text", None),
            "params_env": params_env,
            "effort_engineering_days": getattr(initiative, "effort_engineering_days", None),
        }

        return ScoreInputs(extra=extra)


__all__ = ["ScoringService"]
