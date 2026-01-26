## **Scoring System Architecture Review - Production-Ready Assessment**

### **1. Initiative Score Fields - Purpose & Usage**

**On Initiative Model:**

```python
# Updated metadata (provenance tracking)
updated_source: str  # Last action that modified ANY field (e.g., "flow1.intake_sync", "pm.score_selected")
scoring_updated_source: str  # Last action that modified SCORING fields specifically
scoring_updated_at: datetime  # Timestamp of last scoring operation
created_by_user_id: str  # Optional user tracking

# Active framework (PM choice - drives which scores are "live")
active_scoring_framework: str  # "RICE" | "WSJF" | "MATH_MODEL"
use_math_model: bool  # Flag: should this initiative use math models?

# Active scores (current "view" - populated by Flow 2 activation)
value_score: float
effort_score: float
overall_score: float

# Per-framework scores (isolated storage - computed by Flow 3)
rice_value_score: float
rice_effort_score: float
rice_overall_score: float

wsjf_value_score: float
wsjf_effort_score: float
wsjf_overall_score: float

math_value_score: float
math_effort_score: float
math_overall_score: float

# LLM provenance (for active scores display)
score_llm_suggested: bool
score_approved_by_user: bool
```

**How They're Populated:**

1. **Per-Framework Scores** (`rice_*`, `wsjf_*`, `math_*`):
   - **When**: Flow 3 `pm.score_selected` action OR `compute_all_frameworks()`
   - **How**: `ScoringService._compute_framework_scores_only()` computes each framework independently
   - **Math Model Case**: Representative model selected (primary → first by kpi sort) → stored in `math_value_score` etc.
   - **Provenance**: `scoring_updated_source = "flow3.compute_all_frameworks"`

2. **Active Scores** (`value_score`, `effort_score`, `overall_score`):
   - **When**: Flow 2 activation OR `pm.switch_framework` action
   - **How**: `ScoringService.activate_initiative_framework()` copies from per-framework scores based on `active_scoring_framework`
   - **Example**: If `active_scoring_framework = "RICE"`, copies `rice_value_score` → `value_score`
   - **Provenance**: `scoring_updated_source = "flow2.activate"`

3. **Individual Model Scores** (`InitiativeMathModel.computed_score`):
   - **When**: Flow 3 after MATH_MODEL framework scoring
   - **How**: `ScoringService._score_individual_math_models()` scores each model, stores in `model.computed_score`
   - **Then**: KPI adapter aggregates by `target_kpi_key` → `kpi_contribution_computed_json`

### **2. InitiativeScore History Table**

**Purpose**: Optional audit trail for scoring runs (NOT the current active scores)

**When Populated**:
- Controlled by `settings.SCORING_ENABLE_HISTORY` (default: disabled in most environments)
- Creates one row per (initiative, framework, scoring run) when enabled
- Stores: framework_name, value_score, effort_score, overall_score, inputs_json, components_json, warnings_json, llm_suggested, approved_by_user

**Usage**: Audit/compliance, debugging, score evolution tracking

**Current State**: ✅ Supports all frameworks including multi-model MATH_MODEL

### **3. PM Scoring Workflow - Tab-Aware Actions**

**ProductOps Sheet Tabs:**

1. **Scoring_Inputs Tab** (RICE/WSJF parameters + active scores display):
   - **PM Actions Available**:
     - `pm.score_selected` ✅ (runs all frameworks, writes per-framework scores)
     - `pm.switch_framework` ✅ (activates selected framework without recomputing)
     - `pm.save_selected` ✅ (syncs edited RICE/WSJF params to DB)
   - **PM Flow**:
     1. Edit RICE/WSJF params in columns M-T
     2. Select rows (by clicking initiative_key cells)
     3. Roadmap AI menu → "Score Selected"
     4. System computes RICE + WSJF + MATH_MODEL (if use_math_model=TRUE)
     5. Writes per-framework scores back to columns U-Z (RICE), X-Z (WSJF), I-K (MATH)
     6. Optionally: Switch active framework via "Switch Framework" action

2. **MathModels Tab** (formula definition + approval):
   - **PM Actions Available**:
     - `pm.suggest_math_model_llm` ✅ (LLM suggests formula, writes to llm_suggested_formula_text)
     - `pm.seed_math_params` ✅ (extracts variables from approved formula → seeds Params rows)
     - `pm.save_selected` ✅ (syncs approved formulas to DB)
   - **PM Flow**:
     1. Add rows for each initiative (multiple models per initiative)
     2. Set `target_kpi_key` (which KPI this model impacts)
     3. Document `metric_chain_text` (impact pathway)
     4. Optional: Roadmap AI menu → "Suggest Math Model" (LLM fills llm_suggested_formula_text)
     5. Review suggestion → copy to `formula_text` OR write custom formula
     6. Set `approved_by_user = TRUE`
     7. Roadmap AI menu → "Seed Math Params" (creates Params rows)
     8. Roadmap AI menu → "Save Selected" (persists to DB)

3. **Params Tab** (parameter values):
   - **PM Actions Available**:
     - `pm.save_selected` ✅ (syncs param values to DB)
   - **PM Flow**:
     1. Navigate to auto-seeded rows (framework="MATH_MODEL")
     2. Fill `value` column with estimates
     3. Set `approved = TRUE`
     4. Roadmap AI menu → "Save Selected"
     5. **Then switch to Scoring_Inputs tab** → run "Score Selected"

