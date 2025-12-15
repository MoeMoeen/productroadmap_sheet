# productroadmap_sheet_project/app/services/scoring/engines/math_model.py

from __future__ import annotations

from typing import Dict

from app.services.scoring.interfaces import ScoringEngine, ScoringFramework, ScoreInputs, ScoreResult
from app.utils.safe_eval import SafeEvalError, evaluate_script, extract_identifiers, validate_formula


class MathModelScoringEngine:
    """Scoring engine for custom math models using safe_eval."""

    framework = ScoringFramework.MATH_MODEL

    def compute(self, inputs: ScoreInputs) -> ScoreResult:
        extras = inputs.extra or {}

        use_math_model = extras.get("use_math_model", False)
        if not use_math_model:
            return ScoreResult(warnings=["Math model disabled on initiative"], components={})

        formula_text = extras.get("formula_text")
        model_approved = extras.get("math_model_approved", False)
        llm_suggested = extras.get("math_model_llm_suggested", False)
        effort_fallback = extras.get("effort_engineering_days")
        env: Dict[str, float] = extras.get("params_env", {}) or {}

        if not formula_text:
            return ScoreResult(warnings=["Math model missing or empty formula"], components={})

        if not model_approved:
            return ScoreResult(warnings=["Math model not approved"], components={})

        validation_errors = validate_formula(formula_text)
        if validation_errors:
            return ScoreResult(warnings=[f"Math model invalid: {'; '.join(validation_errors)}"], components={})

        required_params = extract_identifiers(formula_text)
        missing = [p for p in required_params if p not in env]
        if missing:
            return ScoreResult(
                warnings=[f"Math model missing approved parameters: {', '.join(missing)}"],
                components={"missing_params": missing},
            )

        try:
            final_env = evaluate_script(formula_text, env, timeout_secs=5.0)
        except SafeEvalError as exc:
            return ScoreResult(warnings=[f"Math model error: {exc}"], components={})

        value_score = final_env.get("value")
        if value_score is None:
            return ScoreResult(warnings=["Math model did not assign 'value'"], components={})

        effort_score = final_env.get("effort")
        if effort_score is None:
            effort_score = effort_fallback

        overall_score = final_env.get("overall")
        if overall_score is None and value_score is not None and effort_score not in (None, 0):
            try:
                overall_score = value_score / effort_score
            except Exception:
                overall_score = None

        components: Dict[str, object] = {
            "env_inputs": env,
            "env_outputs": final_env,
            "formula": formula_text,
        }

        warnings = []
        if llm_suggested:
            warnings.append("Math model suggested by LLM")

        return ScoreResult(
            value_score=value_score,
            effort_score=effort_score,
            overall_score=overall_score,
            components=components,
            warnings=warnings,
        )


__all__ = ["MathModelScoringEngine"]