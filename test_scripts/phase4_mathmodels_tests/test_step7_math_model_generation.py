# productroadmap_sheet_project/test_scripts/phase4_mathmodels_tests/test_step7_math_model_generation.py
# Tests for Step 7: Math Model suggestion generation
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Ensure project root on sys.path
project_root = Path(__file__).parents[2]
sys.path.insert(0, str(project_root))

from app.db.models.initiative import Initiative
from app.sheets.models import MathModelRow
from app.llm.models import MathModelPromptInput, MathModelSuggestion
from app.llm.scoring_assistant import suggest_math_model_for_initiative
from app.jobs.math_model_generation_job import needs_suggestion, run_math_model_generation_job


def test_needs_suggestion_approved_skipped():
    """Row with approved_by_user=True should be skipped."""
    row = MathModelRow(
        initiative_key="INIT-1",
        approved_by_user=True,
        model_description_free_text="Some description",
    )
    assert needs_suggestion(row) is False


def test_needs_suggestion_no_description_skipped():
    """Row with no description should be skipped."""
    row = MathModelRow(
        initiative_key="INIT-1",
        approved_by_user=False,
        model_description_free_text=None,
        model_prompt_to_llm=None,
    )
    assert needs_suggestion(row) is False


def test_needs_suggestion_has_existing_skipped():
    """Row with existing suggestion (no force) should be skipped."""
    row = MathModelRow(
        initiative_key="INIT-1",
        approved_by_user=False,
        model_description_free_text="Some description",
        llm_suggested_formula_text="value = x + y",
    )
    assert needs_suggestion(row, force=False) is False
    assert needs_suggestion(row, force=True) is True


def test_needs_suggestion_eligible():
    """Row with description but no approval/suggestion should be eligible."""
    row = MathModelRow(
        initiative_key="INIT-1",
        approved_by_user=False,
        model_description_free_text="Some description",
        llm_suggested_formula_text=None,
    )
    assert needs_suggestion(row) is True


def test_suggest_math_model_for_initiative():
    """Test helper builds prompt input and calls LLM."""
    init = Initiative(
        initiative_key="INIT-1",
        title="Test",
        problem_statement="A problem",
        desired_outcome="An outcome",
        llm_summary="Summary",
        expected_impact_description="Impact",
        impact_metric="metric_x",
        impact_unit="units",
    )

    row = MathModelRow(
        initiative_key="INIT-1",
        model_name="Model A",
        model_description_free_text="Describe the model",
        model_prompt_to_llm="Extra instructions",
    )

    mock_llm = Mock()
    mock_suggestion = MathModelSuggestion(
        formula_text="value = x * y",
        assumptions=["assume A", "assume B"],
        notes="Some notes",
    )
    mock_llm.suggest_math_model.return_value = mock_suggestion

    result = suggest_math_model_for_initiative(init, row, mock_llm)

    assert result.formula_text == "value = x * y"
    assert result.assumptions == ["assume A", "assume B"]
    assert result.notes == "Some notes"

    # Verify LLM was called with a properly built payload
    mock_llm.suggest_math_model.assert_called_once()
    call_arg = mock_llm.suggest_math_model.call_args[0][0]
    assert isinstance(call_arg, MathModelPromptInput)
    assert call_arg.initiative_key == "INIT-1"
    assert call_arg.title == "Test"
    assert call_arg.model_description_free_text == "Describe the model"


def test_run_math_model_generation_job_stats():
    """Test job counts stats correctly."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.base import Base

    # Create in-memory DB
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Create test initiatives
    for key in ["INIT-1", "INIT-2", "INIT-3"]:
        init = Initiative(initiative_key=key, title=f"Init {key}")
        db.add(init)
    db.commit()

    # Mock reader to return specific rows
    mock_reader = Mock()
    mock_rows = [
        (2, MathModelRow(initiative_key="INIT-1", approved_by_user=True, model_description_free_text="desc")),  # skipped: approved
        (3, MathModelRow(initiative_key="INIT-2", approved_by_user=False, model_description_free_text=None)),  # skipped: no desc
        (4, MathModelRow(initiative_key="INIT-3", approved_by_user=False, model_description_free_text="desc", llm_suggested_formula_text="value = x")),  # skipped: has suggestion
        (5, MathModelRow(initiative_key="INIT-MISSING", approved_by_user=False, model_description_free_text="desc")),  # skipped: missing init
    ]
    mock_reader.get_rows_for_sheet.return_value = mock_rows

    mock_sheets_client = Mock()
    mock_llm = Mock()
    mock_writer = Mock()

    with patch("app.jobs.math_model_generation_job.MathModelsReader", return_value=mock_reader):
        with patch("app.jobs.math_model_generation_job.MathModelsWriter", return_value=mock_writer):
            result = run_math_model_generation_job(
                db=db,
                sheets_client=mock_sheets_client,
                llm_client=mock_llm,
                spreadsheet_id="sheet_id",
                tab_name="MathModels",
            )

    assert result["rows"] == 4
    assert result["suggested"] == 0
    assert result["skipped_approved"] == 1
    assert result["skipped_no_desc"] == 1
    assert result["skipped_has_suggestion"] == 1
    assert result["skipped_missing_initiative"] == 1


def test_run_math_model_generation_job_suggests():
    """Test job actually suggests when row is eligible."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.base import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    init = Initiative(initiative_key="INIT-1", title="Test Initiative")
    db.add(init)
    db.commit()

    mock_reader = Mock()
    mock_row = MathModelRow(
        initiative_key="INIT-1",
        approved_by_user=False,
        model_description_free_text="A description",
    )
    mock_reader.get_rows_for_sheet.return_value = [(2, mock_row)]

    mock_sheets_client = Mock()
    mock_llm = Mock()
    mock_suggestion = MathModelSuggestion(
        formula_text="value = x + y",
        assumptions=["A1", "A2"],
        notes="Note",
    )
    mock_llm.suggest_math_model.return_value = mock_suggestion

    mock_writer = Mock()

    with patch("app.jobs.math_model_generation_job.MathModelsReader", return_value=mock_reader):
        with patch("app.jobs.math_model_generation_job.MathModelsWriter", return_value=mock_writer):
            with patch("app.jobs.math_model_generation_job.suggest_math_model_for_initiative", return_value=mock_suggestion):
                result = run_math_model_generation_job(
                    db=db,
                    sheets_client=mock_sheets_client,
                    llm_client=mock_llm,
                    spreadsheet_id="sheet_id",
                    tab_name="MathModels",
                )

    assert result["suggested"] == 1

    # Verify writer was called with correct suggestion
    mock_writer.write_suggestions_batch.assert_called_once()
    call_args = mock_writer.write_suggestions_batch.call_args
    suggestions = call_args[1]["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["row_number"] == 2
    assert suggestions[0]["llm_suggested_formula_text"] == "value = x + y"
    assert suggestions[0]["assumptions_text"] == "A1\nA2"
    assert suggestions[0]["llm_notes"] == "Note"