4. **Metrics_Config Tab** (KPI registry):
   - **PM Actions**: `pm.save_selected` (syncs KPI definitions)
   - **Note**: Must define north_star + strategic KPIs here BEFORE using in math models

5. **KPI_Contributions Tab** (PM override surface):
   - **PM Actions**: `pm.save_selected` (overrides system-computed contributions)
   - **Display**: Shows both `kpi_contribution_json` (active) and `kpi_contribution_computed_json` (system reference)
   - **Override**: Edit `kpi_contribution_json` → sets `kpi_contribution_source = "pm_override"` → blocks system updates

### **4. Complete Scoring Flows - End-to-End**

#### **Flow A: RICE/WSJF Scoring (Simple Frameworks)**

```
ProductOps/Scoring_Inputs:
1. PM edits rice_reach, rice_impact, rice_confidence, rice_effort (columns M-P)
2. PM selects rows → Roadmap AI → "Score Selected"
3. Backend:
   - ScoringService.score_initiative_all_frameworks():
     - Compute RICE → rice_value_score, rice_effort_score, rice_overall_score
     - Compute WSJF → wsjf_value_score, wsjf_effort_score, wsjf_overall_score
     - Skip MATH_MODEL if use_math_model=FALSE
   - ProductOpsWriter.write_scores_to_sheet():
     - Writes to Scoring_Inputs columns U-Z (RICE scores)
   - Sets scoring_updated_source = "flow3.compute_all_frameworks"
4. If active_scoring_framework = "RICE":
   - Flow 2 activation copies rice_* → value_score, effort_score, overall_score
   - Sets scoring_updated_source = "flow2.activate"
```

#### **Flow B: Math Model Scoring (Multi-Model Architecture)**

```
Phase 1: Define Metric Chains & KPI Targets
ProductOps/MathModels:
1. PM adds rows (multiple per initiative):
   - initiative_key = "INIT-123"
   - model_name = "Revenue Impact Model"
   - target_kpi_key = "revenue" (from Metrics_Config)
   - metric_chain_text = "signups → activation → purchases → revenue"
   - is_primary = TRUE (if representative model)

Phase 2: Generate Formulas (Optional LLM)
2. PM selects rows → Roadmap AI → "Suggest Math Model"
3. Backend:
   - LLMClient.suggest_math_model():
     - Builds prompt with problem_statement + metric_chain + target KPI
     - Returns formula_text + assumptions + param suggestions
   - MathModelsWriter writes to llm_suggested_formula_text column

Phase 3: Approve Formulas
4. PM reviews llm_suggested_formula_text
5. Copies to formula_text OR writes custom
6. Sets approved_by_user = TRUE
7. Roadmap AI → "Save Selected"

Phase 4: Seed & Fill Parameters
8. PM stays on MathModels → Roadmap AI → "Seed Math Params"
9. Backend:
   - ParamSeedingJob:
     - Parses formula_text → extracts variable names
     - Creates Params rows (framework="MATH_MODEL", model_name=<model_name>)
     - Calls LLM for metadata (param_display, unit, description)
10. PM switches to Params tab
11. Filters by initiative_key + framework="MATH_MODEL"
12. Fills value column
13. Sets approved = TRUE
14. Roadmap AI → "Save Selected"

Phase 5: Compute Scores & KPI Contributions
15. PM switches to Scoring_Inputs tab
16. Selects rows → Roadmap AI → "Score Selected"
17. Backend:
    - ScoringService.score_initiative_all_frameworks():
      - For MATH_MODEL framework:
        a) _build_math_model_inputs():
           - Selects representative model (primary → first by kpi sort)
           - Loads params from Params table
        b) MathModelScoringEngine.compute():
           - Evaluates representative formula
           - Returns value_score (impact), effort_score, overall_score
        c) Stores in math_value_score, math_effort_score, math_overall_score
        d) _score_individual_math_models():
           - Iterates ALL initiative.math_models
           - Scores each individually → model.computed_score
        e) update_initiative_contributions():
           - Aggregates model scores by target_kpi_key
           - Writes kpi_contribution_computed_json (always updated)
           - If source != "pm_override": copies to kpi_contribution_json
           - Validates keys against Metrics_Config
    - ProductOpsWriter: Writes math_* scores to Scoring_Inputs columns I-K

Phase 6: Activation (Optional)
18. If active_scoring_framework = "MATH_MODEL":
    - Flow 2 copies math_* → value_score, effort_score, overall_score
```

#### **Flow C: PM Override KPI Contributions**

```
ProductOps/KPI_Contributions:
1. PM sees:
   - kpi_contribution_json (active, PM-editable)
   - kpi_contribution_computed_json (system reference, read-only)
   - kpi_contribution_source (computed | pm_override)
2. PM edits kpi_contribution_json:
   - Example: {"revenue": 120.5, "user_retention": 85.0}
3. Roadmap AI → "Save Selected"
4. Backend:
   - KPIContributionsSyncService:
     - Sets kpi_contribution_source = "pm_override"
     - Validates keys against Metrics_Config (north_star/strategic only)
     - Drops invalid keys with warnings
5. **Future scoring runs**:
   - System continues updating kpi_contribution_computed_json
   - DOES NOT overwrite kpi_contribution_json (preserves PM override)
   - PM can see diff between computed vs override
```

### **5. Edge Cases & Validation**

