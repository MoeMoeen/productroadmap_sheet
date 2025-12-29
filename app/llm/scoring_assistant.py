# productroadmap_sheet_project/app/llm/scoring_assistant.py

from __future__ import annotations

from app.db.models.initiative import Initiative
from app.llm.client import LLMClient
from app.llm.models import MathModelPromptInput, MathModelSuggestion, ParamMetadataSuggestion
from app.sheets.models import MathModelRow


def suggest_math_model_for_initiative(
	initiative: Initiative,
	row: MathModelRow,
	llm: LLMClient,
) -> MathModelSuggestion:
	"""Construct prompt input from Initiative + MathModelRow and call LLM.
	
	Includes PM-authored model description/prompt and any existing assumptions/notes
	so LLM can build on prior context or iterate.
	"""

	payload = MathModelPromptInput(
		initiative_key=str(initiative.initiative_key),
		title=str(initiative.title),
		problem_statement=getattr(initiative, "problem_statement", None),
		desired_outcome=getattr(initiative, "desired_outcome", None),
		hypothesis=getattr(initiative, "hypothesis", None),
		llm_summary=getattr(initiative, "llm_summary", None),
		expected_impact_description=getattr(initiative, "expected_impact_description", None),
		impact_metric=getattr(initiative, "impact_metric", None),
		impact_unit=getattr(initiative, "impact_unit", None),
		model_name=getattr(row, "model_name", None),
		model_description_free_text=getattr(row, "model_description_free_text", None),
		model_prompt_to_llm=getattr(row, "model_prompt_to_llm", None),
		assumptions_text=getattr(row, "assumptions_text", None),
		llm_notes=getattr(row, "llm_notes", None),
	)

	return llm.suggest_math_model(payload)


def suggest_param_metadata_for_model(
	initiative_key: str,
	identifiers: list[str],
	formula_text: str,
	llm: LLMClient,
) -> ParamMetadataSuggestion:
	"""Call LLM to suggest param metadata for formula identifiers.

	Step 8: Use approved formula identifiers + formula context to get param metadata.
	Includes formula for better LLM quality.
	"""
	return llm.suggest_param_metadata(initiative_key, identifiers, formula_text=formula_text)


__all__ = ["suggest_math_model_for_initiative", "suggest_param_metadata_for_model"]
