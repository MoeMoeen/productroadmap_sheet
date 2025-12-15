# Tests for MathModelScoringEngine compute()
import sys
from pathlib import Path

# Ensure project root on sys.path for `app` imports
project_root = Path(__file__).parents[2]
sys.path.insert(0, str(project_root))

from app.services.scoring import ScoringFramework, get_engine
from app.services.scoring.interfaces import ScoreInputs


def test_math_model_engine_happy_path():
    engine = get_engine(ScoringFramework.MATH_MODEL)
    script = """
value = traffic * rate
# effort is provided by formula as well
effort = eng_days
"""
    inputs = ScoreInputs(
        extra={
            "use_math_model": True,
            "formula_text": script,
            "math_model_approved": True,
            "math_model_llm_suggested": False,
            "params_env": {"traffic": 1000.0, "rate": 0.02, "eng_days": 5.0},
            "effort_engineering_days": None,
        }
    )

    res = engine.compute(inputs)

    assert res.value_score == 20.0
    assert res.effort_score == 5.0
    assert res.overall_score == 4.0
    assert res.warnings == []
    assert "env_inputs" in res.components and "env_outputs" in res.components


def test_math_model_engine_missing_param():
    engine = get_engine(ScoringFramework.MATH_MODEL)
    script = """
value = traffic * rate
"""
    inputs = ScoreInputs(
        extra={
            "use_math_model": True,
            "formula_text": script,
            "math_model_approved": True,
            "params_env": {"traffic": 1000.0},
            "effort_engineering_days": None,
        }
    )

    res = engine.compute(inputs)
    assert any("missing approved parameters" in w for w in res.warnings)


def test_math_model_engine_invalid_formula():
    engine = get_engine(ScoringFramework.MATH_MODEL)
    # non-assignment should be rejected
    script = "max(1,2)"  # not an assignment line
    inputs = ScoreInputs(
        extra={
            "use_math_model": True,
            "formula_text": script,
            "math_model_approved": True,
            "params_env": {},
        }
    )

    res = engine.compute(inputs)
    assert any("invalid" in w.lower() or "only assignment" in w.lower() for w in res.warnings)


def test_math_model_engine_llm_warning():
    engine = get_engine(ScoringFramework.MATH_MODEL)
    script = "value = 1\n"
    inputs = ScoreInputs(
        extra={
            "use_math_model": True,
            "formula_text": script,
            "math_model_approved": True,
            "math_model_llm_suggested": True,
            "params_env": {},
            "effort_engineering_days": 2.0,
        }
    )

    res = engine.compute(inputs)
    assert any("suggested by LLM" in w for w in res.warnings)
