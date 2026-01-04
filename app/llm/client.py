# productroadmap_sheet_project/app/llm/client.py

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from openai import OpenAI

from app.config import settings
from app.llm.models import MathModelPromptInput, MathModelSuggestion, ParamMetadataSuggestion

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around OpenAI client for math-model suggestions."""

    def __init__(self, client: Optional[OpenAI] = None) -> None:
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self._client = client or OpenAI(api_key=api_key)

    def suggest_math_model(self, payload: MathModelPromptInput) -> MathModelSuggestion:
        """Call OpenAI to generate a math model suggestion.

        Returns a MathModelSuggestion parsed from JSON response.
        """

        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(payload)

        model = settings.OPENAI_MODEL_MATHMODEL or "gpt-4o"  # Step 7: formula quality requires gpt-4o
        temperature = settings.OPENAI_TEMPERATURE
        max_tokens = settings.OPENAI_MAX_TOKENS
        timeout = settings.OPENAI_REQUEST_TIMEOUT

        resp = self._client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            timeout=timeout,
        )

        try:
            content = resp.choices[0].message.content
            data = json.loads(content or "{}")
            return MathModelSuggestion.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("llm.suggest_math_model_parse_error", extra={"response": str(resp)})
            raise RuntimeError(f"Failed to parse LLM response: {exc}") from exc

    def suggest_param_metadata(self, initiative_key: str, identifiers: list[str], formula_text: str = "") -> ParamMetadataSuggestion:
        """Call OpenAI to suggest parameter metadata for identifiers.

        Uses cheaper model for Step 8. Returns ParamMetadataSuggestion.
        Includes formula context for better quality.
        """
        if not identifiers:
            raise ValueError("identifiers list is empty")

        system_prompt = (
            "You help define parameter metadata for product value models. "
            "Return ONLY a JSON object with keys: initiative_key (string), identifiers (list of strings), params (list of objects). "
            "Each params item must have: key, name, description, unit, example_value, source_hint. "
            "Rules: key must match an identifier exactly; provide concise, practical names and descriptions; "
            "units should be simple (e.g., 'days', 'USD', 'count'); example_value can be a number or short string; "
            "Do not include any text outside the JSON."
        )
        user_prompt_lines = [
            f"Initiative: {initiative_key}",
            f"Identifiers needing metadata: {', '.join(identifiers)}",
        ]
        if formula_text:
            user_prompt_lines.append(f"Formula: {formula_text}")
        user_prompt = "\n".join(user_prompt_lines)

        model = settings.OPENAI_MODEL_PARAMMETA or settings.OPENAI_MODEL
        temperature = settings.OPENAI_TEMPERATURE
        max_tokens = settings.OPENAI_MAX_TOKENS
        timeout = settings.OPENAI_REQUEST_TIMEOUT

        resp = self._client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            timeout=timeout,
        )

        try:
            content = resp.choices[0].message.content
            data = json.loads(content or "{}")
            return ParamMetadataSuggestion.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("llm.suggest_param_metadata_parse_error", extra={"response": str(resp)})
            raise RuntimeError(f"Failed to parse LLM response: {exc}") from exc


def _build_system_prompt() -> str:
    return (
        "You are an expert product & finance analyst. "
        "Design quantitative value models for product initiatives. "
        "Return ONLY a JSON object with keys: llm_suggested_formula_text (multi-line script), "
        "llm_suggested_metric_chain_text (string; optional), llm_notes (string). "
        "Do NOT generate assumptions—any assumptions in the prompt are PM-authored context only. "
        "Rules: llm_suggested_formula_text must use only assignment lines 'name = expression'; "
        "define 'value' as primary metric; optionally define 'effort' (or 'effort_days') and 'overall'; "
        "align to the immediate KPI when provided; propose an improved metric chain only if it clarifies the KPI path; "
        "use lower_snake_case variable names; allowed operations are +, -, *, /, parentheses, min(), max(); "
        "no imports, no function definitions, no prose outside JSON. "
        "Example formula_text: "
        "ticket_savings = ticket_reduction_per_month * cost_per_ticket * horizon_months\n"
        "churn_savings = churn_reduction * affected_customers * customer_lifetime_value\n"
        "total_cost = one_off_cost + monthly_running_cost * horizon_months\n"
        "value = ticket_savings + churn_savings - total_cost\n"
        "overall = value / effort_days"
    )


def _build_user_prompt(payload: MathModelPromptInput) -> str:
    lines = [
        f"Initiative: {payload.initiative_key} - {payload.title}",
    ]

    def add(label: str, val: Optional[str]) -> None:
        if val:
            lines.append(f"{label}: {val}")

    add("Immediate KPI key", payload.immediate_kpi_key)
    add("Metric chain (PM provided)", payload.metric_chain_text)
    add("Problem", payload.problem_statement)
    add("Desired outcome", payload.desired_outcome)
    add("Hypothesis", payload.hypothesis)
    add("LLM summary", payload.llm_summary)
    add("Expected impact", payload.expected_impact_description)
    add("Impact metric", payload.impact_metric)
    add("Impact unit", payload.impact_unit)
    add("Model name", payload.model_name)
    add("Model description", payload.model_description_free_text)
    add("Custom prompt", payload.model_prompt_to_llm)
    add("Assumptions (PM-owned; do not change)", payload.assumptions_text)

    return "\n".join(lines)


__all__ = ["LLMClient"]
