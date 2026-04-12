# productroadmap_sheet_project/app/llm/client.py
from __future__ import annotations

import json
import logging
from typing import Optional

from openai import OpenAI

from app.config import settings
from app.llm.models import (
    InitiativeSummaryOutput,
    InitiativeSummaryPromptInput,
    MathModelEvaluation,
    MathModelPromptInput,
    MathModelSuggestion,
    ParamMetadataSuggestion,
)

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

    def evaluate_math_model(
        self,
        payload: MathModelPromptInput,
        suggestion: MathModelSuggestion,
    ) -> MathModelEvaluation:
        system_prompt = _build_math_model_evaluator_system_prompt()
        user_prompt = _build_math_model_evaluator_user_prompt(payload, suggestion)

        model = settings.OPENAI_MODEL_MATHMODEL or "gpt-4o"
        temperature = 0.1
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
            return MathModelEvaluation.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("llm.evaluate_math_model_parse_error", extra={"response": str(resp)})
            raise RuntimeError(f"Failed to parse math model evaluation response: {exc}") from exc

    def revise_math_model(
        self,
        payload: MathModelPromptInput,
        suggestion: MathModelSuggestion,
        evaluation: MathModelEvaluation,
    ) -> MathModelSuggestion:
        system_prompt = _build_math_model_revision_system_prompt()
        user_prompt = _build_math_model_revision_user_prompt(payload, suggestion, evaluation)

        model = settings.OPENAI_MODEL_MATHMODEL or "gpt-4o"
        temperature = 0.1
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
            logger.exception("llm.revise_math_model_parse_error", extra={"response": str(resp)})
            raise RuntimeError(f"Failed to parse math model revision response: {exc}") from exc

    def generate_initiative_summary(
        self,
        payload: InitiativeSummaryPromptInput,
    ) -> InitiativeSummaryOutput:
        system_prompt = _build_initiative_summary_system_prompt()
        user_prompt = _build_initiative_summary_user_prompt(payload)

        model = settings.OPENAI_MODEL
        temperature = 0.1
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
            return InitiativeSummaryOutput.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("llm.generate_initiative_summary_parse_error", extra={"response": str(resp)})
            raise RuntimeError(f"Failed to parse initiative summary response: {exc}") from exc


def _build_system_prompt() -> str:
    return (
        "You are a senior product economist and KPI modeling expert working on a dining/checkout platform.\n\n"

        "Your job is to build a **causal, delta-based mathematical model** that quantifies how a product initiative impacts a target KPI.\n\n"

        "====================\n"
        "CORE PRINCIPLE\n"
        "====================\n"
        "You MUST model IMPACT as a DELTA (change), not absolute values.\n\n"
        "Every model must answer:\n"
        "→ How much does this initiative CHANGE the target KPI?\n\n"

        "====================\n"
        "REASONING PROCESS (MANDATORY)\n"
        "====================\n"
        "1. Identify the target KPI\n"
        "2. Identify which metric(s) the initiative directly changes\n"
        "3. Build a causal chain from those changes → target KPI\n"
        "4. Express each step as a measurable delta\n"
        "5. Propagate deltas through the chain mathematically\n"
        "6. Output final delta as 'value'\n\n"

        "====================\n"
        "MODEL REQUIREMENTS\n"
        "====================\n"
        "- The model MUST be delta-driven (prefix variables with delta_ when applicable)\n"
        "- The model MUST reflect real business mechanics (no abstract variables)\n"
        "- The model MUST follow a causal chain (not random formulas)\n"
        "- The model MUST align with KPI structure if provided\n"
        "- If a metric chain is provided, the formula MUST follow the same causal structure and represent each step of the chain\n"
        "- The model MUST include at least 2-3 steps: immediate KPI delta, propagation step(s), and final KPI impact\n"
        "- The final output MUST be:\n"
        "    value = delta impact on target KPI\n\n"

        "====================\n"
        "STRICT RULES\n"
        "====================\n"
        "- DO NOT model effort, cost, or implementation complexity\n"
        "- DO NOT include ROI, efficiency, or effort-based metrics\n"
        "- DO NOT invent meaningless variables (e.g. 'impact_factor')\n"
        "- DO NOT output absolute KPI values\n"
        "- ALWAYS output delta-based variables\n"
        "- ALL variables must represent real measurable quantities\n\n"

        "====================\n"
        "TARGET KPI SELECTION RULE\n"
        "====================\n"
        "If Target KPI is NOT explicitly provided:\n\n"
        "1. You MUST select the most appropriate Target KPI from the KPI definitions provided.\n"
        "2. Only choose from:\n"
        "   - North Star KPIs\n"
        "   - Strategic KPIs\n"
        "3. DO NOT choose low-level or operational metrics as the final value.\n"
        "4. The selected Target KPI must represent a business outcome (e.g., revenue, GMV, profit, retention).\n\n"
        "You must explicitly reflect this choice in:\n"
        "- llm_suggested_metric_chain_text\n"
        "- llm_notes (brief justification)\n\n"

        "====================\n"
        "OUTPUT FORMAT\n"
        "====================\n"
        "Return ONLY JSON with:\n"
        "- llm_suggested_metric_chain_text\n"
        "- llm_suggested_formula_text\n"
        "- llm_notes\n\n"

        "====================\n"
        "FORMULA RULES\n"
        "====================\n"
        "- Use ONLY assignment lines: variable = expression\n"
        "- Use lower_snake_case variable names\n"
        "- Allowed operations: +, -, *, /, parentheses, min(), max()\n"
        "- DO NOT write explanations inside formula_text\n"
        "- Final output MUST include:\n"
        "    value = <delta impact on KPI>\n\n"

        "====================\n"
        "QUALITY BAR\n"
        "====================\n"
        "This model must be realistic, causal, and usable by a product & finance team.\n"
        "It should clearly explain HOW the initiative changes the KPI.\n\n"

        "In llm_notes:\n"
        "- State which KPI you selected as Target KPI if it was not explicitly provided\n"
        "- Explain briefly why it is the correct business outcome metric\n\n"

        "====================\n"
        "EXAMPLE (IMPORTANT)\n"
        "====================\n"
        "Initiative: Improve checkout UX\n\n"

        "Metric chain:\n"
        "checkout_conversion_rate → completed_transactions → GMV\n\n"

        "Formula:\n"
        "delta_checkout_conversion = improvement_in_conversion_rate\n"
        "delta_transactions = traffic * delta_checkout_conversion\n"
        "delta_gmv = delta_transactions * average_order_value\n"
        "value = delta_gmv\n"
    )


