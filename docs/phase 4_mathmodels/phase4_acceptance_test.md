# Phase 4 Acceptance Test Checklist

**Purpose**: End-to-end validation of custom math model scoring workflow  
**Test Initiative**: INIT-TEST-MATH-001  
**Duration**: ~30 minutes  
**Last Updated**: 16 December 2025

---

## Prerequisites

Before starting the acceptance test, verify:

- [ ] `OPENAI_API_KEY` environment variable configured
- [ ] ProductOps spreadsheet has tabs: `MathModels`, `Params`, `Scoring_Inputs`
- [ ] Database migrations applied: `alembic upgrade head`
- [ ] Python environment activated: `cd productroadmap_sheet_project && source .venv/bin/activate`
- [ ] Test initiative exists in DB with `initiative_key = INIT-TEST-MATH-001`

**Setup Test Initiative** (if needed):
```bash
# Add initiative to DB via intake or manual insert
# Ensure: initiative_key='INIT-TEST-MATH-001', use_math_model=TRUE
```

---

## Test Scenario: Custom Math Model Scoring

### Phase 1: Formula Definition

#### 1.1 Create Math Model Entry
**Actions**:
- [ ] Open ProductOps spreadsheet → **MathModels** tab
- [ ] Add new row with these values:
  - `initiative_key`: `INIT-TEST-MATH-001`
  - `model_description_free_text`: `"Calculate value from user sessions, conversion rate, and revenue per conversion"`
  - `formula_text`: `value = sessions * 0.05 * 100`
  - `approved_by_user`: `TRUE`
- [ ] Save sheet

**Expected Result**: Row visible in MathModels tab with formula approved

---

#### 1.2 Optional: Test LLM Formula Suggestion
**Command**:
```bash
uv run python -m test_scripts.flow4_mathmodels_cli --suggest-mathmodels --limit 1 --log-level INFO
```

**Actions**:
- [ ] Run command above
- [ ] Check MathModels tab for `llm_suggested_formula_text` populated
- [ ] Verify `llm_notes` contains rationale

**Expected Result**:
- LLM suggestion appears in sheet (if initiative has `use_math_model=TRUE` and not already approved)
- Logs show: `"Suggested formula for INIT-TEST-MATH-001"`

**Skip if**: Already manually wrote formula in step 1.1

---

### Phase 2: Parameter Seeding

#### 2.1 Seed Parameter Rows
**Command**:
```bash
uv run python -m test_scripts.flow4_mathmodels_cli --seed-params --limit 1 --max-llm-calls 5 --log-level INFO
```

**Actions**:
- [ ] Run command above
- [ ] Check ProductOps → **Params** tab
- [ ] Verify new row(s) added for `INIT-TEST-MATH-001`

**Expected Result**:
- Params tab has row with:
  - `initiative_key`: `INIT-TEST-MATH-001`
  - `framework`: `MATH_MODEL`
  - `param_name`: `sessions`
  - `is_auto_seeded`: `TRUE`
  - `param_display`, `description`, `unit`, `min`, `max` populated by LLM (or blank if LLM skipped)
- Logs show: `"Seeded X params for INIT-TEST-MATH-001"`

---

#### 2.2 Fill Parameter Values
**Actions**:
- [ ] In **Params** tab, find row for `param_name=sessions`
- [ ] Set `value`: `10000`
- [ ] Set `approved`: `TRUE`
- [ ] Save sheet

**Expected Result**: Param row shows value=10000, approved=TRUE

---

### Phase 3: Score Computation

#### 3.1 Sync ProductOps Inputs to DB
**Command**:
```bash
uv run python -m test_scripts.flow3_product_ops_cli --sync --log-level INFO
```

**Actions**:
- [ ] Run command above

**Expected Result**:
- Logs show: `"flow3.sync.done | updated=X"`
- DB now has param values synced

---

#### 3.2 Compute All Framework Scores
**Command**:
```bash
uv run python -m test_scripts.flow3_product_ops_cli --compute-all --log-level INFO
```

