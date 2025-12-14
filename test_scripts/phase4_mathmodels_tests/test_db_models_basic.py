from datetime import datetime, timezone
from app.db.models import Initiative, InitiativeMathModel, InitiativeParam
from app.schemas.initiative import InitiativeRead
from app.schemas.scoring import InitiativeMathModelRead, InitiativeParamRead

def test_initiative_math_fields_present():
    init = Initiative(
        id=1,
        initiative_key="INIT-TEST",
        title="Test Initiative",
        status="new",
        strategic_priority_coefficient=1.0,
        is_mandatory=False,
        score_llm_suggested=False,
        score_approved_by_user=False,
        use_math_model=True,
        math_value_score=10.0,
        math_effort_score=2.0,
        math_overall_score=5.0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    data = InitiativeRead.model_validate(init)
    assert data.math_value_score == 10.0
    assert data.math_effort_score == 2.0
    assert data.math_overall_score == 5.0


def test_initiative_param_schema():
    p = InitiativeParam(
        id=1,
        initiative_id=1,
        framework="MATH_MODEL",
        param_name="uplift_conv",
        value=0.12,
        approved=True,
        is_auto_seeded=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    s = InitiativeParamRead.model_validate(p)
    assert s.framework == "MATH_MODEL"
    assert s.param_name == "uplift_conv"
    assert s.value == 0.12
    assert s.approved is True


def test_initiative_math_model_schema():
    m = InitiativeMathModel(
        id=1,
        framework="MATH_MODEL",
        formula_text="value = uplift_conv * sessions * margin",
        suggested_by_llm=True,
        approved_by_user=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    s = InitiativeMathModelRead.model_validate(m)
    assert s.framework == "MATH_MODEL"
    assert "value" in s.formula_text
    assert s.suggested_by_llm is True