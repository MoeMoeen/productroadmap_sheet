# productroadmap_sheet_project/app/jobs/math_model_generation_job.py

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.llm.client import LLMClient
from app.llm.scoring_assistant import suggest_math_model_for_initiative
from app.sheets.math_models_reader import MathModelsReader, MathModelRowPair
from app.sheets.math_models_writer import MathModelsWriter
from app.sheets.client import SheetsClient
from app.utils.safe_eval import validate_formula  # Formula validation

logger = logging.getLogger(__name__)


def needs_suggestion(row: object, force: bool = False) -> bool:
	try:
		approved = bool(getattr(row, "approved_by_user", False))
		has_desc = bool(getattr(row, "model_description_free_text", None) or getattr(row, "model_prompt_to_llm", None))
		has_existing = bool(getattr(row, "llm_suggested_formula_text", None))
	except Exception:
		return False

	if approved:
		return False
	if has_existing and not force:
		return False
	if not has_desc:
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
) -> Dict[str, int]:
	reader = MathModelsReader(sheets_client)
	writer = MathModelsWriter(sheets_client)

	rows: List[MathModelRowPair] = reader.get_rows_for_sheet(
		spreadsheet_id=spreadsheet_id,
		tab_name=tab_name,
		max_rows=max_rows,
	)

	suggestions_to_write: List[Dict[str, object]] = []
	suggested = 0
	skipped_approved = 0
	skipped_no_desc = 0
	skipped_has_suggestion = 0
	skipped_missing_initiative = 0
	formula_validation_warnings = 0

	for row_number, mm in rows:
		# COST GUARD: Stop if reached max LLM calls
		if suggested >= max_llm_calls:
			logger.warning(f"Stopping: reached max_llm_calls limit ({max_llm_calls})")
			break
		if getattr(mm, "approved_by_user", False):
			skipped_approved += 1
			continue
		if getattr(mm, "llm_suggested_formula_text", None) and not force:
			skipped_has_suggestion += 1
			continue
		if not (getattr(mm, "model_description_free_text", None) or getattr(mm, "model_prompt_to_llm", None)):
			skipped_no_desc += 1
			continue

		initiative = (
			db.query(Initiative)
			.filter(Initiative.initiative_key == getattr(mm, "initiative_key", None))
			.one_or_none()
		)
		if not initiative:
			skipped_missing_initiative += 1
			continue

		try:
			suggestion = suggest_math_model_for_initiative(initiative, mm, llm_client)
			# COST LOGGING: Log LLM call metadata
			logger.info(
				"math_model.llm_call_made",
				extra={
					"initiative_key": getattr(mm, "initiative_key", None),
					"row": row_number,
					"model": "gpt-4o",
					"formula_length": len(suggestion.formula_text) if suggestion.formula_text else 0,
				},
			)
		except Exception:
			logger.exception(
				"math_model.suggest_error",
				extra={"initiative_key": getattr(mm, "initiative_key", None)},
			)
			continue

		# FORMULA VALIDATION: Check if formula is valid, warn if not
		if suggestion.formula_text:
			try:
				errors = validate_formula(suggestion.formula_text)
				if errors:
					logger.warning(
						f"Formula validation warning for {getattr(mm, 'initiative_key', 'unknown')}: {errors}",
					)
					formula_validation_warnings += 1
			except Exception as e:
				logger.warning(
					f"Could not validate formula for {getattr(mm, 'initiative_key', 'unknown')}: {e}",
				)

		suggestions_to_write.append(
			{
				"row_number": row_number,
				"llm_suggested_formula_text": suggestion.formula_text,
				"assumptions_text": "\n".join(suggestion.assumptions),
				"llm_notes": suggestion.notes,
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
		"formula_validation_warnings": formula_validation_warnings,
		"skipped_approved": skipped_approved,
		"skipped_no_desc": skipped_no_desc,
		"skipped_has_suggestion": skipped_has_suggestion,
		"skipped_missing_initiative": skipped_missing_initiative,
	}

	logger.info("math_model.generation_complete", extra=stats)
	return stats


__all__ = ["run_math_model_generation_job", "needs_suggestion"]
