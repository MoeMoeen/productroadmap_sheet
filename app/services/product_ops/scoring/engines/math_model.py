# productroadmap_sheet_project/app/services/scoring/engines/math_model.py

from __future__ import annotations

from typing import Dict, Optional

from app.services.product_ops.scoring.interfaces import ScoringEngine, ScoringFramework, ScoreInputs, ScoreResult
from app.utils.safe_eval import SafeEvalError, evaluate_script, extract_identifiers, validate_formula


class MathModelScoringEngine:
    """Scoring engine for custom math models using safe_eval."""

    framework = ScoringFramework.MATH_MODEL

    def score_single_model(
        self,
        formula_text: str,
        params_env: Dict[str, float],
        approved_by_user: bool = False,
        effort_fallback: Optional[float] = None,
    ) -> ScoreResult:
        """
        Score a single math model formula.
        
        Args:
            formula_text: Formula to evaluate
            params_env: Parameter environment dict
            approved_by_user: Whether formula is approved
            effort_fallback: Fallback effort value if not in formula
        
        Returns:
            ScoreResult with value_score (computed impact for this model)
        """
        if not formula_text:
            return ScoreResult(warnings=["Math model missing or empty formula"], components={})

        if not approved_by_user:
            return ScoreResult(warnings=["Math model not approved"], components={})

        validation_errors = validate_formula(formula_text)
        if validation_errors:
            return ScoreResult(warnings=[f"Math model invalid: {'; '.join(validation_errors)}"], components={})

        required_params = extract_identifiers(formula_text)
        missing = [p for p in required_params if p not in params_env]
        if missing:
            return ScoreResult(
                warnings=[f"Math model missing approved parameters: {', '.join(missing)}"],
                components={"missing_params": missing},
            )

        try:
            final_env = evaluate_script(formula_text, params_env, timeout_secs=5.0)
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
            "env_inputs": params_env,
            "env_outputs": final_env,
            "formula": formula_text,
        }

        return ScoreResult(
            value_score=value_score,
            effort_score=effort_score,
            overall_score=overall_score,
            components=components,
            warnings=[],
        )

    def compute(self, inputs: ScoreInputs) -> ScoreResult:
        """
        Compute scores using math model formula from inputs.
        
        Delegates to score_single_model() for actual scoring logic.
        This is the ScoringFramework interface method for representative model scoring.
        """
        extras = inputs.extra or {}

        use_math_model = extras.get("use_math_model", False)
        if not use_math_model:
            return ScoreResult(warnings=["Math model disabled on initiative"], components={})

        formula_text = extras.get("formula_text")
        model_approved = extras.get("math_model_approved", False)
        llm_suggested = extras.get("math_model_llm_suggested", False)
        effort_fallback = extras.get("effort_engineering_days")
        params_env: Dict[str, float] = extras.get("params_env", {}) or {}

        # Delegate to single-model scorer
        result = self.score_single_model(
            formula_text=formula_text or "",
            params_env=params_env,
            approved_by_user=model_approved,
            effort_fallback=effort_fallback,
        )

        # Add LLM provenance warning if needed
        if llm_suggested and not result.warnings:
            result.warnings.append("Math model suggested by LLM")
        elif llm_suggested:
            # Prepend LLM warning if other warnings exist
            result.warnings = ["Math model suggested by LLM"] + result.warnings

        return result


__all__ = ["MathModelScoringEngine"]