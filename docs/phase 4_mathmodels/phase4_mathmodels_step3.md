# Step 3: Sheets Integration (MathModels & Params Readers/Writers)

**Status**: ✅ COMPLETE - All 17 tests passing

## Overview

Step 3 implements the data flow between the ProductOps Google Sheet and the database. Two main components:

1. **Readers** (MathModelsReader, ParamsReader): Pull data from sheets and convert to Pydantic models
2. **Writers** (MathModelsWriter, ParamsWriter): Push suggestions/updates back to sheets with safety constraints

## Files Created

### 1. `app/sheets/models.py` (NEW)
**Purpose**: Define Pydantic row models for sheet data
- `MathModelRow`: Represents a single MathModel row from the MathModels tab
- `ParamRow`: Represents a single parameter row from the Params tab
- Both use `ConfigDict(extra="ignore")` for Pydantic v2 compliance

**Key Fields**:
- MathModelRow: initiative_id, formula_text, parameters_json, assumptions_text, suggested_by_llm, approved_by_user, formula_suggestion, assumptions_suggestion
- ParamRow: initiative_id, param_name, value, unit, display, description, source, approved, is_auto_seeded, framework

### 2. `app/sheets/math_models_reader.py` (POPULATED)
**Purpose**: Read MathModels tab from ProductOps sheet
- `MathModelsReader.get_rows_for_sheet()`: Returns list of (row_number, MathModelRow) tuples
- Handles empty rows, header normalization, column aliases
- Returns rows as (row_number, model) pairs for easy back-reference to sheet
- Safe parsing with error logging (doesn't fail on malformed rows)

**Key Methods**:
- `get_rows_for_sheet()`: Main API, reads entire tab
- `_row_to_dict()`: Maps cell values to dict based on headers
- `_is_empty_row()`: Skips completely empty rows

### 3. `app/sheets/math_models_writer.py` (POPULATED)
**Purpose**: Write LLM suggestions to MathModels tab
- Populates `formula_suggestion` and `assumptions_suggestion` columns
- Never overwrites user-approved cells (safety constraint)
- Supports both single updates and batch operations

**Key Methods**:
- `write_formula_suggestion()`: Write single formula suggestion
- `write_assumptions_suggestion()`: Write single assumptions suggestion
- `write_suggestions_batch()`: Batch write multiple suggestions in one API call
- `_find_column_index()`: Helper to locate columns by header name

**Safety Constraints**:
- Only writes to suggestion columns (separate from user-editable columns)
- Never updates formula_text, assumptions_text if approved_by_user is True

### 4. `app/sheets/params_reader.py` (POPULATED)
**Purpose**: Read Params tab from ProductOps sheet
- `ParamsReader.get_rows_for_sheet()`: Returns list of (row_number, ParamRow) tuples
- Handles flexible column naming (e.g., "param_name" or "parameter_name")
- Parses all metadata fields (unit, display, description, source)

**Key Methods**:
- `get_rows_for_sheet()`: Main API
- `_row_to_dict()`: Maps with alias support
- Column name aliases:
  - param_name ← parameter_name
  - display ← display_name
  - description ← notes
  - is_auto_seeded ← auto_seeded

### 5. `app/sheets/params_writer.py` (POPULATED)
**Purpose**: Write parameters to Params tab with append-only strategy

**Concurrency Strategy** (CRITICAL):
- Never deletes existing rows
- Only updates `value` if `approved` flag is False
- Tracks `is_auto_seeded` flag for each parameter
- Prevents data loss from concurrent PM editing

**Key Methods**:
- `append_parameters()`: Add new param rows to sheet
- `update_parameter_value()`: Update a param value (checks approved status first)
- `update_parameters_batch()`: Batch update multiple values
- `_find_column_index()`: Locate columns by header
- `_build_column_indices()`: Build mapping of column names to positions
- `_build_row()`: Construct row in correct column order

**Rules**:
1. Never delete rows (append-only)
2. Only update value if not approved
3. Only update metadata on new rows
4. Track is_auto_seeded to identify auto-generated params

### 6. `test_scripts/phase4_mathmodels_tests/test_sheet_readers_writers.py` (NEW)
**Purpose**: Comprehensive test coverage for readers/writers

**Test Classes** (17 tests total, all passing):

1. **TestMathModelRow** (2 tests)
   - test_math_model_row_creation: All fields
   - test_math_model_row_optional_fields: Minimal fields

2. **TestParamRow** (2 tests)
   - test_param_row_creation: All fields
   - test_param_row_default_framework: Defaults framework to "MATH_MODEL"

3. **TestMathModelsReader** (3 tests)
   - test_get_rows_for_sheet_empty: Empty sheet handling
   - test_get_rows_for_sheet_with_data: Full data parsing
   - test_get_rows_skips_empty_rows: Empty row filtering

4. **TestMathModelsWriter** (2 tests)
   - test_write_formula_suggestion: Single formula write
   - test_write_suggestions_batch: Batch write operation

5. **TestParamsReader** (3 tests)
   - test_get_rows_for_sheet_empty: Empty sheet handling
   - test_get_rows_for_sheet_with_data: Full data parsing
   - test_get_rows_with_column_name_aliases: Alias handling

6. **TestParamsWriter** (3 tests)
   - test_append_parameters: Appending new rows
   - test_update_parameter_value_not_approved: Update when not approved
   - test_update_parameter_value_already_approved: Skip update when approved
   - test_update_parameters_batch: Batch update with approval checks

7. **TestIntegration** (1 test)
   - test_read_then_write_workflow: Complete read→write cycle

## Test Results

```
✅ TestMathModelRow::test_math_model_row_creation PASSED
✅ TestMathModelRow::test_math_model_row_optional_fields PASSED
✅ TestParamRow::test_param_row_creation PASSED
✅ TestParamRow::test_param_row_default_framework PASSED
✅ TestMathModelsReader::test_get_rows_for_sheet_empty PASSED
✅ TestMathModelsReader::test_get_rows_for_sheet_with_data PASSED
✅ TestMathModelsReader::test_get_rows_skips_empty_rows PASSED
✅ TestMathModelsWriter::test_write_formula_suggestion PASSED
✅ TestMathModelsWriter::test_write_suggestions_batch PASSED
✅ TestParamsReader::test_get_rows_for_sheet_empty PASSED
✅ TestParamsReader::test_get_rows_for_sheet_with_data PASSED
✅ TestParamsReader::test_get_rows_with_column_name_aliases PASSED
✅ TestParamsWriter::test_append_parameters PASSED
✅ TestParamsWriter::test_update_parameter_value_not_approved PASSED
✅ TestParamsWriter::test_update_parameter_value_already_approved PASSED
✅ TestParamsWriter::test_update_parameters_batch PASSED
✅ TestIntegration::test_read_then_write_workflow PASSED

17 passed in 0.99s
```

## Architecture Patterns

### Reader Pattern
```python
reader = MathModelsReader(client)
rows = reader.get_rows_for_sheet(spreadsheet_id, tab_name)
# Returns: List[(row_number, MathModelRow), ...]

for row_num, model in rows:
    # row_num can be used to reference back to sheet
    # model is fully typed Pydantic object
    process(model)
```

### Writer Pattern
```python
writer = MathModelsWriter(client)
# Single write
writer.write_formula_suggestion(spreadsheet_id, tab_name, row_number=2, formula_suggestion="...")

# Batch write (more efficient)
suggestions = [
    {"row_number": 2, "formula_suggestion": "formula1"},
    {"row_number": 3, "formula_suggestion": "formula2"},
]
writer.write_suggestions_batch(spreadsheet_id, tab_name, suggestions)
```

### Append-Only Params Pattern
```python
params_writer = ParamsWriter(client)

# Add new parameters (append to end)
new_params = [
    {"initiative_id": 1, "param_name": "uplift", "value": "0.15", "framework": "MATH_MODEL"},
]
params_writer.append_parameters(spreadsheet_id, tab_name, new_params)

# Update existing parameter (only if not approved)
params_writer.update_parameter_value(spreadsheet_id, tab_name, row_number=5, value="0.20")

# Batch updates with approval checking
updates = [
    {"row_number": 5, "value": "0.20", "is_auto_seeded": False},
    {"row_number": 6, "value": "1500", "is_auto_seeded": False},
]
params_writer.update_parameters_batch(spreadsheet_id, tab_name, updates)
```

## Integration Points

### With Previous Steps
- Uses `SheetsClient` from `app/sheets/client.py` (existing)
- Uses `ProductOpsConfig` from `app/config.py` (Step 1)
- Reads/writes to tabs configured in `product_ops_config.json`
- Uses header normalization from `app/utils/header_utils.py` (existing)

### With Future Steps
- **Step 4 (LLM Integration)**: ParamsWriter and MathModelsWriter will be called with LLM suggestions
- **Step 5 (Formula Parser)**: Will parse formulas from MathModelsReader output
- **Step 6 (Scoring Engine)**: Will read parameters from ParamsReader output

## Key Design Decisions

1. **Separate Suggestion Columns**: LLM suggestions go to formula_suggestion/assumptions_suggestion, not overwriting user edits
2. **Row-Number Tracking**: Return (row_number, model) tuples so writers can update the exact sheet row
3. **Append-Only Params**: Never delete or modify existing params, only add new ones or update unapproved values
4. **Header Flexibility**: Support column name aliases for user convenience
5. **Error Tolerance**: Readers log errors but don't fail (continue processing other rows)
6. **Batch Operations**: Writers support both single and batch updates for efficiency

## Next Steps

**Step 4: LLM Integration**
- Create `MathModelScoringAssistant` to generate formula and parameter suggestions
- Use LLM to extract parameters from formula text
- Call `MathModelsWriter` to write suggestions back to sheet

**Step 5: Formula Parser**
- Implement `extract_identifiers()` using AST parsing
- Implement `evaluate_script()` using asteval
- Validate formulas before approval

**Step 6: Scoring Engine**
- Read approved formulas from MathModelsReader
- Read parameter values from ParamsReader
- Evaluate formulas and write scores back to Initiative

## Dependencies

- Google Sheets API (via SheetsClient)
- Pydantic v2 (ConfigDict for validation)
- pytest + unittest.mock (for tests)
- logging (for error/debug output)
