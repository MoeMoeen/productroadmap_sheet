# productroadmap_sheet_project/app/llm/client.py

from __future__ import annotations

import json
import logging
from typing import Optional

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
        "You are a senior product economist and KPI modeling expert working on a dining platform.\n\n"
        "Your job is to build a causal, delta-based mathematical model that quantifies how a product initiative changes a target KPI.\n\n"
        "====================\n"
        "CORE PRINCIPLE\n"
        "====================\n"
        "You MUST model impact as a DELTA (change), never as an absolute KPI level.\n"
        "Every model must answer: how much does this initiative change the target KPI?\n\n"
        "====================\n"
        "REASONING PROCESS\n"
        "====================\n"
        "1. Identify the target KPI\n"
        "2. Identify the immediate KPI or driver that the initiative changes first\n"
        "3. Build a causal chain from the immediate change to the target KPI\n"
        "4. Express each step as a measurable delta\n"
        "5. Propagate deltas through the chain mathematically\n"
        "6. Output final delta as value\n\n"
        "====================\n"
        "MODEL REQUIREMENTS\n"
        "====================\n"
        "- The model MUST be delta-driven\n"
        "- The model MUST be causal, not correlational\n"
        "- The model MUST use real business quantities only\n"
        "- The model MUST align to the provided target KPI\n"
        "- If an immediate KPI is provided, it is only an upstream driver unless it is also the target KPI\n"
        "- If a metric chain is provided, stay on that chain or a very near equivalent refinement\n"
        "- The final output MUST be:\n"
        "    value = delta impact on target KPI\n\n"
        "====================\n"
        "STRICT RULES\n"
        "====================\n"
        "- DO NOT model effort, cost, implementation complexity, ROI, or efficiency\n"
        "- DO NOT output absolute KPI values as the final answer\n"
        "- DO NOT invent vague variables like impact_factor, quality_score, or efficiency_gain\n"
        "- DO NOT introduce unrelated KPIs that are outside the provided target/immediate/metric-chain context\n"
        "- When target KPI and immediate KPI differ, it is INVALID for value to equal the immediate KPI or its uplift directly\n"
        "- The final non-cost value term must be in the target KPI's units\n"
        "- All variables must represent measurable real-world quantities\n\n"
        "====================\n"
        "OUTPUT FORMAT\n"
        "====================\n"
        "Return ONLY a JSON object with keys:\n"
        "- llm_suggested_metric_chain_text\n"
        "- llm_suggested_formula_text\n"
        "- llm_notes\n\n"
        "====================\n"
        "FORMULA RULES\n"
        "====================\n"
        "- Use ONLY assignment lines: variable = expression\n"
        "- Use lower_snake_case variable names\n"
        "- Prefer delta_ prefixes for change variables\n"
        "- Allowed operations: +, -, *, /, parentheses, min(), max()\n"
        "- Do NOT write prose inside formula_text\n"
        "- Final output MUST include:\n"
        "    value = <delta impact on target KPI>\n\n"
        "====================\n"
        "QUALITY BAR\n"
        "====================\n"
        "The model must be realistic, causal, auditable, and usable by product and finance teams.\n"
        "It should clearly show how the initiative changes the target KPI through intermediate measurable steps.\n\n"
        "====================\n"
        "EXAMPLE\n"
        "====================\n"
        "Initiative: improve self-serve onboarding\n"
        "Immediate KPI: onboarding_conversion_rate\n"
        "Target KPI: active_restaurants\n"
        "Metric chain: onboarding_conversion_rate -> new_restaurants -> active_restaurants\n\n"
        "Formula:\n"
        "delta_onboarding_conversion_rate = improved_onboarding_conversion_rate - baseline_onboarding_conversion_rate\n"
        "delta_new_restaurants = potential_restaurants * delta_onboarding_conversion_rate\n"
        "delta_active_restaurants = delta_new_restaurants * restaurant_activation_rate\n"
        "value = delta_active_restaurants"
    )


def _build_user_prompt(payload: MathModelPromptInput) -> str:
    lines = [
        f"Initiative: {payload.initiative_key} - {payload.title}",
    ]

    def add(label: str, val: Optional[str]) -> None:
        if val:
            lines.append(f"{label}: {val}")

    add("Target KPI", payload.target_kpi_key)
    add("Immediate KPI", payload.immediate_kpi_key)

    if payload.target_kpi_key:
        lines.append(
            f"-> Your job is to model the DELTA (change) in '{payload.target_kpi_key}' caused by this initiative."
        )

    if payload.immediate_kpi_key:
        lines.append(
            f"-> '{payload.immediate_kpi_key}' is the first driver this initiative most directly changes."
        )

    if payload.immediate_kpi_key and payload.target_kpi_key and payload.immediate_kpi_key != payload.target_kpi_key:
        lines.append(
            f"-> IMPORTANT: do NOT make value equal '{payload.immediate_kpi_key}' or a delta of '{payload.immediate_kpi_key}'."
        )
        lines.append(
            f"-> REQUIRED: make value equal the incremental change in '{payload.target_kpi_key}', using '{payload.immediate_kpi_key}' only as an upstream driver."
        )

    lines.append("\n=== TASK ===")
    lines.append(
        "Build a delta-based causal model that quantifies how this initiative changes the target KPI."
    )

    lines.append("\n=== THINKING FRAMEWORK ===")
    lines.append(
        "- What behavior or funnel step does this initiative directly change?\n"
        "- Which metric changes first?\n"
        "- How does that change propagate to the target KPI?\n"
        "- What measurable deltas occur at each step?\n"
        "- How do these deltas combine into final impact on the target KPI?"
    )

    if payload.metric_chain_text:
        add("Existing metric chain", payload.metric_chain_text)
        lines.append("-> Stay on this chain unless a small refinement is clearly better.")

    add("Problem", payload.problem_statement)
    add("Desired outcome", payload.desired_outcome)
    add("Hypothesis", payload.hypothesis)
    add("LLM summary", payload.llm_summary)
    add("Expected impact", payload.expected_impact_description)
    add("Impact metric", payload.impact_metric)
    add("Impact unit", payload.impact_unit)
    add("Model name", payload.model_name)
    add("Model description", payload.model_description_free_text)
    add("Custom instructions", payload.model_prompt_to_llm)
    if payload.llm_context_text:
        lines.append("\n=== COMPANY CONTEXT ===")
        lines.append(payload.llm_context_text)
    if payload.metrics_config_text:
        lines.append("\n=== RELEVANT KPI DEFINITIONS ===")
        lines.append(payload.metrics_config_text)
    if payload.assumptions_text:
        lines.append("\n=== PM ASSUMPTIONS ===")
        lines.append(payload.assumptions_text)

    lines.append("\n=== IMPORTANT CONSTRAINTS ===")
    lines.append(
        "- Model ONLY impact delta, not absolute KPI levels\n"
        "- Do NOT include effort, cost, ROI, or efficiency terms\n"
        "- Use only real business metrics relevant to the target/immediate/metric-chain context\n"
        "- Do NOT pull in unrelated KPIs from elsewhere in the business\n"
        "- Final output must define: value = delta impact on target KPI"
    )

    return "\n".join(lines)


def build_constructed_math_model_prompt(payload: MathModelPromptInput) -> str:
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(payload)
    return "\n\n".join(
        [
            "[system]",
            system_prompt,
            "[user]",
            user_prompt,
        ]
    )


__all__ = ["LLMClient", "build_constructed_math_model_prompt"]