**Actions**:
- [ ] Run command above
- [ ] Check logs for math model evaluation

**Expected Result**:
- Logs show: `"Computed math_value_score for INIT-TEST-MATH-001"`
- DB fields updated:
  - `math_value_score = 50000` (10000 × 0.05 × 100)
  - `math_warnings = NULL` or empty (no errors)

**Manual Verification** (optional):
```bash
uv run python -c "from app.db.session import SessionLocal; from app.db.models.initiative import Initiative; db=SessionLocal(); i=db.query(Initiative).filter_by(initiative_key='INIT-TEST-MATH-001').first(); print(f'math_value_score={i.math_value_score}, warnings={i.math_warnings}'); db.close()"
```

---

#### 3.3 Write Scores Back to ProductOps
**Command**:
```bash
uv run python -m test_scripts.flow3_product_ops_cli --write-scores --log-level INFO
```

**Actions**:
- [ ] Run command above
- [ ] Open ProductOps → **Scoring_Inputs** tab
- [ ] Find row for `INIT-TEST-MATH-001`

**Expected Result**:
- **Scoring_Inputs** tab columns populated:
  - `math_value_score`: `50000`
  - `math_overall_score`: `50000` (or value/effort if effort defined)
  - `math_warnings`: Empty (no errors)

---

### Phase 4: Activation & Backlog Sync

#### 4.1 Set Active Framework to Math Model
**Actions**:
- [ ] In **Scoring_Inputs** tab, find `INIT-TEST-MATH-001`
- [ ] Set `active_scoring_framework`: `MATH_MODEL`
- [ ] Save sheet

**Expected Result**: Column shows `MATH_MODEL` for this initiative

---

#### 4.2 Sync Active Framework Choice to DB
**Command**:
```bash
uv run python -m test_scripts.flow3_product_ops_cli --sync --log-level INFO
```

**Actions**:
- [ ] Run command above

**Expected Result**:
- DB field `initiative.active_scoring_framework = 'MATH_MODEL'`

---

#### 4.3 Activate Chosen Framework Scores
**Command**:
```bash
uv run python -m test_scripts.flow2_scoring_activation_cli --all --log-level INFO
```

**Actions**:
- [ ] Run command above

**Expected Result**:
- DB fields updated:
  - `initiative.value_score = 50000` (copied from math_value_score)
  - `initiative.overall_score = 50000` (copied from math_overall_score)
- Logs show: `"Activated MATH_MODEL for INIT-TEST-MATH-001"`

**Manual Verification**:
```bash
uv run python -c "from app.db.session import SessionLocal; from app.db.models.initiative import Initiative; db=SessionLocal(); i=db.query(Initiative).filter_by(initiative_key='INIT-TEST-MATH-001').first(); print(f'active_framework={i.active_scoring_framework}, value_score={i.value_score}, overall_score={i.overall_score}'); db.close()"
```

---

#### 4.4 Sync Active Scores to Central Backlog
**Command**:
```bash
uv run python -m test_scripts.backlog_sync_cli --log-level INFO
```

**Actions**:
- [ ] Run command above
- [ ] Open Central Backlog spreadsheet
- [ ] Find row for `INIT-TEST-MATH-001`

**Expected Result**:
- Central Backlog columns show:
  - `value_score`: `50000`
  - `overall_score`: `50000`
  - `active_scoring_framework`: `MATH_MODEL`

---

## Phase 5: Error Handling Tests

### 5.1 Test Missing Parameter Warning

**Actions**:
- [ ] In MathModels tab, change `formula_text` to: `value = sessions * missing_param`
- [ ] Run compute: `uv run python -m test_scripts.flow3_product_ops_cli --compute-all`
- [ ] Check Scoring_Inputs tab

**Expected Result**:
- `math_warnings` column shows: `"Missing params: missing_param"`
- `math_value_score` is NULL or 0
- Logs show warning message

---

### 5.2 Test Unapproved Formula

