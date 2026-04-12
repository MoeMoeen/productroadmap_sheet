# productroadmap_sheet_project/app/jobs/math_model_generation_job.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.llm.client import LLMClient, build_constructed_math_model_prompt
from app.llm.scoring_assistant import build_math_model_prompt_enrichment, build_math_model_prompt_input, load_metrics_config_prompt_json
from app.sheets.math_models_reader import MathModelsReader, MathModelRowPair
from app.sheets.math_models_writer import MathModelsWriter
from app.sheets.client import SheetsClient
from app.utils.model_evaluation import evaluation_acceptance_status, run_math_model_quality_cycle

logger = logging.getLogger(__name__)


def _has_sufficient_generation_context(initiative: Initiative, row: object) -> bool:
	has_problem_context = bool(
		(getattr(initiative, "problem_statement", None) and str(getattr(initiative, "problem_statement", "")).strip())
		or (getattr(initiative, "hypothesis", None) and str(getattr(initiative, "hypothesis", "")).strip())
		or (getattr(initiative, "llm_summary", None) and str(getattr(initiative, "llm_summary", "")).strip())
		or (getattr(initiative, "title", None) and str(getattr(initiative, "title", "")).strip())
	)
	has_row_prompt = bool(
		(getattr(row, "model_description_free_text", None) and str(getattr(row, "model_description_free_text", "")).strip())
		or (getattr(row, "model_prompt_to_llm", None) and str(getattr(row, "model_prompt_to_llm", "")).strip())
	)
	return has_problem_context or has_row_prompt


def needs_suggestion(row: object, force: bool = False) -> bool:
	try:
		approved = bool(getattr(row, "approved_by_user", False))
		has_existing = bool(getattr(row, "llm_suggested_formula_text", None))
	except Exception:
		return False

	if approved:
		return False
	if has_existing and not force:
		return False
	return True


