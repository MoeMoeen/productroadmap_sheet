# productroadmap_sheet_project/app/llm/scoring_assistant.py

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.initiative import Initiative
from app.db.models.optimization import OrganizationMetricConfig
from app.llm.client import LLMClient
from app.llm.context_formatters import format_llm_context_sections, format_metrics_config_rows
from app.llm.models import MathModelPromptInput, MathModelSuggestion, ParamMetadataSuggestion
from app.sheets.client import SheetsClient
from app.sheets.llm_context_reader import LLMContextReader
from app.sheets.metrics_config_reader import MetricsConfigReader
from app.sheets.models import MathModelRow, MetricsConfigRow
from app.services.product_ops.metric_chain_parser import format_chain_for_llm, parse_metric_chain
from app.utils.header_utils import normalize_header

logger = logging.getLogger(__name__)


def load_sheet_level_llm_context(

	sheets_client: Optional[SheetsClient],
	*,
	spreadsheet_id: Optional[str],
	tab_name: Optional[str] = None,
) -> Optional[str]:
	"""Load and format shared ProductOps LLM context for prompt enrichment."""
	if sheets_client is None or not spreadsheet_id:
		return None

	try:
		resolved_tab = tab_name or (getattr(settings.PRODUCT_OPS, "llm_context_tab", None) if settings.PRODUCT_OPS else None) or "LLM_Context"
		reader = LLMContextReader(
			client=sheets_client,
			spreadsheet_id=str(spreadsheet_id),
			tab_name=str(resolved_tab),
		)
		sections = reader.read()
		formatted = format_llm_context_sections(sections)
		if not formatted.text:
			return None
		logger.info(
			"llm_context.loaded",
			extra={
				"tab": resolved_tab,
				"section_count": formatted.included_sections,
				"entry_count": formatted.included_lines,
				"truncated": formatted.truncated,
				"total_chars": formatted.total_chars,
			},
		)
		return formatted.text
	except Exception as exc:
		logger.warning("llm_context.load_failed: %s", str(exc)[:200])
		return None


def load_metrics_config_prompt_context(
	sheets_client: Optional[SheetsClient],
	*,
	spreadsheet_id: Optional[str],
	tab_name: Optional[str] = None,
) -> Optional[str]:
	"""Load and format active KPI definitions from Metrics_Config for prompt enrichment."""
	if sheets_client is None or not spreadsheet_id:
		return None

	try:
		resolved_tab = tab_name or (getattr(settings.PRODUCT_OPS, "metrics_config_tab", None) if settings.PRODUCT_OPS else None) or "Metrics_Config"
		reader = MetricsConfigReader(sheets_client)
		rows = [
			row
			for _, row in reader.get_rows_for_sheet(str(spreadsheet_id), str(resolved_tab))
			if getattr(row, "is_active", None) is True and getattr(row, "kpi_key", None)
		]
		formatted = format_metrics_config_rows(rows)
		if not formatted.text:
			return None
		logger.info(
			"metrics_config_prompt.loaded",
			extra={
				"tab": resolved_tab,
				"metrics_count": formatted.included_lines,
				"truncated": formatted.truncated,
				"total_chars": formatted.total_chars,
			},
		)
		return formatted.text
	except Exception as exc:
		logger.warning("metrics_config_prompt.load_failed: %s", str(exc)[:200])
		return None


def load_metrics_config_prompt_json(
	sheets_client: Optional[SheetsClient],
	*,
	spreadsheet_id: Optional[str],
	tab_name: Optional[str] = None,
) -> Optional[list[dict[str, Optional[str]]]]:
	"""Load active KPI definitions as structured JSON for prompt use."""
	if sheets_client is None or not spreadsheet_id:
		return None

	try:
		resolved_tab = tab_name or (getattr(settings.PRODUCT_OPS, "metrics_config_tab", None) if settings.PRODUCT_OPS else None) or "Metrics_Config"
		reader = MetricsConfigReader(sheets_client)
		rows = [
			row
			for _, row in reader.get_rows_for_sheet(str(spreadsheet_id), str(resolved_tab))
			if getattr(row, "is_active", None) is True and getattr(row, "kpi_key", None)
		]
		return [_metrics_row_to_prompt_json(row) for row in rows]
	except Exception as exc:
		logger.warning("metrics_config_prompt_json.load_failed: %s", str(exc)[:200])
		return None


def _metrics_row_to_prompt_json(row: MetricsConfigRow) -> dict[str, Optional[str]]:
	return {
		"kpi_key": getattr(row, "kpi_key", None),
		"kpi_name": getattr(row, "kpi_name", None),
		"kpi_level": getattr(row, "kpi_level", None),
		"unit": getattr(row, "unit", None),
		"description": getattr(row, "description", None),
	}


def normalize_kpi_reference(
	reference: Optional[str],
	metrics_config_json: Optional[list[dict[str, Optional[str]]]],
) -> Optional[str]:
	if not reference:
		return reference
	if not metrics_config_json:
		return reference

	normalized_reference = normalize_header(reference)
	if not normalized_reference:
		return reference

	for item in metrics_config_json:
		kpi_key = item.get("kpi_key") if isinstance(item, dict) else None
		kpi_name = item.get("kpi_name") if isinstance(item, dict) else None
		if kpi_key and normalize_header(kpi_key) == normalized_reference:
			return kpi_key
		if kpi_name and normalize_header(kpi_name) == normalized_reference:
			return kpi_key or reference

	return reference


