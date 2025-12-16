# Phase 4: Math Model Scoring - Operational Runbook

**Status**: Production-Ready (Phase 4 Complete)  
**Audience**: Product Managers, Operations Team  
**Last Updated**: 16 December 2025

---

## Overview

Phase 4 enables **custom math model scoring** where PMs define formulas (e.g., `value = sessions * conversion_rate * revenue_per_user`) and the system:
1. Parses formulas and extracts parameter identifiers
2. Prompts PM to fill parameter values
3. Evaluates formulas to compute `math_value_score` and `math_effort_score`
4. Stores scores alongside RICE/WSJF for comparison

**Integration Point**: Math model scores compete with RICE/WSJF via `active_scoring_framework` field.

---

## Daily Operations (Standard Flow)

### 1. Sync inputs from ProductOps → DB
```bash
uv run python -m test_scripts.flow3_product_ops_cli --sync --log-level INFO
```
**What it does**: Reads ProductOps Scoring_Inputs tab and updates DB with:
- `active_scoring_framework` (RICE | WSJF | MATH_MODEL)
- Framework inputs (rice_reach, wsjf_business_value, etc.)
- `use_math_model` flag

**Duration**: ~10 seconds for 100 initiatives

---

### 2. Compute all framework scores (RICE + WSJF + MATH_MODEL)
```bash
uv run python -m test_scripts.flow3_product_ops_cli --compute-all --log-level INFO
```
**What it does**:
- RICE: Computes `rice_value_score`, `rice_effort_score`, `rice_overall_score`
- WSJF: Computes `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`
- MATH_MODEL: Evaluates custom formulas → `math_value_score`, `math_effort_score`, `math_overall_score`
- Stores all per-framework scores in DB (does NOT overwrite active scores)

**Duration**: ~30 seconds for 100 initiatives

---

### 3. Write scores back to ProductOps Scoring tab
```bash
uv run python -m test_scripts.flow3_product_ops_cli --write-scores --log-level INFO
```
**What it does**: Updates ProductOps sheet columns:
- `rice_value_score`, `rice_effort_score`, `rice_overall_score`
- `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`
- `math_value_score`, `math_effort_score`, `math_overall_score`
- `math_warnings` (empty if successful, error messages if formula/params incomplete)

**Duration**: ~15 seconds for 100 initiatives

**PM Action Required**: Review scores in ProductOps sheet and set `active_scoring_framework` per initiative.

---

### 4. PM Action: Choose Active Framework
In ProductOps **Scoring_Inputs** tab:
- Compare `rice_overall_score` vs `wsjf_overall_score` vs `math_overall_score`
- Set `active_scoring_framework` to desired framework:
  - `RICE` - Classic reach × impact × confidence / effort
  - `WSJF` - Cost of delay / job size
  - `MATH_MODEL` - Custom formula defined in MathModels tab

**Tips**:
- Use `math_warnings` column to check if math model is ready (empty = good)
- Filter by `use_math_model=TRUE` to find candidates for math scoring
- Can mix frameworks: some initiatives use RICE, others use MATH_MODEL

---

### 5. Activate chosen framework scores
```bash
uv run python -m test_scripts.flow2_scoring_cli --all --log-level INFO
```
**What it does**: Reads `active_scoring_framework` from DB and copies per-framework scores to active fields:
- `value_score` ← `rice_value_score` OR `wsjf_value_score` OR `math_value_score`
- `effort_score` ← framework-specific effort
- `overall_score` ← framework-specific overall

**Duration**: ~5 seconds for 100 initiatives

---

### 6. Sync active scores to Central Backlog
```bash
uv run python -m test_scripts.backlog_sync_cli --log-level INFO
```
**What it does**: Writes active scores from DB to Central Backlog sheet:
- `value_score`, `effort_score`, `overall_score`
- `active_scoring_framework` label

**Duration**: ~20 seconds for 100 initiatives

**Result**: Central Backlog now reflects PM's chosen scoring framework per initiative.

---

## Math Model Workflow (One-Time Per Initiative)

### Setup Phase

#### 1. PM writes model in MathModels tab
**Manual Steps**:
- Add new row with `initiative_key` (e.g., `INIT-001`)
- Fill `model_description_free_text`: Plain English description of the model logic
  - Example: "User sessions multiplied by conversion rate and revenue per conversion"
- Write formula in `formula_text`:
  ```python
  value = sessions * conv_rate * revenue_per_conversion
  effort = eng_days
  ```
  **Constraints**:
  - Must assign `value` (required)
  - Can optionally assign `effort`
  - Use Python syntax (basic arithmetic, no functions)
  - Identifiers become parameter names