**Actions**:
- [ ] In MathModels tab, set `approved_by_user`: `FALSE`
- [ ] Run compute: `uv run python -m test_scripts.flow3_product_ops_cli --compute-all`
- [ ] Check Scoring_Inputs tab

**Expected Result**:
- `math_warnings` column shows: `"Formula not approved"`
- `math_value_score` is NULL or 0

**Cleanup**:
- [ ] Set `approved_by_user` back to `TRUE`
- [ ] Restore original formula: `value = sessions * 0.05 * 100`

---

### 5.3 Test Formula Syntax Error

**Actions**:
- [ ] In MathModels tab, change `formula_text` to: `value = sessions * *` (invalid syntax)
- [ ] Run compute: `uv run python -m test_scripts.flow3_product_ops_cli --compute-all`
- [ ] Check logs and Scoring_Inputs tab

**Expected Result**:
- Logs show: `"Syntax error in formula"`
- `math_warnings` column shows syntax error message
- `math_value_score` is NULL or 0

**Cleanup**:
- [ ] Restore valid formula: `value = sessions * 0.05 * 100`

---

## Success Criteria

**All checkboxes above must be checked for acceptance test to pass.**

### Critical Path Validation:
- ✅ Formula created and approved in MathModels tab
- ✅ Parameters seeded automatically from formula
- ✅ Parameter values filled and approved by PM
- ✅ Math scores computed correctly (50000 = 10000 × 0.05 × 100)
- ✅ Scores visible in ProductOps Scoring_Inputs tab
- ✅ Active framework set to MATH_MODEL
- ✅ Active scores propagated to DB
- ✅ Central Backlog reflects math model scores

### Error Handling Validation:
- ✅ Missing parameters trigger warning (not crash)
- ✅ Unapproved formulas skipped gracefully
- ✅ Syntax errors caught and logged

### Data Lineage:
- ✅ End-to-end flow: MathModels → Params → DB → ProductOps → Central Backlog
- ✅ No data loss or corruption at any step
- ✅ Warnings visible to PM in sheet

---

## Troubleshooting

### If tests fail:

1. **LLM suggestions not appearing**:
   - Check `OPENAI_API_KEY`: `echo $OPENAI_API_KEY`
   - Verify `use_math_model=TRUE` in Scoring_Inputs
   - Try `--force` flag: `--suggest-mathmodels --force`

2. **Parameter seeding fails**:
   - Verify formula is approved (`approved_by_user=TRUE`)
   - Check logs for LLM API errors
   - Manually add param rows in Params tab as fallback

3. **Scores not computing**:
   - Check `math_warnings` column for specific error
   - Verify all params have `value` and `approved=TRUE`
   - Check logs with `--log-level DEBUG`

4. **Backlog not updating**:
   - Verify `active_scoring_framework=MATH_MODEL` in DB
  - Re-run activation: `flow2_scoring_activation_cli --all`
   - Check Central Backlog config in settings

---

## Cleanup (Optional)

After acceptance test completes, optionally remove test data:

```bash
# Remove test initiative from DB
uv run python -c "from app.db.session import SessionLocal; from app.db.models.initiative import Initiative; db=SessionLocal(); db.query(Initiative).filter_by(initiative_key='INIT-TEST-MATH-001').delete(); db.commit(); db.close()"

# Manually remove rows from ProductOps sheet:
# - MathModels tab: INIT-TEST-MATH-001 row
# - Params tab: INIT-TEST-MATH-001 rows
# - Scoring_Inputs tab: INIT-TEST-MATH-001 row
```

---

## Sign-Off

**Test Executed By**: _________________  
**Date**: _________________  
**Result**: ☐ PASS  ☐ FAIL  
**Notes**:

---

## Related Documentation
- [Phase 4 Runbook](./phase4_mathmodels_runbook.md)
- [CLI Commands Cheatsheet](./cli_commands_cheatsheet.md)
- [Flow 3 Documentation](./flow_3_productops.md)