**✅ Multi-Model Aggregation**:
- Multiple models target same KPI → primary model wins, else highest score
- Aggregation by target_kpi_key ensures no duplicate KPI keys in output JSON
- Validation: at most 1 is_primary=True per initiative (deterministic fallback)

**✅ Invalid KPI Keys**:
- Adapter validates against Metrics_Config (is_active=true, level∈{north_star, strategic})
- Drops invalid keys with warning logged
- Returns diagnostics["invalid_kpis"] list

**✅ Missing Representative Model**:
- If no is_primary: selects first by target_kpi_key sort
- If no models: math_value_score = None (graceful degradation)

**✅ PM Override Protection**:
- Once source="pm_override", system never overwrites kpi_contribution_json
- System always updates kpi_contribution_computed_json for PM reference
- PM must manually change source back to "computed" to re-enable system updates

**✅ Partial Sync Conflicts**:
- Metrics_Config validation warns if exactly 1 active north_star not found
- Selective sync (not all KPIs) could cause validation errors

### **6. Consistency with Latest Changes**

**✅ All Fields Relevant:**
- `scoring_updated_source` / `scoring_updated_at`: ✅ Used for provenance tracking
- Per-framework scores: ✅ Populated by Flow 3, copied by Flow 2
- Active scores: ✅ Activated by Flow 2 based on `active_scoring_framework`
- `use_math_model`: ✅ Controls MATH_MODEL framework execution
- `score_llm_suggested` / `score_approved_by_user`: ✅ Copied from representative model during activation

**✅ Tab-Aware Actions:**
- `pm.score_selected`: Should run from **Scoring_Inputs tab** (has active_scoring_framework context)
- `pm.seed_math_params`: Should run from **MathModels tab** (has formula_text + approved_by_user)
- `pm.save_selected`: Tab-aware branching (Scoring_Inputs → sync inputs, MathModels → sync models, Params → sync params)

**✅ Sheet Columns Registered:**
- Scoring_Inputs: ✅ All columns mapped (including math_warnings)
- MathModels: ✅ NEW columns added (target_kpi_key, is_primary, computed_score)
- Params: ✅ Supports model_name column for multi-model params
- KPI_Contributions: ✅ NEW columns added (kpi_contribution_computed_json, kpi_contribution_source)

### **7. Recommended PM Workflow Summary**

**For Math Model Scoring (Complete Flow):**

1. **Define KPIs** (Metrics_Config tab) → Save
2. **Create Models** (MathModels tab):
   - Add rows, set target_kpi_key, metric_chain_text, model_name
   - Optionally: Suggest formulas (LLM)
   - Approve formulas
   - Save
3. **Seed Params** (MathModels tab) → "Seed Math Params" action
4. **Fill Params** (Params tab) → Edit values → Approve → Save
5. **Score** (Scoring_Inputs tab) → Select rows → "Score Selected"
6. **Verify** (KPI_Contributions tab) → Check kpi_contribution_computed_json
7. **Override** (Optional, KPI_Contributions tab) → Edit kpi_contribution_json → Save

**For RICE/WSJF Scoring (Simple Flow):**

1. **Edit Params** (Scoring_Inputs tab, columns M-T)
2. **Score** (same tab) → Select rows → "Score Selected"
3. **Switch Framework** (Optional) → Select rows → "Switch Framework" action


## Complete PM Action Flow: `pm.score_selected`

**Entry Point:** Product Ops Scoring_Inputs tab → Roadmap AI menu → "Score Selected" action

### **Complete Call Chain:**