- Set `approved_by_user = TRUE` to enable scoring

**System Columns** (read-only, managed by system):
- `model_name`: Auto-generated (e.g., `INIT-001_v1`)
- `suggested_by_llm`: TRUE if LLM-generated
- `llm_suggested_formula_text`: LLM suggestion (if Step 7 ran)
- `llm_notes`: LLM rationale

---

#### 2. System suggests formula (optional)
```bash
uv run python -m test_scripts.flow4_mathmodels_cli --suggest-mathmodels --limit 10 --max-llm-calls 10 --log-level INFO
```
**What it does**:
- Reads initiatives where `use_math_model=TRUE` AND `approved_by_user=FALSE`
- Sends initiative context to LLM (gpt-4o)
- LLM writes suggested formula to `llm_suggested_formula_text` and notes to `llm_notes`

**PM Action**: Review suggestions and either:
- Copy `llm_suggested_formula_text` → `formula_text` (then set `approved_by_user=TRUE`)
- Write your own formula in `formula_text` and approve
- Reject by leaving `approved_by_user=FALSE`

**Flags**:
- `--limit N`: Max initiatives to suggest for (default: 10)
- `--max-llm-calls N`: Safety cap on API calls (default: 10)
- `--force`: Re-suggest even if already suggested

**Cost**: ~$0.02 per initiative (gpt-4o API)

---

#### 3. Seed parameter rows
```bash
uv run python -m test_scripts.flow4_mathmodels_cli --seed-params --limit 50 --max-llm-calls 20 --log-level INFO
```
**What it does**:
- Reads approved formulas from MathModels tab
- Extracts identifiers (e.g., `sessions`, `conv_rate`, `revenue_per_conversion`)
- Appends rows to **Params** tab with:
  - `initiative_key`, `framework=MATH_MODEL`, `param_name` (e.g., `sessions`)
  - `is_auto_seeded=TRUE`
  - Metadata from LLM: `param_display`, `description`, `unit`, `min`, `max`, `source`

**PM Action**: None required yet (seeding is automatic)

**Flags**:
- `--limit N`: Max initiatives to seed params for (default: 50)
- `--max-llm-calls N`: Safety cap on API calls (default: 20)
- `--force`: Re-seed even if params already exist

**Cost**: ~$0.001 per initiative (gpt-4o-mini API)

---

#### 4. PM fills parameter values
**Manual Steps** (in **Params** tab):
- Find rows for your `initiative_key` with `framework=MATH_MODEL`
- Fill `value` column with actual numbers:
  - `sessions` → `10000`
  - `conv_rate` → `0.05`
  - `revenue_per_conversion` → `100`
- Set `approved = TRUE` when confident
- Optional: Add notes in `notes` column

**System Columns** (read-only):
- `initiative_key`, `framework`, `param_name`, `is_auto_seeded`
- `param_display`, `description`, `unit`, `min`, `max`, `source` (LLM-provided metadata)

**Editable Columns**:
- `value` - The numeric value to use in formula
- `approved` - TRUE/FALSE flag
- `notes` - Freeform PM notes

---

### Scoring Phase

#### 5. Compute math model scores
```bash
uv run python -m test_scripts.flow3_product_ops_cli --compute-all --log-level INFO
uv run python -m test_scripts.flow3_product_ops_cli --write-scores --log-level INFO
```
**What it does**:
- Evaluates approved formulas with approved parameter values
- Writes results to DB:
  - `math_value_score` - Result of `value = ...` expression
  - `math_effort_score` - Result of `effort = ...` expression (if present)
  - `math_overall_score` - Computed as `value / effort` (if both present)
  - `math_warnings` - Error messages if formula/params incomplete
- Writes scores back to ProductOps sheet

**Success Indicators**:
- `math_value_score` populated (non-zero)
- `math_warnings` empty
- `math_overall_score` computed

**Common Warnings**:
- `"Missing params: x, y"` → Fill those params in Params tab and approve
- `"Formula not approved"` → Set `approved_by_user=TRUE` in MathModels tab
- `"Division by zero"` → Check effort value (cannot be 0)
- `"Syntax error"` → Fix formula_text syntax

---

#### 6. Activate math model
**Manual Steps**:
- In ProductOps **Scoring_Inputs** tab, set `active_scoring_framework = MATH_MODEL`
- Verify `math_warnings` is empty
- Run activation flow:
  ```bash
  uv run python -m test_scripts.flow3_product_ops_cli --sync --log-level INFO
  uv run python -m test_scripts.flow2_scoring_cli --all --log-level INFO
  uv run python -m test_scripts.backlog_sync_cli --log-level INFO
  ```

