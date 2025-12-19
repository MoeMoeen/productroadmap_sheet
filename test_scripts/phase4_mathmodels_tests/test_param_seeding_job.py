# productroadmap_sheet_project/test_scripts/phase4_mathmodels_tests/test_param_seeding_job.py

"""Unit tests for param seeding job (Step 8).

Tests with mocked LLM and sheets clients to verify:
- Skip unapproved rows
- Skip when no missing identifiers
- Append only missing params
- Set flags: approved=False, is_auto_seeded=True, framework=MATH_MODEL
- Respect max_llm_calls limit
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.jobs.param_seeding_job import run_param_seeding_job, ParamSeedingStats
from app.llm.models import ParamMetadataSuggestion, ParamSuggestion
from app.sheets.models import MathModelRow, ParamRow


@pytest.fixture
def mock_llm_client():
    """Mock LLM client that returns fake param metadata."""
    client = MagicMock()
    
    def mock_suggest(initiative_key: str, identifiers: list[str], formula_text: str = ""):
        params = [
            ParamSuggestion(
                key=ident,
                name=ident.replace("_", " ").title(),
                description=f"Description for {ident}",
                unit="count",
                example_value="100",
                source_hint="analytics",
            )
            for ident in identifiers
        ]
        return ParamMetadataSuggestion(
            initiative_key=initiative_key,
            identifiers=identifiers,
            params=params,
        )
    
    client.suggest_param_metadata.side_effect = mock_suggest
    return client


@pytest.fixture
def mock_sheets_client():
    """Mock sheets client."""
    return MagicMock()


def test_seed_params_skips_unapproved_mathmodel(mock_llm_client, mock_sheets_client):
    """Test that seeding skips unapproved MathModels rows."""
    
    # Mock MathModelsReader to return unapproved row
    math_rows = [
        (2, MathModelRow(
            initiative_key="INIT-001",
            formula_text="value = x + y",
            approved_by_user=False,
        ))
    ]
    
    # Mock ParamsReader to return no existing params
    param_rows = []
    
    with patch("app.jobs.param_seeding_job.MathModelsReader") as MockMathReader, \
         patch("app.jobs.param_seeding_job.ParamsReader") as MockParamsReader, \
         patch("app.jobs.param_seeding_job.ParamsWriter") as MockParamsWriter:
        
        MockMathReader.return_value.get_rows_for_sheet.return_value = math_rows
        MockParamsReader.return_value.get_rows_for_sheet.return_value = param_rows
        
        stats = run_param_seeding_job(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test-sheet",
            mathmodels_tab="MathModels",
            params_tab="Params",
            llm_client=mock_llm_client,
        )
        
        assert stats.rows_scanned_mathmodelstab == 1
        assert stats.skipped_row_mathmodeltab_unapproved == 1
        assert stats.llm_calls == 0
        assert stats.seeded_params_paramsstab == 0


def test_seed_params_skips_when_no_missing_identifiers(mock_llm_client, mock_sheets_client):
    """Test that seeding skips when all identifiers already exist in Params."""
    
    # Mock MathModelsReader to return approved row with formula
    math_rows = [
        (2, MathModelRow(
            initiative_key="INIT-001",
            formula_text="value = x + y",
            approved_by_user=True,
        ))
    ]
    
    # Mock ParamsReader to return existing params for x and y
    param_rows = [
        (2, ParamRow(initiative_key="INIT-001", framework="MATH_MODEL", param_name="x", value=10)),
        (3, ParamRow(initiative_key="INIT-001", framework="MATH_MODEL", param_name="y", value=20)),
    ]
    
    with patch("app.jobs.param_seeding_job.MathModelsReader") as MockMathReader, \
         patch("app.jobs.param_seeding_job.ParamsReader") as MockParamsReader, \
         patch("app.jobs.param_seeding_job.ParamsWriter") as MockParamsWriter:
        
        MockMathReader.return_value.get_rows_for_sheet.return_value = math_rows
        MockParamsReader.return_value.get_rows_for_sheet.return_value = param_rows
        
        stats = run_param_seeding_job(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test-sheet",
            mathmodels_tab="MathModels",
            params_tab="Params",
            llm_client=mock_llm_client,
        )
        
        assert stats.rows_scanned_mathmodelstab == 1
        assert stats.skipped_row_mathmodeltab_no_missing == 1
        assert stats.llm_calls == 0
        assert stats.seeded_params_paramsstab == 0


def test_seed_params_appends_only_missing_rows(mock_llm_client, mock_sheets_client):
    """Test that seeding appends only missing identifiers."""
    
    # Mock MathModelsReader to return approved row with formula
    math_rows = [
        (2, MathModelRow(
            initiative_key="INIT-001",
            formula_text="value = x + y + z",
            approved_by_user=True,
        ))
    ]
    
    # Mock ParamsReader to return existing param for x only (y and z are missing)
    param_rows = [
        (2, ParamRow(initiative_key="INIT-001", framework="MATH_MODEL", param_name="x", value=10)),
    ]
    
    with patch("app.jobs.param_seeding_job.MathModelsReader") as MockMathReader, \
         patch("app.jobs.param_seeding_job.ParamsReader") as MockParamsReader, \
         patch("app.jobs.param_seeding_job.ParamsWriter") as MockParamsWriter:
        
        MockMathReader.return_value.get_rows_for_sheet.return_value = math_rows
        MockParamsReader.return_value.get_rows_for_sheet.return_value = param_rows
        mock_writer = MockParamsWriter.return_value
        
        stats = run_param_seeding_job(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test-sheet",
            mathmodels_tab="MathModels",
            params_tab="Params",
            llm_client=mock_llm_client,
        )
        
        assert stats.rows_scanned_mathmodelstab == 1
        assert stats.eligible_rows_mathmodelstab == 1
        assert stats.llm_calls == 1
        assert stats.seeded_params_paramsstab == 2  # y and z
        
        # Verify append_new_params was called with only missing identifiers
        mock_writer.append_new_params.assert_called_once()
        call_args = mock_writer.append_new_params.call_args
        params_appended = call_args.kwargs["params"]
        
        assert len(params_appended) == 2
        param_names = {p["param_name"] for p in params_appended}
        assert param_names == {"y", "z"}


def test_seed_params_sets_flags_approved_false_auto_seeded_true(mock_llm_client, mock_sheets_client):
    """Test that seeded params have approved=False and is_auto_seeded=True."""
    
    # Mock MathModelsReader to return approved row with formula
    math_rows = [
        (2, MathModelRow(
            initiative_key="INIT-001",
            formula_text="value = x",
            approved_by_user=True,
        ))
    ]
    
    # Mock ParamsReader to return no existing params
    param_rows = []
    
    with patch("app.jobs.param_seeding_job.MathModelsReader") as MockMathReader, \
         patch("app.jobs.param_seeding_job.ParamsReader") as MockParamsReader, \
         patch("app.jobs.param_seeding_job.ParamsWriter") as MockParamsWriter:
        
        MockMathReader.return_value.get_rows_for_sheet.return_value = math_rows
        MockParamsReader.return_value.get_rows_for_sheet.return_value = param_rows
        mock_writer = MockParamsWriter.return_value
        
        stats = run_param_seeding_job(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test-sheet",
            mathmodels_tab="MathModels",
            params_tab="Params",
            llm_client=mock_llm_client,
        )
        
        assert stats.seeded_params_paramsstab == 1
        
        # Verify flags
        call_args = mock_writer.append_new_params.call_args
        params_appended = call_args.kwargs["params"]
        
        assert len(params_appended) == 1
        param = params_appended[0]
        assert param["approved"] is False
        assert param["is_auto_seeded"] is True


def test_seed_params_uses_framework_math_model(mock_llm_client, mock_sheets_client):
    """Test that seeded params use framework='MATH_MODEL'."""
    
    # Mock MathModelsReader to return approved row with formula
    math_rows = [
        (2, MathModelRow(
            initiative_key="INIT-001",
            formula_text="value = x",
            approved_by_user=True,
        ))
    ]
    
    # Mock ParamsReader to return no existing params
    param_rows = []
    
    with patch("app.jobs.param_seeding_job.MathModelsReader") as MockMathReader, \
         patch("app.jobs.param_seeding_job.ParamsReader") as MockParamsReader, \
         patch("app.jobs.param_seeding_job.ParamsWriter") as MockParamsWriter:
        
        MockMathReader.return_value.get_rows_for_sheet.return_value = math_rows
        MockParamsReader.return_value.get_rows_for_sheet.return_value = param_rows
        mock_writer = MockParamsWriter.return_value
        
        stats = run_param_seeding_job(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test-sheet",
            mathmodels_tab="MathModels",
            params_tab="Params",
            llm_client=mock_llm_client,
        )
        
        assert stats.seeded_params_paramsstab == 1
        
        # Verify framework
        call_args = mock_writer.append_new_params.call_args
        params_appended = call_args.kwargs["params"]
        
        assert len(params_appended) == 1
        param = params_appended[0]
        assert param["framework"] == "MATH_MODEL"


def test_seed_params_respects_max_llm_calls(mock_llm_client, mock_sheets_client):
    """Test that seeding respects max_llm_calls limit."""
    
    # Mock MathModelsReader to return 5 approved rows, each needing LLM call
    math_rows = [
        (i, MathModelRow(
            initiative_key=f"INIT-{i:03d}",
            formula_text=f"value = x{i}",
            approved_by_user=True,
        ))
        for i in range(1, 6)
    ]
    
    # Mock ParamsReader to return no existing params
    param_rows = []
    
    with patch("app.jobs.param_seeding_job.MathModelsReader") as MockMathReader, \
         patch("app.jobs.param_seeding_job.ParamsReader") as MockParamsReader, \
         patch("app.jobs.param_seeding_job.ParamsWriter") as MockParamsWriter:
        
        MockMathReader.return_value.get_rows_for_sheet.return_value = math_rows
        MockParamsReader.return_value.get_rows_for_sheet.return_value = param_rows
        
        stats = run_param_seeding_job(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test-sheet",
            mathmodels_tab="MathModels",
            params_tab="Params",
            llm_client=mock_llm_client,
            max_llm_calls=3,  # Limit to 3 calls
        )
        
        # Job breaks after hitting max_llm_calls, so rows_scanned will be 4 (3 processed + 1 that triggered break)
        assert stats.rows_scanned_mathmodelstab >= 3
        assert stats.llm_calls == 3  # Should stop at limit
        assert stats.seeded_params_paramsstab == 3  # Only 3 params seeded


def test_seed_params_skips_rows_with_no_identifiers(mock_llm_client, mock_sheets_client):
    """Test that seeding skips rows with no identifiers in formula."""
    
    # Mock MathModelsReader to return approved row with no variables (just constants)
    math_rows = [
        (2, MathModelRow(
            initiative_key="INIT-001",
            formula_text="value = 42",
            approved_by_user=True,
        ))
    ]
    
    # Mock ParamsReader to return no existing params
    param_rows = []
    
    with patch("app.jobs.param_seeding_job.MathModelsReader") as MockMathReader, \
         patch("app.jobs.param_seeding_job.ParamsReader") as MockParamsReader, \
         patch("app.jobs.param_seeding_job.ParamsWriter") as MockParamsWriter, \
         patch("app.jobs.param_seeding_job.SheetsClient", return_value=mock_sheets_client):
        
        MockMathReader.return_value.get_rows_for_sheet.return_value = math_rows
        MockParamsReader.return_value.get_rows_for_sheet.return_value = param_rows
        
        stats = run_param_seeding_job(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test-sheet",
            mathmodels_tab="MathModels",
            params_tab="Params",
            llm_client=mock_llm_client,
        )
        
        assert stats.rows_scanned_mathmodelstab == 1
        assert stats.skipped_row_mathmodeltab_no_identifiers == 1
        assert stats.llm_calls == 0
        assert stats.seeded_params_paramsstab == 0