```
1. USER ACTION: PM selects rows in Scoring_Inputs tab, clicks "Score Selected"
   ↓
2. _action_pm_score_selected(db, ctx)
   [app/services/action_runner.py:680-860]
   ├─ Extracts selected initiative_keys from action context
   ├─ Gets spreadsheet_id + tab from sheet_context
   │
   ├─ STEP 1: Sync inputs (Sheet → DB)
   ├─ run_flow3_sync_inputs_to_initiatives(db, spreadsheet_id, tab_name, initiative_keys)
   │  [app/jobs/flow3_product_ops_job.py:90-222]
   │  ├─ ScoringInputsReader.read_scoring_inputs_rows()
   │  │  [app/sheets/scoring_inputs_reader.py]
   │  │  └─ Reads: rice_reach, wsjf_job_size, active_scoring_framework, etc.
   │  └─ Updates Initiative fields in DB (rice_reach → initiative.rice_reach)
   │
   ├─ STEP 2: Compute all frameworks (DB compute)
   ├─ ScoringService.compute_for_initiatives(keys, commit_every=10)
   │  [app/services/product_ops/scoring_service.py:465-530]
   │  │
   │  ├─ FOR EACH selected initiative:
   │  │  score_initiative_all_frameworks(initiative)
   │  │  [scoring_service.py:260-300]
   │  │  │
   │  │  ├─ FOR framework in [RICE, WSJF, MATH_MODEL]:
   │  │  │  score_initiative(initiative, framework, activate=False)
   │  │  │  [scoring_service.py:45-185]
   │  │  │  │
   │  │  │  ├─ Build ScoringInputs from initiative fields
   │  │  │  │
   │  │  │  ├─ Call framework engine:
   │  │  │  │  ├─ IF RICE: RiceScoringEngine.compute()
   │  │  │  │  ├─ IF WSJF: WsjfScoringEngine.compute()
   │  │  │  │  └─ IF MATH_MODEL: MathModelScoringEngine.compute()
   │  │  │  │     [app/services/product_ops/math_model_scoring_engine.py]
   │  │  │  │     └─ Selects primary model OR max score per KPI
   │  │  │  │
   │  │  │  ├─ Store representative score:
   │  │  │  │  ├─ initiative.rice_value_score / rice_overall_score (RICE)
   │  │  │  │  ├─ initiative.wsjf_value_score / wsjf_overall_score (WSJF)
   │  │  │  │  └─ initiative.math_value_score / math_overall_score (MATH_MODEL)
   │  │  │  │
   │  │  │  └─ IF MATH_MODEL:
   │  │  │     │
   │  │  │     ├─ _score_individual_math_models(initiative)
   │  │  │     │  [scoring_service.py:195-250]
   │  │  │     │  │
   │  │  │     │  └─ FOR EACH model in initiative.math_models:
   │  │  │     │     ├─ Build params_env with constraints
   │  │  │     │     ├─ engine.score_single_model(model, params_env)
   │  │  │     │     │  [math_model_scoring_engine.py:275-410]
   │  │  │     │     │  ├─ Evaluate formula with llm_formula_executor
   │  │  │     │     │  └─ Store in model.computed_score
   │  │  │     │     └─ db.flush()
   │  │  │     │
   │  │  │     └─ update_initiative_contributions(db, initiative, commit=False)
   │  │  │        [app/services/product_ops/kpi_contribution_adapter.py:162-260]
   │  │  │        │
   │  │  │        ├─ compute_kpi_contributions(initiative)
   │  │  │        │  [kpi_contribution_adapter.py:90-155]
   │  │  │        │  ├─ Group models by target_kpi_key
   │  │  │        │  ├─ Primary model wins per KPI (NOT summed)
   │  │  │        │  └─ Returns {kpi_key: score}
   │  │  │        │
   │  │  │        ├─ validate_kpi_keys(computed_contributions)
   │  │  │        │  └─ Filters out non north_star/strategic KPIs
   │  │  │        │
   │  │  │        └─ Update Initiative:
   │  │  │           ├─ initiative.kpi_contribution_computed_json (ALWAYS)
   │  │  │           └─ initiative.kpi_contribution_json (IF source != "pm_override")
   │  │  │
   │  │  └─ db.commit() every commit_every (default 10) initiatives
   │  │
   │  └─ Returns computed_count
   │
   ├─ STEP 3: Write scores back to sheet (DB → Sheet)
   ├─ run_flow3_write_scores_to_sheet(db, spreadsheet_id, tab_name, keys, warnings)
   │  [app/jobs/flow3_product_ops_job.py:223-280]
   │  │
   │  └─ write_scores_to_productops_sheet(db, client, spreadsheet_id, tab_name, keys, warnings)
   │     [app/sheets/productops_writer.py:69-305]
   │     │
   │     ├─ Read header row → map columns (rice_value_score, wsjf_overall_score, etc.)
   │     ├─ Read initiative_key column → build row_index map
   │     ├─ Load initiatives from DB (selected keys OR all)
   │     │
   │     ├─ FOR EACH initiative with matching row:
   │     │  ├─ Build cell updates for per-framework scores:
   │     │  │  ├─ rice_value_score, rice_effort_score, rice_overall_score
   │     │  │  ├─ wsjf_value_score, wsjf_effort_score, wsjf_overall_score
   │     │  │  ├─ math_value_score, math_effort_score, math_overall_score
   │     │  │  ├─ math_warnings (JSON string if present)
   │     │  │  └─ value_score, effort_score, overall_score (active framework)
   │     │  │
   │     │  ├─ Add provenance: updated_source = FLOW3_PRODUCTOPSSHEET_WRITE_SCORES
   │     │  └─ Add timestamp: updated_at
   │     │
   │     ├─ Batch update cells (chunks of 200 to avoid API limits)
   │     └─ Returns updated_count
   │
   └─ STEP 4: Write status column (best-effort)
      └─ write_status_to_sheet(client, spreadsheet_id, tab, status_by_key)
         [app/sheets/productops_writer.py:308-390]
         └─ Updates "Status" column with "OK" / "FAILED: reason"
```

---

### **Key Behaviors:**

1. **Multi-Model Scoring:**
   - `_score_individual_math_models()` scores EACH InitiativeMathModel
   - Each model.computed_score stored individually in DB
   - Primary model OR max score determines representative math_value_score

2. **KPI Contributions:**
   - `compute_kpi_contributions()` aggregates models by target_kpi_key
   - Primary model WINS per KPI (not summed)
   - Invalid KPIs filtered out (only north_star/strategic levels)
   - Respects pm_override: computed_json always updates, active json only if source != "pm_override"

3. **Score Writeback:**
   - Writes ALL per-framework scores (rice_*, wsjf_*, math_*)
   - Writes active scores (value_score, effort_score, overall_score)
   - Adds provenance token: `FLOW3_PRODUCTOPSSHEET_WRITE_SCORES`
   - Updates timestamp: updated_at

4. **Provenance Tracking:**
   - activate=False → `FLOW3_COMPUTE_ALL_FRAMEWORKS`
   - activate=True → `FLOW2_COMPUTE_SELECTED_FRAMEWORK`
   - Sheet writeback → `FLOW3_PRODUCTOPSSHEET_WRITE_SCORES`

---

### **Database Fields Updated:**

