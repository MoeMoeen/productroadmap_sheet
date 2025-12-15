# Tests for ScoringService with Math Model integration
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure project root on sys.path for `app` imports
project_root = Path(__file__).parents[2]
sys.path.insert(0, str(project_root))

from app.db.base import Base
from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeMathModel, InitiativeParam
from app.services.scoring.interfaces import ScoringFramework
from app.services.scoring_service import ScoringService


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed_initiative_with_math_model(db):
    init = Initiative(
        initiative_key="INIT-1",
        title="Test Initiative",
        use_math_model=True,
        effort_engineering_days=5.0,
    )
    model = InitiativeMathModel(
        formula_text="""
value = traffic * rate
# let effort fall back from initiative
""".strip(),
        suggested_by_llm=False,
        approved_by_user=True,
    )
    init.math_model = model
    db.add(init)
    db.flush()

    # Approved params
    db.add_all(
        [
            InitiativeParam(
                initiative_id=init.id,
                framework=ScoringFramework.MATH_MODEL.value,
                param_name="traffic",
                value=1000.0,
                approved=True,
            ),
            InitiativeParam(
                initiative_id=init.id,
                framework=ScoringFramework.MATH_MODEL.value,
                param_name="rate",
                value=0.02,
                approved=True,
            ),
        ]
    )
    db.flush()
    return init


def test_service_populates_math_fields_without_activation():
    db = make_session()
    init = seed_initiative_with_math_model(db)

    svc = ScoringService(db)
    # Do NOT activate; should only update math_* fields
    svc.score_initiative(init, ScoringFramework.MATH_MODEL, activate=False)

    db.refresh(init)
    assert init.math_value_score == 20.0  # type: ignore
    # effort falls back to initiative when not provided by formula
    assert init.math_effort_score == 5.0  # type: ignore
    assert init.value_score is None  # not activated
    assert init.active_scoring_framework is None


def test_service_activation_updates_active_fields():
    db = make_session()
    init = seed_initiative_with_math_model(db)
    svc = ScoringService(db)
    svc.score_initiative(init, ScoringFramework.MATH_MODEL, activate=True)

    db.refresh(init)
    assert init.value_score == init.math_value_score  # type: ignore
    assert init.active_scoring_framework == ScoringFramework.MATH_MODEL.value  # type: ignore
