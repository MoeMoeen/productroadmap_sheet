"""Tests for sheet readers and writers (Step 3)."""

import pytest
from unittest.mock import Mock, MagicMock, patch, ANY

from app.sheets.models import MathModelRow, ParamRow
from app.sheets.math_models_reader import MathModelsReader
from app.sheets.math_models_writer import MathModelsWriter
from app.sheets.params_reader import ParamsReader
from app.sheets.params_writer import ParamsWriter


class TestMathModelRow:
    """Test MathModelRow pydantic model."""
    
    def test_math_model_row_creation(self):
        """Test creating a MathModelRow with all fields."""
        row = MathModelRow(
            initiative_key="INIT-001",
            formula_text="value = uplift * sessions * margin",
            parameters_json='{"uplift": 0.15, "sessions": 1000, "margin": 0.3}',
            assumptions_text="Assumes 15% uplift in conversion",
            suggested_by_llm=True,
            approved_by_user=False,
            llm_suggested_formula_text="value = uplift * sessions",
            llm_notes="Conservative estimate",
        )
        
        assert row.initiative_key == "INIT-001"
        assert row.formula_text is not None and "uplift" in row.formula_text
        assert row.suggested_by_llm is True
        assert row.approved_by_user is False
    
    def test_math_model_row_optional_fields(self):
        """Test MathModelRow with minimal required fields."""
        row = MathModelRow(initiative_key="INIT-001")
        
        assert row.initiative_key == "INIT-001"
        assert row.formula_text is None
        assert row.parameters_json is None


class TestParamRow:
    """Test ParamRow pydantic model."""
    
    def test_param_row_creation(self):
        """Test creating a ParamRow with all fields."""
        row = ParamRow(
            initiative_key="INIT-001",
            param_name="conversion_uplift",
            value="0.15",
            unit="percentage",
            display="Conversion Uplift",
            description="Expected uplift in conversion rate",
            source="analytics",
            approved=True,
            is_auto_seeded=False,
            framework="MATH_MODEL",
        )
        
        assert row.param_name == "conversion_uplift"
        assert row.value == "0.15"
        assert row.approved is True
        assert row.framework == "MATH_MODEL"
    
    def test_param_row_default_framework(self):
        """Test ParamRow defaults framework to MATH_MODEL."""
        row = ParamRow(initiative_key="INIT-001", param_name="test")
        
        assert row.framework == "MATH_MODEL"


class TestMathModelsReader:
    """Test MathModelsReader."""
    
    def test_get_rows_for_sheet_empty(self):
        """Test reader with empty sheet."""
        mock_client = Mock()
        mock_client.get_sheet_grid_size.return_value = (1, 5)
        mock_client.get_values.return_value = []
        
        reader = MathModelsReader(mock_client)
        rows = reader.get_rows_for_sheet("sheet_id", "MathModels")
        
        assert rows == []
    
    def test_get_rows_for_sheet_with_data(self):
        """Test reader with data rows."""
        mock_client = Mock()
        mock_client.get_sheet_grid_size.return_value = (100, 10)
        mock_client.get_values.return_value = [
            ["initiative_key", "formula_text", "parameters_json", "assumptions_text", "suggested_by_llm"],
            ["INIT-001", "value = uplift * 1000", '{"uplift": 0.15}', "Assumes 15% uplift", True],
            ["INIT-002", "value = base * factor", '{"base": 100, "factor": 2}', "", False],
        ]
        
        reader = MathModelsReader(mock_client)
        rows = reader.get_rows_for_sheet("sheet_id", "MathModels")
        
        assert len(rows) == 2
        
        row_num_1, model_1 = rows[0]
        assert row_num_1 == 2
        assert model_1.initiative_key == "INIT-001"
        assert model_1.suggested_by_llm is True
        
        row_num_2, model_2 = rows[1]
        assert row_num_2 == 3
        assert model_2.initiative_key == "INIT-002"
    
    def test_get_rows_skips_empty_rows(self):
        """Test that reader skips completely empty rows."""
        mock_client = Mock()
        mock_client.get_sheet_grid_size.return_value = (100, 5)
        mock_client.get_values.return_value = [
            ["initiative_key", "formula_text"],
            ["INIT-001", "formula1"],
            ["", ""],  # Empty row
            ["INIT-002", "formula2"],
        ]
        
        reader = MathModelsReader(mock_client)
        rows = reader.get_rows_for_sheet("sheet_id", "MathModels")
        
        assert len(rows) == 2
        assert rows[0][1].initiative_key == "INIT-001"
        assert rows[1][1].initiative_key == "INIT-002"