**Initiative Model:**
- `rice_value_score`, `rice_effort_score`, `rice_overall_score`
- `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`
- `math_value_score`, `math_effort_score`, `math_overall_score`
- `math_warnings` (JSON text)
- `kpi_contribution_computed_json` (always)
- `kpi_contribution_json` (if not pm_override)
- `kpi_contribution_source` (always)

**InitiativeMathModel:**
- `computed_score` (per model)
- `last_computed_at`

---

### **Files Involved (Complete List):**

| File Path | Role |
|-----------|------|
| app/services/action_runner.py | PM action orchestration |
| app/jobs/flow3_product_ops_job.py | Flow 3 jobs (sync + writeback) |
| app/services/product_ops/scoring_service.py | Core scoring logic |
| app/services/product_ops/math_model_scoring_engine.py | Math model execution |
| app/services/product_ops/kpi_contribution_adapter.py | KPI contribution aggregation |
| app/sheets/scoring_inputs_reader.py | Read inputs from sheet |
| app/sheets/productops_writer.py | Write scores to sheet |



























## **✅ Implementation Complete: KPI Contributions Writeback**

I've successfully implemented the KPI contributions writeback feature with three components:

---

### **1. Created `app/sheets/kpi_contributions_writer.py`** ✅

**Similar to productops_writer.py, implements:**
- `write_kpi_contributions_to_sheet()` function
- Writes system-computed KPI contributions back to sheet
- Batch updates using Google Sheets API
- Provenance tracking with new token

**Columns Written:**
- `kpi_contribution_computed_json` ← Latest system computation from math models
- `kpi_contribution_source` ← "math_model_derived" or "pm_override"
- `run_status` ← "OK" (placeholder for validation)
- `updated_source` ← `FLOW3_PRODUCTOPSSHEET_WRITE_KPI_CONTRIBUTIONS`
- `updated_at` ← ISO timestamp

---

### **2. Added Provenance Token** ✅

**In app/utils/provenance.py:**
```python
FLOW3_PRODUCTOPSSHEET_WRITE_KPI_CONTRIBUTIONS = "flow3.productopssheet_write_kpi_contributions"
```

---

### **3. Integrated into `pm.score_selected`** ✅

**In app/services/action_runner.py:**

Added **Step 3.5** after score writeback:
```python
# 3.5) Write KPI contributions back to KPI_Contributions tab (if exists)
kpi_contributions_written = 0
if cfg and hasattr(cfg, "kpi_contributions_tab"):
    kpi_tab = cfg.kpi_contributions_tab
    try:
        from app.sheets.kpi_contributions_writer import write_kpi_contributions_to_sheet
        kpi_contributions_written = write_kpi_contributions_to_sheet(
            db=db,
            client=ctx.sheets_client,
            spreadsheet_id=str(spreadsheet_id),
            tab_name=str(kpi_tab),
            initiative_keys=keys,
        )
        logger.info(...)
    except Exception as e:
        logger.warning(...)  # Non-fatal
```

**Return payload includes:**
```python
{
    "kpi_contributions_written": kpi_contributions_written,
    "substeps": [
        {"step": "flow3.write_kpi_contributions", "status": "ok", "count": kpi_contributions_written}
    ]
}
```

---

### **Complete Updated Flow: `pm.score_selected`**

```
PM: Scoring_Inputs tab → Roadmap AI menu → "Score Selected"
  ↓
_action_pm_score_selected(keys)
  ↓ Step 1: Sync inputs
  run_flow3_sync_inputs_to_initiatives()
  ↓ Step 2: Compute all frameworks + KPI contributions
  ScoringService.compute_for_initiatives(keys)
    → score_initiative_all_frameworks()
      → score_initiative(framework=MATH_MODEL)
        → _score_individual_math_models()
        → update_initiative_contributions() ✅ PERSISTS TO DB
  ↓ Step 3: Write scores to Scoring_Inputs tab
  run_flow3_write_scores_to_sheet()
  ↓ Step 3.5: Write KPI contributions to KPI_Contributions tab ✅ NEW
  write_kpi_contributions_to_sheet()
    → Updates: kpi_contribution_computed_json, kpi_contribution_source,
               run_status, updated_source, updated_at
  ↓ Step 4: Write status column
  write_status_to_sheet()
```

---
































---

## **✅ Fix #1: Immediate Writeback After pm.save_selected**

**Location:** app/services/action_runner.py

**What It Does:**
```python
# After KPI contributions sync (sheet → DB):
result = svc.sync_sheet_to_db(...)
saved = result.get("upserts", 0)
unlocked = result.get("unlocked", 0)

# NEW: Immediately write back to sheet (DB → sheet)
writeback_count = write_kpi_contributions_to_sheet(
    db=db,
    client=ctx.sheets_client,
    spreadsheet_id=str(spreadsheet_id),
    tab_name=str(tab),
    initiative_keys=keys or None,
)
# PM now sees updated kpi_contribution_source column immediately
```

**Result:** PM sees "pm_override" in source column **immediately** after save, not after next scoring action.

---

## **✅ Fix #2 Option A: Unlock via Empty Field**

**Location:** app/services/product_ops/kpi_contributions_sync_service.py

**What It Does:**
```python
contrib = self._normalize_contribution(row.kpi_contribution_json)
if contrib is None:  # PM cleared the field
    current_source = getattr(initiative, "kpi_contribution_source", None)
    if current_source == "pm_override":
        # Unlock: Clear override, let system take control
        initiative.kpi_contribution_json = None
        initiative.kpi_contribution_source = None
        unlocked += 1
        logger.info("kpi_contrib_sync.unlock_override", ...)
    else:
        skipped_empty += 1
    continue
```