def run_math_model_generation_job(
	db: Session,
	sheets_client: SheetsClient,
	llm_client: LLMClient,
	spreadsheet_id: str,
	tab_name: str,
	max_rows: Optional[int] = None,
	force: bool = False,
	max_llm_calls: int = 10,  # Cost safety guard: limit LLM calls per run
) -> Dict[str, Any]:
	reader = MathModelsReader(sheets_client)
	writer = MathModelsWriter(sheets_client)

	rows: List[MathModelRowPair] = reader.get_rows_for_sheet(
		spreadsheet_id=spreadsheet_id,
		tab_name=tab_name,
		max_rows=max_rows,
	)
	llm_context_text, metrics_config_text = build_math_model_prompt_enrichment(
		sheets_client,
		spreadsheet_id=spreadsheet_id,
	)
	metrics_config_json = load_metrics_config_prompt_json(
		sheets_client,
		spreadsheet_id=spreadsheet_id,
	)
	suggestions_to_write: List[Dict[str, object]] = []
	suggested = 0
	skipped_approved = 0
	skipped_no_desc = 0
	skipped_has_suggestion = 0
	skipped_missing_initiative = 0
	formula_validation_failures = 0
	evaluation_accept_count = 0
	evaluation_needs_revision_count = 0
	evaluation_reject_count = 0
	total_llm_calls = 0
	rejected_details: List[Dict[str, object]] = []

	for row_number, mm in rows:
		# COST GUARD: Stop if reached max LLM calls
		if total_llm_calls >= max_llm_calls:
			logger.warning(f"Stopping: reached max_llm_calls limit ({max_llm_calls})")
			break
		if getattr(mm, "approved_by_user", False):
			skipped_approved += 1
			continue
		if getattr(mm, "llm_suggested_formula_text", None) and not force:
			skipped_has_suggestion += 1
			continue
		initiative = (
			db.query(Initiative)
			.filter(Initiative.initiative_key == getattr(mm, "initiative_key", None))
			.one_or_none()
		)
		if not initiative:
			skipped_missing_initiative += 1
			continue
		if not _has_sufficient_generation_context(initiative, mm):
			skipped_no_desc += 1
			continue

		try:
			payload = build_math_model_prompt_input(
				initiative,
				mm,
				db=db,
				llm_context_text=llm_context_text,
				metrics_config_text=metrics_config_text,
				metrics_config_json=metrics_config_json,
			)
			quality_result = run_math_model_quality_cycle(
				llm_client,
				payload,
				max_revision_attempts=2,
			)
			total_llm_calls += quality_result.llm_calls_made
			if quality_result.validation_errors:
				logger.warning(
					f"Formula validation failed for {getattr(mm, 'initiative_key', 'unknown')}: {quality_result.validation_errors}",
				)
				formula_validation_failures += 1
				rejected_details.append(
					{
						"initiative_key": getattr(mm, "initiative_key", None),
						"row_number": row_number,
						"reason": "rule_validation_failed",
						"validation_errors": quality_result.validation_errors,
					}
				)
				continue
			if quality_result.suggestion is None or quality_result.evaluation is None:
				if quality_result.acceptance_status == "rejected":
					evaluation_reject_count += 1
					rejected_details.append(
						{
							"initiative_key": getattr(mm, "initiative_key", None),
							"row_number": row_number,
							"reason": quality_result.rejection_reason or "evaluation_pipeline_failed",
						}
					)
				continue
			suggestion = quality_result.suggestion
			evaluation = quality_result.evaluation
			if quality_result.acceptance_status == "rejected":
				evaluation_reject_count += 1
				rejected_details.append(
					{
						"initiative_key": getattr(mm, "initiative_key", None),
						"row_number": row_number,
						"reason": quality_result.rejection_reason or "rejected_by_evaluator",
						"score": evaluation.score,
						"verdict": evaluation.verdict,
					}
				)
				logger.warning(
					"math_model.evaluation_rejected",
					extra={
						"initiative_key": getattr(mm, "initiative_key", None),
						"row": row_number,
						"score": evaluation.score,
						"reason": quality_result.rejection_reason,
					},
				)
				continue
			# COST LOGGING: Log LLM call metadata
			logger.info(
				"math_model.llm_call_made",
				extra={
					"initiative_key": getattr(mm, "initiative_key", None),
					"row": row_number,
					"model": "gpt-4o",
					"formula_length": len(suggestion.llm_suggested_formula_text) if suggestion.llm_suggested_formula_text else 0,
				},
			)
		except Exception:
			logger.exception(
				"math_model.suggest_error",
				extra={"initiative_key": getattr(mm, "initiative_key", None)},
			)
			continue

		constructed_prompt = build_constructed_math_model_prompt(payload)
		evaluation_status = evaluation_acceptance_status(evaluation.score, evaluation.verdict)
		if evaluation_status == "accepted":
			evaluation_accept_count += 1
		elif evaluation_status == "needs_revision":
			evaluation_needs_revision_count += 1
		else:
			evaluation_reject_count += 1

		suggestions_to_write.append(
			{
				"row_number": row_number,
				"llm_suggested_formula_text": suggestion.llm_suggested_formula_text,
				"llm_notes": suggestion.llm_notes,
				"llm_suggested_metric_chain_text": suggestion.llm_suggested_metric_chain_text,
				"constructed_llm_prompt": constructed_prompt,
				"llm_evaluation_score": evaluation.score,
				"llm_evaluation_verdict": evaluation.verdict,
				"llm_evaluation_issues": "\n".join(evaluation.issues),
				"llm_evaluation_strengths": "\n".join(evaluation.strengths),
				"llm_evaluation_suggested_improvements": "\n".join(evaluation.suggested_improvements),
				"llm_selected_target_kpi": evaluation.selected_target_kpi,
				"llm_target_kpi_reasoning": evaluation.target_kpi_reasoning,
				"llm_revision_attempts": quality_result.revision_attempts,
			}
		)
		suggested += 1

	if suggestions_to_write:
		writer.write_suggestions_batch(
			spreadsheet_id=spreadsheet_id,
			tab_name=tab_name,
			suggestions=suggestions_to_write,
		)

	stats = {
		"rows": len(rows),
		"suggested": suggested,
		"llm_calls": total_llm_calls,
		"formula_validation_failures": formula_validation_failures,
		"evaluation_accept_count": evaluation_accept_count,
		"evaluation_needs_revision_count": evaluation_needs_revision_count,
		"evaluation_reject_count": evaluation_reject_count,
		"rejected_details": rejected_details,
		"skipped_approved": skipped_approved,
		"skipped_no_desc": skipped_no_desc,
		"skipped_has_suggestion": skipped_has_suggestion,
		"skipped_missing_initiative": skipped_missing_initiative,
	}

	logger.info("math_model.generation_complete", extra=stats)
	return stats


__all__ = ["run_math_model_generation_job", "needs_suggestion"]