class TestMathModelsWriter:
    """Test MathModelsWriter."""
    
    def test_write_formula_suggestion(self):
        """Test writing a single formula suggestion."""
        mock_client = Mock()
        mock_client.get_values.return_value = [
            ["initiative_key", "llm_suggested_formula_text", "llm_notes"]
        ]
        
        writer = MathModelsWriter(mock_client)
        writer.write_formula_suggestion(
            "sheet_id",
            "MathModels",
            row_number=2,
            llm_suggested_formula_text="suggested_formula",
        )
        
        mock_client.update_values.assert_called_once()
        call_args = mock_client.update_values.call_args
        assert "MathModels!B2" in call_args.kwargs["range_"]
        assert call_args.kwargs["values"] == [["suggested_formula"]]
    
    def test_write_suggestions_batch(self):
        """Test batch writing suggestions."""
        mock_client = Mock()
        mock_client.get_values.return_value = [
            ["initiative_key", "llm_suggested_formula_text", "llm_notes"]
        ]
        
        writer = MathModelsWriter(mock_client)
        suggestions = [
            {
                "row_number": 2,
                "llm_suggested_formula_text": "formula1",
                "llm_notes": "assumptions1",
            },
            {
                "row_number": 3,
                "llm_suggested_formula_text": "formula2",
                "llm_notes": None,
            },
        ]
        
        writer.write_suggestions_batch("sheet_id", "MathModels", suggestions)
        
        mock_client.batch_update_values.assert_called_once()
        call_args = mock_client.batch_update_values.call_args
        assert len(call_args.kwargs["data"]) >= 2


class TestParamsReader:
    """Test ParamsReader."""
    
    def test_get_rows_for_sheet_empty(self):
        """Test reader with empty sheet."""
        mock_client = Mock()
        mock_client.get_sheet_grid_size.return_value = (1, 5)
        mock_client.get_values.return_value = []
        
        reader = ParamsReader(mock_client)
        rows = reader.get_rows_for_sheet("sheet_id", "Params")
        
        assert rows == []
    
    def test_get_rows_for_sheet_with_data(self):
        """Test reader with parameter data."""
        mock_client = Mock()
        mock_client.get_sheet_grid_size.return_value = (100, 10)
        mock_client.get_values.return_value = [
            ["initiative_key", "param_name", "value", "unit", "approved"],
            ["INIT-001", "conversion_uplift", "0.15", "pct", True],
            ["INIT-001", "session_count", "1000", "count", False],
        ]
        
        reader = ParamsReader(mock_client)
        rows = reader.get_rows_for_sheet("sheet_id", "Params")
        
        assert len(rows) == 2
        
        row_num_1, param_1 = rows[0]
        assert row_num_1 == 2
        assert param_1.param_name == "conversion_uplift"
        assert param_1.value == "0.15"
        
        row_num_2, param_2 = rows[1]
        assert row_num_2 == 3
        assert param_2.param_name == "session_count"
    
    def test_get_rows_with_column_name_aliases(self):
        """Test that reader handles column name aliases."""
        mock_client = Mock()
        mock_client.get_sheet_grid_size.return_value = (100, 10)
        mock_client.get_values.return_value = [
            ["initiative_key", "parameter_name", "value", "display_name"],
            ["INIT-001", "param1", "100", "Parameter 1"],
        ]
        
        reader = ParamsReader(mock_client)
        rows = reader.get_rows_for_sheet("sheet_id", "Params")
        
        assert len(rows) == 1
        row_num, param = rows[0]
        assert param.param_name == "param1"
        assert param.display == "Parameter 1"