**How PM Uses It:**
1. Open KPI_Contributions tab
2. **Clear the `kpi_contribution_json` cell** (delete contents)
3. Run "Save Selected"
4. System detects empty + pm_override → **unlocks it**
5. Next `pm.score_selected` will write system values back

---

## **Updated Flow Timeline:**

### **Scenario A: PM Overrides**
```
T1: PM edits kpi_contribution_json → pm.save_selected
    ↓ sync_sheet_to_db():
    └─ initiative.kpi_contribution_json = PM_EDIT (DB)
    └─ initiative.kpi_contribution_source = "pm_override" (DB)
    ↓ write_kpi_contributions_to_sheet():
    └─ Sheet column kpi_contribution_source: "pm_override" ✅ IMMEDIATELY
```

### **Scenario B: PM Unlocks**
```
T1: PM clears kpi_contribution_json → pm.save_selected
    ↓ sync_sheet_to_db() detects empty + pm_override:
    └─ initiative.kpi_contribution_json = NULL (DB)
    └─ initiative.kpi_contribution_source = NULL (DB) ✅ UNLOCKED
    ↓ write_kpi_contributions_to_sheet():
    └─ Sheet column kpi_contribution_source: "" (empty) ✅ IMMEDIATELY

T2: pm.score_selected runs
    ↓ update_initiative_contributions():
    └─ Sees source != "pm_override"
    └─ initiative.kpi_contribution_json = computed (system takes control)
    └─ initiative.kpi_contribution_source = "math_model_derived"
    ↓ write_kpi_contributions_to_sheet():
    └─ Sheet shows system-computed values ✅
```

---

## **Response Payload Updated:**

```python
{
    "saved_count": 5,           # PM overrides written
    "unlocked_count": 2,        # PM overrides cleared (unlocked)
    "writeback_count": 7,       # Total rows written back to sheet
}
```


























---

You're **absolutely right** — I made a critical error! Let me correct this:

## **Candidates Tab Column Ownership (Per Live Sheets Registry)**

Looking at the **actual metadata** from projectscope.md:

### **Group 1: Formula Columns (PM Copies from Backlog via Formula)** ✅ SKIP
- `initiative_key`, `title`, `country`, `department`, `lifecycle_status`, `active_scoring_framework`, `active_overall_score`
- **Metadata**: "PM Copies via formula from Backlog; Sheet→Sheet (formula), read-only."

### **Group 2: PM Input Columns (EDITABLE by PM)** ⚠️ **I WAS WRONG**
| Column | Metadata | Action |
|--------|----------|--------|
| `engineering_tokens` | "PM input Sheet → DB" | **DO NOT OVERWRITE** |
| `deadline_date` | "PM input Sheet → DB" | **DO NOT OVERWRITE** |
| `category` | "PM input - categorize work type for optimization" | **DO NOT OVERWRITE** |
| `program_key` | "PM input - assign initiative to a program for cross-functional tracking" | **DO NOT OVERWRITE** |

**You're correct**: These are **PM entry surfaces on the Candidates tab**, not derived from DB. They should be **preserved**, not overwritten.

### **Group 3: DB-Derived Columns (Backend Computes)** ✅ WRITE
| Column | Metadata | Action |
|--------|----------|--------|
| `north_star_contribution` | "Backend derives ← DB (display only here); entry surface is ProductOps/KPI_contributions" | **WRITE from DB** |
| `strategic_kpi_contributions` | "Backend derives ← DB (display only here); entry surface is ProductOps/KPI_contributions" | **WRITE from DB** |
| `immediate_kpi_key` | "PM input → DB" | **WRITE from DB** |

### **Group 4: Constraint-Derived Columns (READ-ONLY, Display Only)** ✅ WRITE
| Column | Metadata | Action |
|--------|----------|--------|
| `is_mandatory` | "READ-ONLY. Derived from Constraints tab. Edit constraints on Constraints tab only." | **WRITE from Constraints** |
| `mandate_reason` | "?" | **WRITE from Constraints** |
| `bundle_key` | "READ-ONLY. Derived from Constraints tab (bundle_all_or_nothing). Display only." | **WRITE from Constraints** |
| `prerequisite_keys` | "READ-ONLY. Derived from Constraints tab (require_prereq). Display only." | **WRITE from Constraints** |
| `exclusion_keys` | "READ-ONLY. Derived from Constraints tab (exclude_* constraints). Display only." | **WRITE from Constraints** |
| `synergy_group_keys` | "READ-ONLY. Derived from Constraints tab (synergy_bonus). Display only." | **WRITE from Constraints** |

### **Group 5: Sheet-Only PM Input** ✅ SKIP
- `notes`, `is_selected_for_run`
- **Metadata**: "PM input: Sheet-only notes/checkbox"

### **Group 6: Backend Status** ✅ WRITE
- `run_status`, `updated_source`, `updated_at`

---

## **Corrected Writer Behavior**

The writer should **NOT overwrite PM input columns** (`engineering_tokens`, `deadline_date`, `category`, `program_key`). Instead:

1. **On first populate (initiative not in sheet)**: Write all columns (including PM input defaults from DB)
2. **On subsequent updates (initiative exists)**: **SKIP PM input columns**, only update:
   - Derived KPI columns (from DB)
   - Constraint indicators (from Constraints tab)
   - Status columns

