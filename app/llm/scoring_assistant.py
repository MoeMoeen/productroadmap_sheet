# productroadmap_sheet_project/app/llm/scoring_assistant.py

from __future__ import annotations

from app.db.models.initiative import Initiative
from app.llm.client import LLMClient
from app.llm.models import MathModelPromptInput, MathModelSuggestion
from app.sheets.models import MathModelRow


def suggest_math_model_for_initiative(
	initiative: Initiative,
	row: MathModelRow,
	llm: LLMClient,
) -> MathModelSuggestion:
	"""Construct prompt input from Initiative + MathModelRow and call LLM."""

	payload = MathModelPromptInput(
		initiative_key=str(initiative.initiative_key),
		title=str(initiative.title),
		problem_statement=getattr(initiative, "problem_statement", None),
		desired_outcome=getattr(initiative, "desired_outcome", None),
		llm_summary=getattr(initiative, "llm_summary", None),
		expected_impact_description=getattr(initiative, "expected_impact_description", None),
		impact_metric=getattr(initiative, "impact_metric", None),
		impact_unit=getattr(initiative, "impact_unit", None),
		model_name=getattr(row, "model_name", None),
		model_description_free_text=getattr(row, "model_description_free_text", None),
		model_prompt_to_llm=getattr(row, "model_prompt_to_llm", None),
	)

	return llm.suggest_math_model(payload)


__all__ = ["suggest_math_model_for_initiative"]