class TestParamsWriter:
    """Test ParamsWriter."""
    
    def test_append_parameters(self):
        """Test appending new parameters."""
        mock_client = Mock()
        mock_client.get_values.return_value = [
            ["initiative_key", "param_name", "value", "framework"]
        ]
        mock_client.get_sheet_grid_size.return_value = (2, 4)
        
        writer = ParamsWriter(mock_client)
        params = [
            {
                "initiative_key": "INIT-001",
                "param_name": "uplift",
                "value": "0.15",
                "framework": "MATH_MODEL",
            },
            {
                "initiative_key": "INIT-001",
                "param_name": "sessions",
                "value": "1000",
                "framework": "MATH_MODEL",
            },
        ]
        
        writer.append_parameters("sheet_id", "Params", params)
        
        mock_client.update_values.assert_called_once()
        call_args = mock_client.update_values.call_args
        assert call_args.kwargs["values"]  # Should have rows to append
    
    @patch('app.sheets.params_writer.ParamsWriter._find_column_index')
    def test_update_parameter_value_not_approved(self, mock_find_col):
        """Test updating a parameter value when not approved."""
        mock_client = Mock()
        
        # Mock column finding
        mock_find_col.side_effect = [
            3,  # approved_col_idx
            2,  # value_col_idx
            9,  # auto_seeded_col_idx (in second call to _find_column_index)
        ]
        
        # Mock get_values for approved status check
        mock_client.get_values.return_value = [[False]]
        
        writer = ParamsWriter(mock_client)
        writer.update_parameter_value("sheet_id", "Params", row_number=2, value="0.20")
        
        # Should call update_values for the value update
        assert mock_client.update_values.call_count >= 1
    
    def test_update_parameter_value_already_approved(self):
        """Test that approved parameters are not updated."""
        mock_client = Mock()
        
        # Get header
        # Check approved flag (returns True)
        mock_client.get_values.side_effect = [
            [["initiative_key", "value", "approved"]],  # header
            [[True]],  # approved status
        ]
        
        writer = ParamsWriter(mock_client)
        writer.update_parameter_value("sheet_id", "Params", row_number=2, value="0.20")
        
        # Should not call update_values for the value
        # (only called for getting header/approved status)
        assert not mock_client.update_values.called or len(
            mock_client.update_values.call_args_list
        ) == 0
    
    def test_update_parameters_batch(self):
        """Test batch updating parameters."""
        mock_client = Mock()
        mock_client.get_values.side_effect = [
            [["value"]],  # value column
            [["approved"]],  # approved column
            [["is_auto_seeded"]],  # auto_seeded column
            # For each approved check:
            [[False]],  # row 2 not approved
            [[False]],  # row 3 not approved
        ]
        
        writer = ParamsWriter(mock_client)
        updates = [
            {"row_number": 2, "value": "0.20", "is_auto_seeded": True},
            {"row_number": 3, "value": "2000", "is_auto_seeded": False},
        ]
        
        writer.update_parameters_batch("sheet_id", "Params", updates)
        
        mock_client.batch_update_values.assert_called_once()


class TestIntegration:
    """Integration tests for reader/writer patterns."""
    
    def test_read_then_write_workflow(self):
        """Test complete workflow: read data, then write suggestions."""
        mock_client = Mock()
        
        # Setup for reader
        mock_client.get_sheet_grid_size.return_value = (100, 8)
        mock_client.get_values.side_effect = [
            # Reader gets MathModels
            [
                ["initiative_key", "formula_text", "llm_suggested_formula_text"],
                ["INIT-001", None, None],
                ["INIT-002", None, None],
            ],
            # Writer gets header for suggestions
            [["initiative_key", "formula_text", "llm_suggested_formula_text"]],
        ]
        
        reader = MathModelsReader(mock_client)
        models = reader.get_rows_for_sheet("sheet_id", "MathModels")
        
        assert len(models) == 2
        
        writer = MathModelsWriter(mock_client)
        suggestions = [
            {"row_number": 2, "llm_suggested_formula_text": "suggested_formula_1"},
            {"row_number": 3, "llm_suggested_formula_text": "suggested_formula_2"},
        ]
        writer.write_suggestions_batch("sheet_id", "MathModels", suggestions)
        
        assert mock_client.batch_update_values.called