**This makes the Candidates tab a hybrid**:
- **PM enters**: `engineering_tokens`, `deadline_date`, `category`, `program_key` directly in sheet
- **Backend syncs PM inputs to DB**: Via your new `sync_candidates_from_sheet()` function (already implemented!)
- **Backend writes read-only indicators**: KPI contributions, constraint flags, status

---

## **Updated Implementation Plan**

### **Writer Logic**

```python
def populate_candidates_from_db(...):
    # Read existing rows to detect which initiatives already exist
    existing_keys = _read_existing_initiative_keys(...)
    
    for initiative in initiatives:
        is_new = initiative.initiative_key not in existing_keys
        
        if is_new:
            # NEW INITIATIVE: Write ALL columns (including PM input defaults from DB)
            write_columns = [
                "initiative_key",  # Formula (will be overwritten by formula anyway)
                "engineering_tokens",  # PM input (seed initial value from DB)
                "deadline_date",  # PM input (seed initial value from DB)
                "category",  # PM input (seed initial value from DB)
                "program_key",  # PM input (seed initial value from DB)
                "north_star_contribution",  # Derived
                "strategic_kpi_contributions",  # Derived
                "is_mandatory",  # Constraint-derived
                "bundle_key",  # Constraint-derived
                # ... etc
            ]
        else:
            # EXISTING INITIATIVE: Skip PM input columns, only update derived/system fields
            write_columns = [
                # SKIP: engineering_tokens, deadline_date, category, program_key
                "north_star_contribution",  # Derived (UPDATE)
                "strategic_kpi_contributions",  # Derived (UPDATE)
                "is_mandatory",  # Constraint-derived (UPDATE)
                "bundle_key",  # Constraint-derived (UPDATE)
                "run_status",  # Status (UPDATE)
                "updated_source",  # Provenance (UPDATE)
                "updated_at",  # Timestamp (UPDATE)
            ]
```

---

## **Sync Flow (Bidirectional)**

### **Sheet → DB** (Already Implemented ✅)
```
PM edits Candidates tab (engineering_tokens, category, etc.)
  ↓
PM runs: Roadmap AI → "Save Selected"
  ↓
sync_candidates_from_sheet() persists edits to DB
```

### **DB → Sheet** (New Writer)
```
PM runs: Roadmap AI → "Populate Candidates"
  ↓
populate_candidates_from_db()
  ├─ NEW initiatives: Write ALL columns (seed PM inputs from DB)
  └─ EXISTING initiatives: Update ONLY derived/constraint/status columns
```

---

























# Sheet Readers and Writers: Plain English Explanation

## **Core Principles**

### **Sheet Structure (Universal)**
Every sheet tab follows this structure:
- **Row 1**: Column headers (e.g., "initiative_key", "engineering_tokens")
- **Rows 2-3**: Metadata rows (descriptions, validation rules, etc.) - **NEVER touched by system**
- **Row 4+**: Actual data starts here

---

## **How READERS Work**

### **Step-by-Step Reading Process:**

1. **Read the header row (row 1)**
   - Get all column names from the sheet
   - Example: `["initiative_key", "title", "engineering_tokens", "country"]`

2. **Build a lookup map (header normalization)**
   - Normalize headers to handle aliases (e.g., "Initiative Key" = "initiative_key")
   - Create mapping: `sheet_column_name → canonical_field_name`
   - Example: Both "initiative_key" and "Initiative Key" map to the field `initiative_key`

3. **Read data rows (starting from row 4)**
   - Read range: `A4:Z{last_row}` (skips rows 1-3)
   - Each row becomes a list of values: `["INIT_001", "Build feature X", 120, "US"]`

4. **Stop at blank runs**
   - Tracks consecutive blank rows (typically stops after 50 blanks)
   - Prevents reading thousands of empty rows (performance + quota optimization)

5. **Convert rows to objects**
   - For each row, zip values with headers: `{"initiative_key": "INIT_001", "title": "Build feature X", ...}`
   - Handle missing/empty cells as `None` or `""`
   - Parse special fields (JSON strings → dicts, date strings → datetime objects)

6. **Return structured data**
   - Returns list of typed objects (e.g., `List[OptCandidateRow]`)

### **Powers:**
- ✅ Handles column reordering (uses header lookup, not position)
- ✅ Handles column aliases (multiple names for same field)
- ✅ Skips unknown columns gracefully
- ✅ Stops at blank regions (efficient)

### **Limitations:**
- ❌ Assumes row 1 is always header
- ❌ Doesn't detect merged cells well
- ❌ Can't read comments or cell formatting
- ❌ Stops at first 50-blank-row run (can miss isolated rows far below)

---

## **How WRITERS Work**

There are **two writing strategies** used across the codebase:

---

### **Strategy A: Upsert by Key (e.g., Backlog Writer)**

**Use case:** Update existing rows OR append new ones based on a unique key (e.g., `initiative_key`)

#### **Step-by-Step:**

1. **Read header (row 1)**
   - Get column names and positions
   - Build map: `column_name → column_index` (e.g., `{"initiative_key": 0, "title": 1}`)

2. **Read key column only (starting from row 4)**
   - Example: Read column A (initiative_key) from rows 4 onwards
   - Build map: `initiative_key → row_number`
   - Example: `{"INIT_001": 4, "INIT_002": 5, "INIT_003": 6}`
   - Stops after 50 consecutive blanks