**Result**: Central Backlog now shows `math_overall_score` as active score for this initiative.

---

## Troubleshooting

### Problem: `math_warnings` shows "Missing params: x, y"
**Cause**: Formula references parameters that don't have values or aren't approved.

**Solution**:
1. Go to **Params** tab
2. Find rows for your `initiative_key` with `framework=MATH_MODEL`
3. Fill `value` column for the missing parameters
4. Set `approved = TRUE`
5. Re-run compute: `uv run python -m test_scripts.flow3_product_ops_cli --compute-all`

---

### Problem: `math_overall_score` is blank
**Possible Causes**:
1. Formula not approved in MathModels tab
2. Parameters missing/not approved in Params tab
3. Formula has syntax errors

**Diagnostic Steps**:
1. Check **MathModels** tab: `approved_by_user = TRUE`?
2. Check **Params** tab: All params have `value` and `approved = TRUE`?
3. Check `math_warnings` column in Scoring_Inputs tab for specific error
4. Check logs for syntax errors: `--log-level DEBUG`

---

### Problem: LLM suggestions aren't appearing
**Possible Causes**:
1. `OPENAI_API_KEY` not set in environment
2. Initiative doesn't have `use_math_model=TRUE`
3. Formula already approved (`approved_by_user=TRUE`)

**Solution**:
1. Verify environment: `echo $OPENAI_API_KEY`
2. Check Scoring_Inputs tab: `use_math_model` column should be TRUE
3. Use `--force` flag to re-suggest: `--suggest-mathmodels --force`
4. Check logs for API errors: `--log-level DEBUG`

---

### Problem: Parameter seeding fails
**Possible Causes**:
1. Formula not approved yet
2. LLM API rate limit or error
3. Formula has no identifiers (e.g., `value = 100`)

**Solution**:
1. Ensure `approved_by_user=TRUE` in MathModels tab
2. Check `--max-llm-calls` limit (increase if needed)
3. Manually add param rows in Params tab if LLM fails

---

### Problem: Scores don't appear in Central Backlog
**Cause**: Active framework not set or activation not run.

**Solution**:
1. Verify `active_scoring_framework = MATH_MODEL` in Scoring_Inputs tab
2. Run sync: `uv run python -m test_scripts.flow3_product_ops_cli --sync`
3. Run activation: `uv run python -m test_scripts.flow2_scoring_cli --all`
4. Run backlog sync: `uv run python -m test_scripts.backlog_sync_cli`

---

## Cost & Performance

### API Costs (OpenAI)
- **Formula suggestion** (gpt-4o): ~$0.02 per initiative
- **Param metadata** (gpt-4o-mini): ~$0.001 per initiative
- **Daily operations** (50 initiatives): ~$1.00

### Rate Limits (Safety Caps)
- `--max-llm-calls` defaults to 10 per run (prevents runaway costs)
- Adjust upward for large batches: `--max-llm-calls 50`

### Performance Benchmarks
- **Sync inputs**: 100 initiatives in ~10 seconds
- **Compute scores**: 100 initiatives in ~30 seconds
- **Write scores**: 100 initiatives in ~15 seconds
- **Backlog sync**: 100 initiatives in ~20 seconds

**Total end-to-end**: ~75 seconds for 100 initiatives

---

## Configuration Reference

### Environment Variables
```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL_MATHMODEL="gpt-4o"  # Formula suggestion
export OPENAI_MODEL_PARAMMETA="gpt-4o-mini"  # Param metadata
```

### Config JSON (product_ops_config.json)
```json
{
  "spreadsheet_id": "your-productops-sheet-id",
  "math_models_tab": "MathModels",
  "params_tab": "Params",
  "scoring_inputs_tab": "Scoring_Inputs"
}
```

### Defaults (app/config.py)
- `SCORING_BATCH_COMMIT_EVERY = 50` - DB commit frequency
- `OPENAI_MODEL_MATHMODEL = "gpt-4o"` - Model for formula suggestions
- `OPENAI_MODEL_PARAMMETA = "gpt-4o-mini"` - Model for param metadata

---

## Related Documentation
- [Phase 4 Implementation Steps](./phase%204_mathmodels/phase4_mathmodel.md)
- [CLI Commands Cheatsheet](./cli_commands_cheatsheet.md)
- [Phase 4 Acceptance Test](./phase4_acceptance_test.md)
- [Initiative Schema](./initiative_schema.md)
- [Flow 3 Documentation](./flow_3_productops.md)
