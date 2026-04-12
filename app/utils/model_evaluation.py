# productroadmap_sheet_project/app/utils/model_evaluation.py
"""Utilities for evaluating and validating math model suggestions."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Protocol

from app.llm.models import MathModelEvaluation, MathModelPromptInput, MathModelSuggestion
from app.utils.safe_eval import validate_formula


logger = logging.getLogger(__name__)


class MathModelLLMProtocol(Protocol):
    """Protocol for LLM interactions related to math model generation and evaluation."""
    def suggest_math_model(self, payload: MathModelPromptInput) -> MathModelSuggestion: ...

    def evaluate_math_model(
        self,
        payload: MathModelPromptInput,
        suggestion: MathModelSuggestion,
    ) -> MathModelEvaluation: ...

    def revise_math_model(
        self,
        payload: MathModelPromptInput,
        suggestion: MathModelSuggestion,
        evaluation: MathModelEvaluation,
    ) -> MathModelSuggestion: ...


@dataclass(frozen=True)
class MathModelQualityResult:
    suggestion: MathModelSuggestion | None
    evaluation: MathModelEvaluation | None
    revision_attempts: int = 0
    llm_calls_made: int = 0
    validation_errors: list[str] = field(default_factory=list)
    acceptance_status: str | None = None
    rejection_reason: str | None = None


def _finalize_quality_result(payload: MathModelPromptInput, result: MathModelQualityResult) -> MathModelQualityResult:
    logger.info(
        "math_model.quality_cycle",
        extra={
            "initiative_key": payload.initiative_key,
            "target_kpi_key": payload.target_kpi_key,
            "selected_target_kpi": result.evaluation.selected_target_kpi if result.evaluation else None,
            "acceptance_status": result.acceptance_status,
            "rejection_reason": result.rejection_reason,
            "revision_attempts": result.revision_attempts,
            "llm_calls_made": result.llm_calls_made,
            "final_score": result.evaluation.score if result.evaluation else None,
            "final_verdict": result.evaluation.verdict if result.evaluation else None,
            "validation_error_count": len(result.validation_errors),
        },
    )
    return result


def evaluation_acceptance_status(score: int, verdict: str) -> str:
    if verdict == "accept" and score >= 80:
        return "accepted"
    if verdict == "needs_revision" or 50 <= score < 80:
        return "needs_revision"
    return "rejected"


def formula_mentions_target_delta(formula_text: str, target_kpi_key: str | None) -> bool:
    if not formula_text or not target_kpi_key:
        return True
    normalized_target = re.sub(r"[^a-z0-9_]+", "_", str(target_kpi_key).strip().lower()).strip("_")
    if not normalized_target:
        return True
    return f"delta_{normalized_target}" in formula_text.lower()


def run_math_model_quality_cycle(
    llm_client: MathModelLLMProtocol,
    payload: MathModelPromptInput,
    *,
    max_revision_attempts: int = 2,
) -> MathModelQualityResult:
    llm_calls_made = 0
    revision_attempts = 0
    current = llm_client.suggest_math_model(payload)
    llm_calls_made += 1

    while True:
        validation_errors = validate_formula(current.llm_suggested_formula_text)
        if validation_errors:
            return _finalize_quality_result(payload, MathModelQualityResult(
                suggestion=current,
                evaluation=None,
                revision_attempts=revision_attempts,
                llm_calls_made=llm_calls_made,
                validation_errors=validation_errors,
                acceptance_status="rejected",
                rejection_reason="rule_validation_failed",
            ))

        evaluation = llm_client.evaluate_math_model(payload, current)
        llm_calls_made += 1

        target_kpi_for_check = payload.target_kpi_key or evaluation.selected_target_kpi
        if target_kpi_for_check and not formula_mentions_target_delta(current.llm_suggested_formula_text, target_kpi_for_check):
            return _finalize_quality_result(payload, MathModelQualityResult(
                suggestion=current,
                evaluation=evaluation,
                revision_attempts=revision_attempts,
                llm_calls_made=llm_calls_made,
                acceptance_status="rejected",
                rejection_reason=f"value does not match target KPI '{target_kpi_for_check}'",
            ))

        acceptance_status = evaluation_acceptance_status(evaluation.score, evaluation.verdict)
        if acceptance_status != "needs_revision" or revision_attempts >= max_revision_attempts:
            return _finalize_quality_result(payload, MathModelQualityResult(
                suggestion=current,
                evaluation=evaluation,
                revision_attempts=revision_attempts,
                llm_calls_made=llm_calls_made,
                acceptance_status=acceptance_status,
                rejection_reason=None if acceptance_status != "rejected" else "rejected_by_evaluator",
            ))

        current = llm_client.revise_math_model(payload, current, evaluation)
        llm_calls_made += 1
        revision_attempts += 1