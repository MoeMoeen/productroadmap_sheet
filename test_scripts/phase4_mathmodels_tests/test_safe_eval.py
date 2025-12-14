# productroadmap_sheet_project/test_scripts/phase4_mathmodels_tests/test_safe_eval.py

from __future__ import annotations

import pytest

from app.utils.safe_eval import (
    SafeEvalError,
    evaluate_script,
    extract_identifiers,
    validate_formula,
)


def test_extract_identifiers_excludes_lhs_and_builtins():
    script = """
ticket_savings = ticket_reduction_per_month * cost_per_ticket * horizon_months
value = ticket_savings + min(churn_reduction, 1) * affected_customers * customer_lifetime_value - total_cost
"""
    ids = extract_identifiers(script)
    assert set(ids) == {
        "ticket_reduction_per_month",
        "cost_per_ticket",
        "horizon_months",
        "churn_reduction",
        "affected_customers",
        "customer_lifetime_value",
        "total_cost",
    }


def test_evaluate_script_happy_path():
    script = """
ticket_savings = ticket_reduction_per_month * cost_per_ticket * horizon_months
value = ticket_savings - total_cost
overall = value
"""
    env = evaluate_script(
        script,
        initial_env={
            "ticket_reduction_per_month": 10,
            "cost_per_ticket": 5,
            "horizon_months": 6,
            "total_cost": 100,
        },
    )
    assert env["ticket_savings"] == 10 * 5 * 6
    assert env["value"] == env["ticket_savings"] - 100
    assert env["overall"] == env["value"]


def test_evaluate_script_rejects_imports_and_attr():
    bad_scripts = [
        "x = __import__('os').system('echo nope')",
        "x = (1).__class__",
        "x = foo.bar",
    ]
    for s in bad_scripts:
        with pytest.raises(SafeEvalError):
            evaluate_script(s, initial_env={})


def test_evaluate_script_timeout_for_long_input():
    # Simulate by many sequential assignments; timeout kept small
    script = "\n".join([f"x{i} = {i}+1" for i in range(5000)])
    with pytest.raises(SafeEvalError):
        evaluate_script(script, initial_env={}, timeout_secs=0.001)


def test_validate_formula_line_limit_and_value_requirement():
    too_long = "\n".join([f"x{i} = {i}" for i in range(12)])
    errors = validate_formula(too_long, max_lines=10)
    assert any("exceeds" in e for e in errors)

    missing_value = "a = 1\nb = 2"
    errors = validate_formula(missing_value)
    assert any("value" in e for e in errors)


def test_validate_formula_good_script():
    script = """
# comment
a = 1
b = 2
value = a + b
"""
    errors = validate_formula(script)
    assert errors == []