3. **Determine target row for each record**
   - If key exists in map → **update that row**
   - If key doesn't exist → **append to next empty row**

4. **Build batch updates grouped by column**
   - Instead of writing cell-by-cell (slow), groups writes by column
   - Example: Write all "engineering_tokens" values in one request
   - Groups consecutive rows to minimize API calls

5. **Write in batches**
   - Sends updates in chunks (200 ranges per request to avoid API limits)
   - Uses `USER_ENTERED` mode (Google Sheets parses formulas, dates, numbers)

6. **Apply protections (optional)**
   - Protects system-owned columns with "warning-only" mode
   - Users can still edit but see a warning

#### **Example Flow:**
```
DB has: INIT_001, INIT_002, INIT_004 (new)
Sheet has: INIT_001 (row 4), INIT_002 (row 5)

Map: {"INIT_001": 4, "INIT_002": 5}
Next append row: 6

Actions:
- INIT_001 → update row 4
- INIT_002 → update row 5  
- INIT_004 → append to row 6
```

#### **Powers:**
- ✅ Updates existing rows without duplicating
- ✅ Appends new rows automatically
- ✅ Batch operations (fast, quota-efficient)
- ✅ Only touches owned columns (preserves PM edits in other columns)

#### **Limitations:**
- ❌ Requires unique key column
- ❌ Can't handle duplicate keys well
- ❌ Doesn't delete removed records (append/update only)

---

### **Strategy B: Append-Only (e.g., Optimization Results Writer)**

**Use case:** Add new records without updating existing ones (e.g., optimization run results)

#### **Step-by-Step:**

1. **Read header (row 1)**
   - Get column names and build alias map

2. **Find next empty row**
   - Reads column A (key column like `run_id`) from row 4 onwards
   - Scans backwards to find last non-empty row
   - Next append row = last_used_row + 1

3. **Build new rows as lists**
   - Each row is a list matching header order
   - Example: `["RUN_123", "INIT_001", True, 120, ...]`

4. **Append in batch**
   - Writes all rows in one API call
   - Uses range like `A10:Z15` (calculates exact range)

#### **Example Flow:**
```
Sheet has data in rows 4-8
Last non-empty row: 8
Next append row: 9

Write 3 new results:
- Row 9: [run_123, INIT_001, True, ...]
- Row 10: [run_123, INIT_002, False, ...]
- Row 11: [run_123, INIT_003, True, ...]
```

#### **Powers:**
- ✅ Never overwrites existing data
- ✅ Supports multi-run accumulation (run_id distinguishes)
- ✅ Simple and safe
- ✅ Handles blank rows in middle (scans backwards)

#### **Limitations:**
- ❌ Can't update existing rows
- ❌ Sheet grows indefinitely (manual cleanup needed)
- ❌ No deduplication (duplicate keys possible)

---

## **Key Design Patterns**

### **1. Header Normalization (Alias Handling)**
```python
normalize_header("Initiative Key") == normalize_header("initiative_key")
# Both map to canonical field "initiative_key"
```
Allows sheets to have flexible column names while system uses consistent field names.

### **2. Blank Run Detection**
```python
blank_run = 0
for row in rows:
    if is_blank(row):
        blank_run += 1
        if blank_run >= 50:
            break  # Stop reading
    else:
        blank_run = 0  # Reset counter
```
Prevents reading 10,000 empty rows. Stops after 50 consecutive blanks.

### **3. Batch Grouping**
Instead of:
```
Write A4 = value1
Write A5 = value2
Write A6 = value3  (3 API calls)
```

We do:
```
Write A4:A6 = [value1, value2, value3]  (1 API call)
```

### **4. Column-Based Ownership**
Writers only touch columns they "own" (defined in header maps). Other columns are preserved. This allows:
- PM-editable columns (notes, custom flags)
- Formula columns (cross-sheet references)
- System-owned columns (updated_at, run_status)

---

## **Real-World Example: Optimization Results Publishing**

**Scenario:** Optimization run completes, need to publish results to sheet.

**What happens:**

1. **Runs Tab (append-only)**
   - Read Runs tab, find last row = 15
   - Append 1 new row at row 16 with run summary

2. **Results Tab (append-only, multi-run)**
   - Read Results tab, find last row = 423
   - Append 50 new rows (rows 424-473) with candidate selections
   - Each row has `run_id` to distinguish from previous runs

3. **Gaps Tab (append-only, multi-run)**
   - Read Gaps tab, find last row = 89
   - Append 12 new rows (rows 90-101) with target gaps
   - Each row has `run_id` + `dimension` + `kpi_key`

**Result:** Sheet now contains historical record of all runs. PM can filter by `run_id` to see specific run results.

---

## **Summary Table**

| Aspect | Readers | Upsert Writers | Append Writers |
|--------|---------|----------------|----------------|
| **Read header** | Yes (row 1) | Yes (row 1) | Yes (row 1) |
| **Skip metadata** | Yes (rows 2-3) | Yes (rows 2-3) | Yes (rows 2-3) |
| **Key lookup** | No | Yes (builds map) | No |
| **Update existing** | N/A | Yes (by key) | No |
| **Add new** | N/A | Yes (append) | Yes (append) |
| **Quota efficiency** | High (batch reads) | High (batch writes) | High (batch writes) |
| **Data safety** | Read-only | Preserves unknown columns | Preserves all existing |
| **Use case** | Load data to DB | Sync bidirectional | Accumulate history |