def build_math_model_prompt_enrichment(
	sheets_client: Optional[SheetsClient],
	*,
	spreadsheet_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
	"""Load shared prompt enrichment used by math-model suggestion flows."""
	llm_context_text = load_sheet_level_llm_context(
		sheets_client,
		spreadsheet_id=spreadsheet_id,
		tab_name=getattr(settings.PRODUCT_OPS, "llm_context_tab", None) if settings.PRODUCT_OPS else None,
	)
	metrics_config_text = load_metrics_config_prompt_context(
		sheets_client,
		spreadsheet_id=spreadsheet_id,
		tab_name=getattr(settings.PRODUCT_OPS, "metrics_config_tab", None) if settings.PRODUCT_OPS else None,
	)
	return llm_context_text, metrics_config_text


def format_metric_chain_for_prompt(metric_chain_text: Optional[str], db: Optional[Session]) -> Optional[str]:
	"""Format metric-chain text with KPI metadata when DB context is available."""
	if not metric_chain_text:
		return metric_chain_text
	if db is None:
		return metric_chain_text

	try:
		parsed = parse_metric_chain(metric_chain_text)
		if not parsed or "chain" not in parsed:
			return metric_chain_text

		kpi_keys = parsed["chain"]
		configs = db.query(OrganizationMetricConfig).filter(OrganizationMetricConfig.kpi_key.in_(kpi_keys)).all()
		config_dicts = [
			{
				"kpi_key": cfg.kpi_key,
				"kpi_name": cfg.kpi_name,
				"kpi_level": cfg.kpi_level,
			}
			for cfg in configs
		]
		return format_chain_for_llm(parsed, config_dicts)
	except Exception as exc:
		logger.debug("Could not format metric chain for prompt: %s", str(exc))
		return metric_chain_text


def build_math_model_prompt_input(
	initiative: Initiative,
	row: MathModelRow,
	*,
	db: Optional[Session] = None,
	llm_context_text: Optional[str] = None,
	metrics_config_text: Optional[str] = None,
	metrics_config_json: Optional[list[dict[str, Optional[str]]]] = None,
) -> MathModelPromptInput:
	"""Build the exact prompt payload used for math-model suggestions."""

	return MathModelPromptInput(
		initiative_key=str(initiative.initiative_key),
		title=str(initiative.title),
		problem_statement=getattr(initiative, "problem_statement", None),
		desired_outcome=getattr(initiative, "desired_outcome", None),
		hypothesis=getattr(initiative, "hypothesis", None),
		llm_summary=getattr(initiative, "llm_summary", None),
		immediate_kpi_key=normalize_kpi_reference(
			getattr(row, "immediate_kpi_key", None) or getattr(initiative, "immediate_kpi_key", None),
			metrics_config_json,
		),
		target_kpi_key=normalize_kpi_reference(
			getattr(row, "target_kpi_key", None),
			metrics_config_json,
		),
		metric_chain_text=format_metric_chain_for_prompt(getattr(row, "metric_chain_text", None), db),
		expected_impact_description=getattr(initiative, "expected_impact_description", None),
		impact_metric=getattr(initiative, "impact_metric", None),
		impact_unit=getattr(initiative, "impact_unit", None),
		model_name=getattr(row, "model_name", None),
		model_description_free_text=getattr(row, "model_description_free_text", None),
		model_prompt_to_llm=getattr(row, "model_prompt_to_llm", None),
		llm_context_text=llm_context_text,
		metrics_config_text=metrics_config_text,
		metrics_config_json=metrics_config_json,
		assumptions_text=getattr(row, "assumptions_text", None),
	)


def suggest_math_model_for_initiative(
	initiative: Initiative,
	row: MathModelRow,
	llm: LLMClient,
	*,
	db: Optional[Session] = None,
	llm_context_text: Optional[str] = None,
	metrics_config_text: Optional[str] = None,
	metrics_config_json: Optional[list[dict[str, Optional[str]]]] = None,
) -> MathModelSuggestion:
	"""Construct prompt input from Initiative + MathModelRow and call LLM.

	Includes PM-authored model description/prompt and any existing assumptions/notes
	so LLM can build on prior context or iterate.
	"""

	payload = build_math_model_prompt_input(
		initiative,
		row,
		db=db,
		llm_context_text=llm_context_text,
		metrics_config_text=metrics_config_text,
		metrics_config_json=metrics_config_json,
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


__all__ = [
	"build_math_model_prompt_enrichment",
	"build_math_model_prompt_input",
	"format_metric_chain_for_prompt",
	"load_metrics_config_prompt_json",
	"load_metrics_config_prompt_context",
	"load_sheet_level_llm_context",
	"normalize_kpi_reference",
	"suggest_math_model_for_initiative",
	"suggest_param_metadata_for_model",
]