def _build_user_prompt(payload: MathModelPromptInput) -> str:
    lines = [
        f"Initiative: {payload.initiative_key} - {payload.title}",
    ]

    def add(label: str, val: Optional[str]) -> None:
        if val:
            lines.append(f"{label}: {val}")

    target_kpi = payload.target_kpi_key

    if target_kpi:
        add("Target KPI", target_kpi)
    else:
        lines.append("Target KPI: NOT PROVIDED")
        lines.append("→ You MUST select the appropriate target KPI from KPI definitions.")

    add("Immediate KPI", payload.immediate_kpi_key)

    if payload.target_kpi_key is None:
        lines.append(
            "⚠️ WARNING: No explicit target KPI provided. You must infer the final KPI from context."
        )

    if target_kpi:
        lines.append(
            f"→ Your goal is to model the DELTA (change) in '{target_kpi}' caused by this initiative."
        )
        lines.append(
            f"→ The final 'value' must represent delta in '{target_kpi}'."
        )

    if payload.immediate_kpi_key and payload.immediate_kpi_key != target_kpi:
        lines.append(
            f"→ '{payload.immediate_kpi_key}' is the first KPI directly affected by the initiative and should be treated as an upstream driver, not the final value output."
        )

    lines.append("\n=== TASK ===")
    lines.append(
        "Build a delta-based causal model that quantifies how this initiative changes the target KPI."
    )

    lines.append("\n=== THINKING FRAMEWORK ===")
    lines.append(
        "- What behavior does this initiative change?\n"
        "- Which metric changes first?\n"
        "- How does that change propagate to the target KPI?\n"
        "- What measurable deltas occur?\n"
        "- How do these deltas combine into final impact?"
    )

    if payload.metric_chain_text:
        add("Existing metric chain", payload.metric_chain_text)
        lines.append("→ You may refine or improve this chain if needed.")
    else:
        lines.append("If no metric chain is provided, you MUST explicitly construct one before writing formulas.")

    add("Problem", payload.problem_statement)
    add("Hypothesis", payload.hypothesis)
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
        lines.append("\n=== KPI DEFINITIONS ===")
        lines.append(payload.metrics_config_text)
    if payload.metrics_config_json:
        lines.append("\n=== KPI DEFINITIONS JSON ===")
        lines.append(json.dumps(payload.metrics_config_json, ensure_ascii=True, indent=2))
        lines.append("\n=== TARGET KPI SELECTION INSTRUCTION ===")
        lines.append(
            "If Target KPI is not explicitly given:\n"
            "→ Select the most appropriate KPI from the provided KPI definitions\n"
            "→ Prefer North Star or Strategic KPIs\n"
            "→ Ensure the final 'value' represents impact on that KPI"
        )

    lines.append("\n=== IMPORTANT CONSTRAINTS ===")
    lines.append(
        "- Model ONLY impact (delta), NOT absolute values\n"
        "- DO NOT include effort, cost, or ROI\n"
        "- Use real business metrics (conversion, GMV, transactions, etc.)\n"
        "- Ensure clear causal logic\n"
        "- Final output must define: value = delta impact on KPI"
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


def _build_math_model_evaluator_system_prompt() -> str:
    return (
        "You are a senior product economist reviewing mathematical KPI models.\n\n"
        "Your task is to evaluate the quality of a causal, delta-based model for a product initiative.\n\n"
        "Evaluate the model across these dimensions:\n"
        "1. Causal correctness\n"
        "2. KPI alignment\n"
        "3. Delta integrity\n"
        "4. Metric realism\n"
        "5. Logical completeness\n"
        "6. Simplicity and clarity\n\n"
        "SCORING GUIDE:\n"
        "- 90 to 100: excellent, production-ready\n"
        "- 75 to 89: good, minor improvements needed\n"
        "- 50 to 74: weak, needs revision\n"
        "- below 50: incorrect or misleading\n\n"
        "VERDICT RULES:\n"
        "- accept: only if the model is causally correct and value clearly represents delta impact on the right target KPI\n"
        "- needs_revision: if the model is partially correct but improvable\n"
        "- reject: if the model is materially wrong, misleading, or not usable\n\n"
        "IMPORTANT:\n"
        "- If no explicit target KPI was provided in the prompt, assess whether the selected target KPI is appropriate\n"
        "- Check whether the formula follows the metric chain\n"
        "- If metric chain exists: each step in the chain MUST appear in the formula; missing steps are a critical issue\n"
        "- Check whether 'value' depends on delta variables and represents final business impact\n"
        "- Do not evaluate implementation effort, ROI, engineering cost, or delivery complexity\n\n"
        "Return ONLY JSON with keys:\n"
        "{\n"
        '  "score": number,\n'
        '  "verdict": "accept" | "needs_revision" | "reject",\n'
        '  "issues": [string],\n'
        '  "strengths": [string],\n'
        '  "suggested_improvements": [string],\n'
        '  "selected_target_kpi": string | null,\n'
        '  "target_kpi_reasoning": string | null\n'
        "}"
    )


def _build_math_model_evaluator_user_prompt(
    payload: MathModelPromptInput,
    suggestion: MathModelSuggestion,
) -> str:
    lines = [
        f"Initiative: {payload.initiative_key} - {payload.title}",
        f"Explicit Target KPI: {payload.target_kpi_key or 'NOT PROVIDED'}",
        f"Immediate KPI: {payload.immediate_kpi_key or 'NOT PROVIDED'}",
        "",
        "Context:",
    ]

    if payload.problem_statement:
        lines.append(f"Problem: {payload.problem_statement}")
    if payload.hypothesis:
        lines.append(f"Hypothesis: {payload.hypothesis}")
    if payload.expected_impact_description:
        lines.append(f"Expected impact: {payload.expected_impact_description}")
    if payload.metric_chain_text:
        lines.append(f"Input metric chain: {payload.metric_chain_text}")
    if payload.metrics_config_text:
        lines.append("KPI definitions:")
        lines.append(payload.metrics_config_text)
    if payload.metrics_config_json:
        lines.append("Structured KPI definitions JSON:")
        lines.append(json.dumps(payload.metrics_config_json, ensure_ascii=True, indent=2))

    lines.extend(
        [
            "",
            "Model to evaluate:",
            f"Suggested metric chain: {suggestion.llm_suggested_metric_chain_text or 'NONE'}",
            "Suggested formula:",
            suggestion.llm_suggested_formula_text,
            f"LLM notes: {suggestion.llm_notes or 'NONE'}",
        ]
    )

    return "\n".join(lines)


def _build_math_model_revision_system_prompt() -> str:
    return (
        "You are a senior product economist revising a causal, delta-based mathematical model.\n\n"
        "You will be given:\n"
        "- the original initiative context\n"
        "- a weak model suggestion\n"
        "- an evaluation report describing issues\n\n"
        "Your job is to produce an improved version of the model.\n\n"
        "RULES:\n"
        "- Keep the model causal and delta-based\n"
        "- Ensure value represents delta impact on the final target KPI\n"
        "- If a metric chain is present, ensure the formula follows it\n"
        "- Use only real business metrics\n"
        "- Do not include effort, cost, ROI, or implementation complexity\n"
        "- Use only assignment lines in formula_text\n"
        "- Use lower_snake_case\n"
        "- Allowed operations: +, -, *, /, parentheses, min(), max()\n\n"
        "Return ONLY JSON with keys:\n"
        "- llm_suggested_metric_chain_text\n"
        "- llm_suggested_formula_text\n"
        "- llm_notes"
    )


def _build_math_model_revision_user_prompt(
    payload: MathModelPromptInput,
    suggestion: MathModelSuggestion,
    evaluation: MathModelEvaluation,
) -> str:
    lines = [
        f"Initiative: {payload.initiative_key} - {payload.title}",
        f"Explicit Target KPI: {payload.target_kpi_key or 'NOT PROVIDED'}",
        f"Immediate KPI: {payload.immediate_kpi_key or 'NOT PROVIDED'}",
    ]

    if payload.metric_chain_text:
        lines.append(f"Input metric chain: {payload.metric_chain_text}")

    if payload.problem_statement:
        lines.append(f"Problem: {payload.problem_statement}")
    if payload.hypothesis:
        lines.append(f"Hypothesis: {payload.hypothesis}")
    if payload.expected_impact_description:
        lines.append(f"Expected impact: {payload.expected_impact_description}")
    if payload.metrics_config_text:
        lines.append("KPI definitions:")
        lines.append(payload.metrics_config_text)
    if payload.metrics_config_json:
        lines.append("Structured KPI definitions JSON:")
        lines.append(json.dumps(payload.metrics_config_json, ensure_ascii=True, indent=2))

    lines.extend(
        [
            "",
            "Original suggestion:",
            f"Metric chain: {suggestion.llm_suggested_metric_chain_text or 'NONE'}",
            "Formula:",
            suggestion.llm_suggested_formula_text,
            "",
            "Evaluation feedback:",
            f"Score: {evaluation.score}",
            f"Verdict: {evaluation.verdict}",
            f"Issues: {evaluation.issues}",
            f"Suggested improvements: {evaluation.suggested_improvements}",
            "",
            "Revise the model so it becomes stronger, more causal, and better aligned to the correct target KPI.",
        ]
    )

    return "\n".join(lines)


def _build_initiative_summary_system_prompt() -> str:
    return (
        "You are a senior product strategist writing concise initiative summaries for a central backlog.\n\n"
        "Your job is to synthesize initiative context into a clear PM-facing summary.\n\n"
        "RULES:\n"
        "- Use only the provided context\n"
        "- Be concrete and business-facing, not generic\n"
        "- If an approved math model is provided, use it to ground expected impact\n"
        "- If the math model is unclear, incomplete, or ambiguous, say that explicitly\n"
        "- Do NOT interpret a formula beyond the information explicitly provided\n"
        "- Do not invent metrics, dependencies, or risks\n"
        "- Put uncertainties in open_questions instead of stating them as facts\n"
        "- Keep each field concise and useful for backlog review\n\n"
        "Return ONLY JSON with keys:\n"
        "{\n"
        '  "headline": string,\n'
        '  "opportunity": string,\n'
        '  "proposed_solution": string,\n'
        '  "expected_impact": string,\n'
        '  "math_model_basis": string | null,\n'
        '  "risks_and_dependencies": [string],\n'
        '  "open_questions": [string]\n'
        "}"
    )


def _build_initiative_summary_user_prompt(payload: InitiativeSummaryPromptInput) -> str:
    lines = [
        f"Initiative: {payload.initiative_key} - {payload.title}",
    ]

    def add(label: str, value: Optional[str]) -> None:
        if value:
            lines.append(f"{label}: {value}")

    add("Requesting team", payload.requesting_team)
    add("Product area", payload.product_area)
    add("Customer segment", payload.customer_segment)
    add("Initiative type", payload.initiative_type)
    add("Immediate KPI", payload.immediate_kpi_key)
    add("Problem statement", payload.problem_statement)
    add("Hypothesis", payload.hypothesis)
    add("Sheet description", payload.sheet_description)
    add("Dependencies", payload.dependencies_others)
    add("Risk description", payload.risk_description)

    if payload.approved_math_model:
        lines.append("Approved math model:")
        add("- Model name", payload.approved_math_model.model_name)
        add("- Target KPI", payload.approved_math_model.target_kpi_key)
        add("- Metric chain", payload.approved_math_model.metric_chain_text)
        add("- Formula", payload.approved_math_model.formula_text)
        add("- Assumptions", payload.approved_math_model.assumptions_text)
        add("- Model description", payload.approved_math_model.model_description_free_text)
    else:
        lines.append("Approved math model: NONE")

    if payload.llm_context_text:
        lines.append("Additional company context:")
        lines.append(payload.llm_context_text)

    lines.extend(
        [
            "",
            "Write a structured initiative summary that helps a PM quickly understand the opportunity, proposed solution, expected business impact, and what still needs clarification.",
        ]
    )
    return "\n".join(lines)


__all__ = ["LLMClient", "build_constructed_math_model_prompt"]
