---

## 1️⃣ Big picture: Sheets as the Product Control Plane

Right now:

* Central backlog sheet = **shared source of truth + presentation** for everyone.
* Intake sheets = **front-end** for intake from departments.
* Flow 1 + Flow 2 = **back-end engine**.

What you’re designing now:

> A **Product Workbook** (one Google spreadsheet) as the *exclusive playground + control panel* for the Product team.

That workbook would have multiple tabs, at least:

1. **Scoring Inputs / Experiments tab**

   * Per initiative + per framework inputs.
   * Product team freely adds/removes/tweaks columns like:

     * `RICE: Reach`
     * `RICE: Impact`
     * `WSJF: Business Value`
     * `WSJF: Time Criticality`
     * `MATH: parameter_1`, `MATH: parameter_2`, etc.
   * Backend:

     * Reads these raw inputs.
     * Maps them into `ScoreInputs` per framework.
     * Computes scores.
     * Writes results back (e.g. “RICE Score”, “WSJF Score”, comments).

2. **Config tab**

   * Mirrors / replaces the stuff in `config.py` and `.env` that should be **product-owned** decisions, not dev-only:

     * `SCORING_DEFAULT_FRAMEWORK`
     * Batch sizes / thresholds
     * Allowed statuses
     * Switches like “Enable math model”, “Use AI suggestions by default”, etc.
   * Backend:

     * Treats this tab as a **config source of truth**.
     * Reads values on flow start.
     * Persists some to DB as needed.
   * Think of it as: *instead of editing `config.py` and redeploying, PMs tune the system from Sheets.*

3. **Future Simulation / Optimization tabs**

   * Monte Carlo simulations, capacity simulations.
   * Linear / multi-objective optimization (e.g. “given budget X, maximize total impact score”).
   * Scenario tabs like:

     * “Scenario A – focus on EMEA”
     * “Scenario B – aggressive infra cut”
   * Backend:

     * Reads scenario specs and parameters.
     * Runs simulation/optimization.
     * Writes outputs: recommended prioritization, expected value distributions, risk bands, etc.


* **Backlog sheet** = simple, stable, largely read-only for non-product stakeholders + selected control like active framework.
* **Product workbook** = messy, rich, flexible, experimental control panel just for Product.

That’s a very healthy separation.

---

## 2️⃣ How to structure the “Scoring Inputs” tab

You said:

> “…each column is related to at least one or many frameworks. The name of each column should also indicate which framework(s) it belongs to.”

I’d shape it like this.

### Option A – Wide, namespaced columns per framework

Each row = one initiative (by key). Columns like:

| Initiative Key | RICE: Reach | RICE: Impact | RICE: Confidence | RICE: Effort | WSJF: Business Value | WSJF: Time Criticality | WSJF: Risk Reduction | WSJF: Job Size | Comments |
| -------------- | ----------- | ------------ | ---------------- | ------------ | -------------------- | ---------------------- | -------------------- | -------------- | -------- |

* Column header convention:

  * `<FRAMEWORK>: <parameter>` or `<framework>.<param>`

Backend logic:

* Read header row.
* Parse headers to detect:

  * `framework` (RICE / WSJF / MATH_MODEL / …)
  * `parameter_name` (`reach`, `impact`, `job_size`, etc.)
* For each row:

  * Look up `initiative_key`.
  * For each framework:

    * Collect all `framework: param` columns into a `ScoreInputs` instance.
    * Call `engine.compute()` for that framework.
    * Persist scores & optional comments.

This lets PMs:

* Add new columns like `RICE: Override Impact` without breaking anything.
* Add a new framework later (`MATH: parameter_1` etc.) and you just extend your header-to-input mapping rules.

### Option B – Long form (one row per initiative+framework)

Alternative schema where each row = (initiative, framework):

| Initiative Key | Framework | Param Name | Param Value | Scenario | Comment |
| -------------- | --------- | ---------- | ----------- | -------- | ------- |

This is more flexible but more complex for PMs to manage. For Sheets, **Option A** (wide with namespaced headers) is nicer UX.

I’d start with Option A.

---

## 3️⃣ How backend would plug this in

Architecturally, similar pattern to intake/backlog:

1. **Config for Product Workbook**

   * Add a new section in config / JSON, e.g.:

     ```json
     {
       "product_workbook": {
         "spreadsheet_id": "....",
         "tabs": {
           "scoring_inputs": "Scoring_Inputs",
           "config": "Config",
           "simulations": "Simulations"
         }
       }
     }
     ```

2. **New reader service** for scoring inputs

   * `app/sheets/scoring_inputs_reader.py`
   * Reads `Scoring_Inputs` tab:

     * Gets header row
     * Builds a mapping: `(framework, param_name) -> column_index`
     * Returns rows as:

       ```python
       List[{
         "initiative_key": "INIT-000001",
         "framework_inputs": {
             "RICE": {...ScoreInputs fields...},
             "WSJF": {...},
         }
       }]
       ```

3. **New job** for scoring from product sheet

   * `run_scoring_from_sheet(db)`:

     * Read scoring inputs from sheet.
     * For each row and framework:

       * Option A: override or complement values on `Initiative` (e.g. store these in `InitiativeScore.inputs_json` only).
       * Option B: treat these as the canonical inputs for scoring and skip Initiative fields.
     * Call `ScoringService` with those `ScoreInputs` (we may extend `score_initiative` to accept explicit `inputs` instead of deriving from Initiative fields).

4. **Back to central backlog**

   * Once scores are persisted to DB, Flow 1 backlog sync writes the final scores + active framework back to central backlog.

So the “product sheet scoring flow” is:

> Product sheet (Scoring_Inputs tab) → Scoring job → DB → Backlog sync → Central backlog sheet

Central backlog never sees all the messy knobs; just the outputs.

---

## 4️⃣ Config tab – replacing hardcoded config with sheet config

You also said:

> “we should reflect all the configs we are manually changing in `config.py` to a config tab… That config tab is the source of truth.”

I think that’s very powerful, *if* we do it selectively.

### Good candidates for sheet-based config

* `SCORING_DEFAULT_FRAMEWORK`
* `SCORING_BATCH_COMMIT_EVERY`
* Thresholds:

  * “Minimum confidence to accept RICE score”
  * “Maximum effort days for ‘quick wins’”
* Toggles:

  * Enable math models
  * Enable AI scoring
  * Whether to use history table or not
* Display-related config for backlog sheet:

  * Which columns to show / hide in view modes
* Per-org / per-team weights and coefficients.

### Less good candidates

* DB connection details
* Service account file paths
* Anything that belongs to infra/devops rather than product behavior.

### How to implement

Config tab schema could be as simple as:

| Key                        | Value | Type   | Scope   | Description                         |
| -------------------------- | ----- | ------ | ------- | ----------------------------------- |
| SCORING_DEFAULT_FRAMEWORK  | RICE  | string | global  | Default framework when none set     |
| SCORING_BATCH_COMMIT_EVERY | 200   | int    | scoring | Batch size for scoring jobs         |
| USE_AI_SUGGESTED_SCORES    | true  | bool   | scoring | Whether to use LLM-suggested scores |

Backend:

* New reader: `ConfigSheetReader` that reads `Config` tab into a dict.
* New small service: `ConfigService` that:

  * Merges:

    * `.env` / `config.py` defaults,
    * DB stored config (optional),
    * sheet-based overrides.
* Then `settings` in the runtime could be a composition: base config + dynamic config loaded at job start.

We don’t need to jump there right now, but your direction is absolutely sound: **product-behavior config belongs in a product-facing control surface, not in Python code**.

---

## 5️⃣ Simulation / Optimization tabs

This fits perfectly as a *third layer* in the same workbook:

* Tabs like:

  * `Simulations_Roadmap_v1`
  * `Capacity_Scenarios`
  * `MonteCarlo_Impact`

Each defines:

* Inputs: distributions, constraints, budgets, scenario labels.
* Backend runs:

  * Monte Carlo
  * Linear programming / MILP for capacity allocation
  * Multi-objective optimization (value vs risk vs cost)
* Outputs:

  * Recommended subsets of initiatives
  * Expected value & risk distributions
  * Visuals (which we might export as images or just numeric tables)

The pattern doesn’t change:

> Sheet tab = declarative scenario
> Backend = engine
> Central backlog or other sheets = rendered outcome

---

## 🧩 Updated Flow 3 – Product Ops Roadmap (with strong sync + multi-framework scoring)

Here’s a refined step-by-step plan reflecting everything we’ve aligned on:

---

### **Phase 3.A – Product Ops Workbook Plumbing**

**Goal:** Introduce the Product Ops workbook and basic wiring.

1. **Create Product Ops Google Sheet**

   * Spreadsheet: `Product Ops Workbook`
   * Tabs:

     * `Scoring_Inputs` (for now)
     * `Config` (for config-driven knobs, later)
     * `Simulations` (future)

2. **Share with service account**

   * Give Editor access to the same service account as other sheets.

3. **Add PRODUCT_OPS to config**

   * In JSON config (or a new one like `product_ops_config.json`):

     ```json
     {
       "product_ops": {
         "spreadsheet_id": "PRODUCT_OPS_SHEET_ID",
         "tabs": {
           "scoring_inputs": "Scoring_Inputs",
           "config": "Config"
         }
       }
     }
     ```

   * In `config.py`:

     ```python
     class ProductOpsConfig(BaseModel):
         spreadsheet_id: str
         scoring_inputs_tab: str = "Scoring_Inputs"
         config_tab: str = "Config"

     class Settings(BaseSettings):
         ...
         PRODUCT_OPS: Optional[ProductOpsConfig] = None
     ```

   * Extend the `model_validator` to load `PRODUCT_OPS` from that JSON, similar to `INTAKE_SHEETS`.

4. **Define v1 schema for `Scoring_Inputs` tab**

   Header row (simple starting point):

   | Initiative Key | RICE: Reach | RICE: Impact | RICE: Confidence | RICE: Effort | WSJF: Business Value | WSJF: Time Criticality | WSJF: Risk Reduction | WSJF: Job Size | RICE: Overall Score | WSJF: Overall Score | Comment |
   | -------------- | ----------- | ------------ | ---------------- | ------------ | -------------------- | ---------------------- | -------------------- | -------------- | ------------------- | ------------------- | ------- |

   * Namespacing rule:
     `"<FRAMEWORK>: <ParamName>"` for inputs and outputs.

   * Later we’ll extend with `MATH1: paramX`, `MATH1: Overall Score`, etc.

5. **Implement `ScoringInputsReader`**

   New file: `app/sheets/scoring_inputs_reader.py`

   Responsibilities:

   * Given `spreadsheet_id` + `tab_name`:

     * Read header row.

     * Parse each header:

       * If it matches `"<FW>: <Param>"`:

         * Extract `framework` (`RICE`, `WSJF`, etc.) and normalized `param_name`.

     * Read data rows.

     * For each row, build:

       ```python
       {
           "initiative_key": "INIT-000001",
           "inputs_by_framework": {
               "RICE": {"reach": ..., "impact": ..., "confidence": ..., "effort": ...},
               "WSJF": {"business_value": ..., "time_criticality": ..., "risk_reduction": ..., "job_size": ...},
           },
           "row_index": N,
       }
       ```

     * Output: list of such row dicts.

6. **Add Flow 3 job**

   New file: `app/jobs/flow3_product_ops_job.py`

   For now:

   ```python
   def run_flow3_scoring_inputs_preview(db: Session) -> None:
       if not settings.PRODUCT_OPS:
           raise ValueError("PRODUCT_OPS not configured")

       sheet_id = settings.PRODUCT_OPS.spreadsheet_id
       tab_name = settings.PRODUCT_OPS.scoring_inputs_tab

       rows = read_scoring_inputs(sheet_id, tab_name)
       # For v1, just log how many, and maybe some examples
   ```

   This gives us a runnable first step to confirm connectivity and parsing.

---

### **Phase 3.B – Strong Sync of Scoring Inputs (sheet → Initiative fields)**

**Goal:** Sheet becomes the master for framework inputs; Initiative fields mirror those inputs.

1. **Define the mapping: Scoring_Inputs columns → Initiative fields**

   Example (we can refine later, but define it explicitly):

   * `RICE: Reach` → `Initiative.rice_reach` (or reuse some existing generic field)

   * `RICE: Impact` → `Initiative.rice_impact`

   * `RICE: Confidence` → `Initiative.rice_confidence`

   * `RICE: Effort` → `Initiative.effort_engineering_days` or `Initiative.rice_effort`

   * `WSJF: Business Value` → `Initiative.wsjf_business_value`

   * `WSJF: Time Criticality` → `Initiative.time_sensitivity_score`

   * `WSJF: Risk Reduction` → `Initiative.wsjf_risk_reduction`

   * `WSJF: Job Size` → `Initiative.effort_engineering_days` or `Initiative.wsjf_job_size`

   If you don’t have those dedicated fields yet, we can:

   * Either add explicit fields (clean)
   * Or use some existing ones temporarily and document that mapping.

2. **Implement strong sync logic**

   In `flow3_product_ops_job.py`, implement:

   ```python
   def run_flow3_sync_inputs_to_initiatives(db: Session) -> None:
       # 1. Read rows from Scoring_Inputs (using ScoringInputsReader)
       # 2. For each row:
       #    - Find Initiative by initiative_key
       #    - For each (framework, param) input:
       #         - If cell is non-empty:
       #             initiative.<mapped_field> = parsed_value
       #         - If cell is empty:
       #             initiative.<mapped_field> = None
       # 3. Commit in batches
   ```

   This enforces:

   * Non-empty in sheet → explicit value in Initiative.
   * Empty in sheet → `None` in Initiative for that input.

   That’s your **strong sync** rule.

3. **ScoringService continues to work from Initiative fields**

   Now, when Flow 2 or Flow 3 builds `ScoreInputs` from an `Initiative`:

   * It uses these synced fields as the source of truth.
   * No hidden magic from older data.

---

### **Phase 3.C – Multi-framework scoring from Product Ops sheet**

**Goal:** Use Scoring_Inputs as the front-end for RICE and WSJF (and later Math) scoring, for multiple frameworks per initiative at once.

1. **Extend ScoringService or add helper to accept explicit `ScoreInputs`**

   * The `score_initiative_all_frameworks` method allows scoring an initiative using all available frameworks without changing the active scoring framework.
   * The `score_all_frameworks` method processes all initiatives in the database, computing scores for both RICE and WSJF frameworks.

2. **Implement Flow 3 scoring job from Product Ops**

   In `flow3_product_ops_job.py`:

   ```python
   def run_flow3_scoring_from_sheet(db: Session) -> None:
       # Precondition: strong sync already done (or we do both in this job)
       # 1. Read scoring inputs (to know which frameworks have inputs)
       # 2. For each row:
       #    - Get Initiative
       #    - For each framework that has any non-empty inputs:
       #         - Call ScoringService.score_initiative(initiative, framework)
       # 3. Commit
   ```

   Key behavior:

   - Per initiative, you may run both RICE and WSJF if inputs exist.
   - Multiple `InitiativeScore` rows are created (one per framework).
   - On the Product Ops sheet:
     - You can write the per-framework outputs into `RICE: Overall Score`, `WSJF: Overall Score`, etc.

3. **Write framework-specific outputs back to Scoring_Inputs tab**

   * Use the same header parsing as inputs (`"RICE: Overall Score"`, `"WSJF: Overall Score"`).
   * After scoring, build a row of output values and call `update_values` to write those cells for that row only.

   So each row on `Scoring_Inputs` shows all frameworks’ inputs and all frameworks’ scores for that initiative.

---

### **Phase 3.D – Config tab as control surface**

**Goal:** Move certain product-owned config knobs out of `config.py` into the Product Ops `Config` tab.

1. **Define v1 `Config` tab schema**

   Headers:

   | Key                        | Value | Type   | Scope   | Description |
   | -------------------------- | ----- | ------ | ------- | ----------- |
   | SCORING_DEFAULT_FRAMEWORK  | RICE  | string | scoring | ...         |
   | SCORING_BATCH_COMMIT_EVERY | 200   | int    | scoring | ...         |

2. **Implement `ConfigReader`**

   * `app/sheets/config_reader.py`:

     * Reads all rows where `Key` is non-empty.
     * Returns `dict[str, str]` mapping keys to raw values.

3. **Add `RuntimeConfig` or helper for overrides**

   At job start:

   * Read config sheet → `overrides`.
   * For any relevant key (`SCORING_DEFAULT_FRAMEWORK`, `SCORING_BATCH_COMMIT_EVERY`):

     * Use override if present, else fall back to `settings`.

4. **Use sheet-driven config in Flow 2 + Flow 3**

   * In scoring jobs:

     * Use `runtime_config.scoring_default_framework` (sheet override) instead of static `settings.SCORING_DEFAULT_FRAMEWORK`.
     * Same for `SCORING_BATCH_COMMIT_EVERY`.

---

### **Phase 3.E – Later: Simulations & Optimization tabs**

Once 3.A–C are stable:

* Add tabs like `Simulations`, `Capacity_Scenarios`.
* Define schemas for scenarios (constraints, budgets, segments).
* Implement readers & jobs that:

  * Run Monte Carlo / LP / multi-objective schedulers.
  * Write outputs back into result columns / result tabs.

Same pattern as before:

> Tab = configuration / scenario
> Backend = engine
> Sheet = place where PMs see & tweak the outcome

---

## 🧩 Flow 3 Implementation Status

### **Phase 3.A – Product Ops Workbook Plumbing** ✅ COMPLETE

**Goal:** Introduce the Product Ops workbook and basic wiring.

**Implemented:**
1. ✅ **Product Ops Google Sheet created**
   - Spreadsheet ID: `1zfxk-qQram2stUWYytiXapOeVh3yNulb32QYVJrOGt8`
   - Tab: `Scoring_Inputs`

2. ✅ **Service account access configured**
   - Sheet shared with service account
   - Read/write permissions verified

3. ✅ **Configuration in place**
   - `product_ops_config.json` created with:
     ```json
     {
       "spreadsheet_id": "1zfxk-qQram2stUWYytiXapOeVh3yNulb32QYVJrOGt8",
       "scoring_inputs_tab": "Scoring_Inputs",
       "config_tab": "Config"
     }
     ```
   - Environment variable: `PRODUCT_OPS_CONFIG_FILE=product_ops_config.json`

4. ✅ **`Scoring_Inputs` schema implemented**
   - Headers support both formats:
     - Namespaced: `RICE: Reach`, `WSJF: Business Value`
     - Underscore: `rice_reach`, `wsjf_business_value`
   - Input columns (PM-editable):
     - `initiative_key`
     - `active_scoring_framework`
     - `use_math_model`
     - `rice_reach`, `rice_impact`, `rice_confidence`, `rice_effort`
     - `wsjf_business_value`, `wsjf_time_criticality`, `wsjf_risk_reduction`, `wsjf_job_size`
     - `strategic_priority_coefficient`
   - Output columns (system-populated):
     - `rice_value_score`, `rice_effort_score`, `rice_overall_score`
     - `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`

5. ✅ **`ScoringInputsReader` implemented**
   - File: `app/sheets/scoring_inputs_reader.py`
   - Features:
     - Flexible header parsing (handles both `RICE: Reach` and `rice_reach` formats)
     - Per-row parsing into framework-specific inputs
     - Returns structured data: `{initiative_key, active_framework, rice_{params}, wsjf_{params}}`

6. ✅ **Flow 3 job implemented**
   - File: `app/jobs/flow3_product_ops_job.py`
   - Commands:
     - `--preview`: Validate sheet inputs
     - `--sync`: Strong sync sheet → DB
     - `--compute-all`: Compute RICE & WSJF for all initiatives
     - `--write-scores`: Write per-framework scores back to sheet

7. ✅ **CLI implemented**
   - File: `test_scripts/flow3_product_ops_cli.py`
   - Custom logging formatter for detailed per-row tracking

---

### **Phase 3.B – Strong Sync of Scoring Inputs** ✅ COMPLETE

**Goal:** Sheet becomes the master for framework inputs; Initiative fields mirror those inputs.

**Implemented:**
1. ✅ **Field mapping defined and implemented**
   - Sheet column → DB field mapping:
     - `rice_reach` → `Initiative.rice_reach`
     - `rice_impact` → `Initiative.rice_impact`
     - `rice_confidence` → `Initiative.rice_confidence`
     - `rice_effort` → `Initiative.rice_effort`
     - `wsjf_business_value` → `Initiative.wsjf_business_value`
     - `wsjf_time_criticality` → `Initiative.wsjf_time_criticality`
     - `wsjf_risk_reduction` → `Initiative.wsjf_risk_reduction`
     - `wsjf_job_size` → `Initiative.wsjf_job_size`
     - `active_scoring_framework` → `Initiative.active_scoring_framework`
     - `strategic_priority_coefficient` → `Initiative.strategic_priority_coefficient`

2. ✅ **Strong sync logic implemented**
   - Function: `run_flow3_sync_inputs_to_initiatives(db, commit_every, spreadsheet_id, tab_name)`
   - Behavior:
     - Non-empty cell in sheet → explicit value in Initiative
     - Empty cell in sheet → `None` in Initiative (clears old values)
     - Sets `updated_source = 'flow3.productopssheet_read_inputs'` for audit trail (per `app/utils/provenance.py`)
   - Batch commit support for performance

3. ✅ **Tested and validated**
   - Successfully synced 10 initiatives from Product Ops sheet
   - Verified field values match sheet inputs exactly
   - Confirmed empty cells clear DB values (strong sync enforcement)

---

### **Phase 3.C – Multi-Framework Scoring** ✅ COMPLETE

**Goal:** Compute and store RICE and WSJF scores side-by-side for comparison.

**Implemented:**
1. ✅ **Per-framework score storage in DB**
   - Migration: `20251204_per_fw_scores.py`
   - New DB columns on `Initiative`:
     - `rice_value_score`, `rice_effort_score`, `rice_overall_score`
     - `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`

2. ✅ **ScoringService enhancements**
   - `_compute_framework_scores_only(initiative, framework, enable_history)`:
     - Computes scores for a specific framework
     - Updates **only** per-framework score fields
     - **Does NOT** change `active_scoring_framework` or active score fields
     - Prevents side effects during multi-framework scoring
   
   - `score_initiative_all_frameworks(initiative, enable_history)`:
     - Scores one initiative with **all** frameworks (RICE + WSJF)
     - Stores results in per-framework fields
     - Used by Flow 3 for side-by-side comparison
   
   - `score_all_frameworks(commit_every)`:
     - Batch version: processes all initiatives
     - Computes both RICE and WSJF for every initiative
     - Efficient batch commits

3. ✅ **Product Ops writer implemented**
   - File: `app/sheets/productops_writer.py`
   - Function: `write_scores_to_productops_sheet(db, client, spreadsheet_id, tab_name)`
   - Features:
     - Reads all initiatives from DB
     - Maps score columns in sheet header
     - Builds batch update payload for all score cells
     - Uses `SheetsClient.batch_update_values()` for efficient single API call
     - Updates columns: `rice_value_score`, `rice_effort_score`, `rice_overall_score`, `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`

4. ✅ **Tested and validated**
   - Successfully computed RICE and WSJF scores for 10+ initiatives
   - Verified per-framework scores stored correctly in DB
   - Confirmed scores written back to Product Ops sheet
   - Verified active scoring framework remains unchanged during compute-all

---

### **Phase 3.D – Config Tab** ⏳ PLANNED (Not Implemented)

**Goal:** Move product-owned config knobs from `config.py` to Product Ops `Config` tab.

**Planned features:**
1. ⏳ **Config tab schema**
   - Headers: `Key`, `Value`, `Type`, `Scope`, `Description`
   - Example configs:
     - `SCORING_DEFAULT_FRAMEWORK`: Default framework when none set
     - `SCORING_BATCH_COMMIT_EVERY`: Batch commit size
     - `USE_AI_SUGGESTED_SCORES`: Enable/disable AI scoring

2. ⏳ **ConfigReader implementation**
   - Read `Config` tab into `dict[str, str]`
   - Merge with code-based defaults

3. ⏳ **Runtime config service**
   - Priority: CLI override > Sheet config > Code defaults
   - Used by Flow 2 and Flow 3 jobs

**Why not implemented yet:**
- Phase 3.A-C provide core functionality
- Config extraction should be driven by actual usage pain points
- Better to consolidate and test 3.A-C first

**Next steps for 3.D:**
- Document which configs PMs actually need to change
- Implement `ConfigReader`
- Add runtime config merging logic
- Test with Flow 2 and Flow 3

---

### **Phase 3.E – Simulations & Optimization** 📋 FUTURE

**Goal:** Enable scenario planning and optimization.

**Planned features:**
- Monte Carlo simulations for risk/uncertainty
- Capacity planning and allocation
- Multi-objective optimization (value vs. cost vs. risk)
- Scenario tabs for "what-if" analysis

**Dependencies:**
- Stable Phase 3.A-C pipeline
- Production usage and feedback
- Clear PM requirements for simulation/optimization needs

---

## 🎯 Current System State (As of 2025-12-09)

### ✅ What Works End-to-End

**Full Flow 3 Pipeline:**
```bash
# 1. Preview inputs from Product Ops sheet
uv run python -m test_scripts.flow3_product_ops_cli --preview

# 2. Sync inputs from sheet to DB (strong sync)
uv run python -m test_scripts.flow3_product_ops_cli --sync

# 3. Compute RICE and WSJF scores for all initiatives
uv run python -m test_scripts.flow3_product_ops_cli --compute-all

# 4. Write per-framework scores back to Product Ops sheet
uv run python -m test_scripts.flow3_product_ops_cli --write-scores
```

**Integration with Flow 1 (Backlog Sync):**
- Active scores from DB → Central Backlog sheet
- PMs can switch `active_scoring_framework` on Central Backlog
- Backlog displays the active framework's scores

**Integration with Flow 2 (Active Scoring):**
- Respects `active_scoring_framework` from Product Ops sheet
- Updates active score fields (`value_score`, `effort_score`, `overall_score`)
- Does NOT interfere with per-framework scores

### 📊 Data Flow Architecture

```
Product Ops Sheet (Scoring_Inputs)
         ↓
    [Flow 3 Sync]
         ↓
    Initiative DB fields (rice_*, wsjf_*, active_scoring_framework)
         ↓
    [Flow 3 Compute All] → Per-framework scores (rice_*_score, wsjf_*_score)
         ↓                          ↓
    [Flow 3 Write]          [Flow 2 Active Scoring] → Active scores (value_score, overall_score)
         ↓                          ↓
Product Ops Sheet (outputs)    Central Backlog Sheet (active scores only)
```

### 🔧 Key Design Decisions

1. **Strong Sync Enforcement**
   - Product Ops sheet is source of truth for inputs
   - Empty cells in sheet → `None` in DB (clears stale data)
   - No silent fallbacks or hidden defaults

2. **Per-Framework Score Isolation**
   - `score_all_frameworks()` only touches per-framework fields
   - Active scoring framework selection remains independent
   - PMs can compare RICE vs. WSJF without losing data

3. **Separation of Concerns**
   - Flow 3: Product Ops experimentation (all frameworks)
   - Flow 2: Active scoring decision (one framework)
   - Flow 1: Backlog presentation (active framework only)

4. **Efficient Batch Operations**
   - Single API call for writing all scores (`batch_update_values`)
   - Batch commits every N initiatives (configurable)
   - Targeted cell updates (no full sheet regeneration)

---

## 📝 Next Steps

### Immediate (Recommended)
1. ✅ **Test Flow 1 integration** (verify Central Backlog sync)
2. ✅ **Test framework switching** (change active framework, verify scores update)
3. ⏳ **Document PM user guide** (how to use Product Ops sheet)
4. ⏳ **Add integration tests** (full Flow 3 pipeline)

### Short-term (When Needed)
1. ⏳ **Implement Phase 3.D** (Config tab) if config changes become frequent
2. ⏳ **Add validation rules** (e.g., "Reach must be > 0")
3. ⏳ **Add error recovery** (retry logic, partial failures)

### Long-term (Future)
1. 📋 **Phase 3.E** (Simulations & Optimization)
2. 📋 **Math Model scoring framework** (custom formulas)
3. 📋 **AI-assisted parameter suggestions**

---

## 🎉 New Feature: Populate Initiatives from Database

### Overview
A new PM action `pm.populate_initiatives` enables Product Managers to automatically populate the Scoring_Inputs tab with optimization candidate initiatives from the database.

### Workflow
1. **Mark candidates in Central Backlog**: PM sets `Is Optimization Candidate = TRUE` for desired initiatives
2. **Navigate to Scoring_Inputs**: PM opens the Scoring_Inputs tab in Product Ops sheet
3. **Run action**: PM clicks "Populate Initiatives" from the Roadmap AI menu
4. **Backend processing**:
   - Queries all initiatives where `is_optimization_candidate = TRUE`
   - Reads existing initiative keys from Scoring_Inputs tab using `ScoringInputsReader`
   - Normalizes keys for robust matching (handles `INIT-4` vs `INIT-0004` variants)
   - Appends only new initiatives using dedicated writer helper
   - Writes only the `initiative_key` column; other columns remain blank
5. **Continue workflow**: PM can now edit framework parameters and run "Score Selected"

### Technical Details

**Backend Components:**
- **Job function**: `app/jobs/flow3_product_ops_job.py::run_flow3_populate_initiatives()`
  - Uses `ScoringInputsReader` abstraction for reading existing keys
  - Uses `normalize_initiative_key()` for robust key comparison (handles `INIT-4`, `INIT_4`, `init0004`)
  - Uses `append_initiative_keys_to_scoring_inputs()` writer helper
  - Accepts `SheetsClient` from caller (no redundant client creation)
- **Action handler**: `app/services/action_runner.py::_action_pm_populate_initiatives()`
  - Validates tab matches configured `scoring_inputs_tab` (rejects wrong-tab triggers)
  - Raises exceptions on failure (ensures proper `STATUS_FAILED` in ActionRuns)
  - Passes existing `ctx.sheets_client` to job
- **Writer helper**: `app/sheets/productops_writer.py::append_initiative_keys_to_scoring_inputs()`
  - Robust row detection (handles sparse sheets, gaps)
  - Batch writes for efficiency
- **Summary extraction**: `_extract_summary()` includes `pm.populate_initiatives` branch
  - `total` = total_candidates
  - `success` = newly_added
  - `skipped` = existing_in_sheet
  - `failed` = failed_count

**Frontend (AppScript):**
- **Function**: `uiPopulateInitiatives()` in `docs/appscripts/productops_appscripts.md`
- **User confirmation**: Shows dialog before execution
- **Result display**: Shows count of total candidates, existing, and newly added

**Action Registry:**
- Registered as `"pm.populate_initiatives"` in action registry
- Tab: Scoring_Inputs (Product Ops sheet)
- Scope: Operates on all optimization candidates (no selection required)

### Production-Grade Features
- **Key normalization**: Uses `normalize_initiative_key()` for robust matching
  - `INIT-4`, `INIT-0004`, `init_4`, `INIT_4` all match correctly
  - Prevents duplicates from formatting variance
- **Tab validation**: Rejects requests targeting wrong tab
- **Proper error handling**: Raises exceptions on failure → ActionRun status = `failed`
- **Reader/writer abstractions**: Uses `ScoringInputsReader` and dedicated writer helper
- **Sparse sheet handling**: Writer scans full column to find last data row (no blank-run cutoff)
- **Client reuse**: Uses existing `ctx.sheets_client` (consistent with action runner pattern)

### Benefits
- **Eliminates manual data entry**: No need to copy initiative keys between sheets
- **Prevents cross-sheet formula brittleness**: Uses programmatic DB→Sheet sync instead of fragile inter-sheet formulas
- **Supports optimization workflow**: Clean handoff from backlog curation to scoring process
- **Scalable**: Handles large candidate sets efficiently with batch operations
- **Robust**: Key normalization prevents duplicates from formatting variance

### Example Usage
```javascript
// AppScript menu trigger
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Roadmap AI')
    .addItem('Populate Initiatives', 'uiPopulateInitiatives')
    .addItem('Score Selected', 'uiScoreSelected')
    .addItem('Save Selected', 'uiSaveSelected')
    .addToUi();
}
```

### Result Format
```json
{
  "pm_job": "pm.populate_initiatives",
  "tab": "Scoring_Inputs",
  "total_candidates": 25,
  "existing_in_sheet": 15,
  "newly_added": 10,
  "substeps": [
    {"step": "populate_from_db", "status": "ok", "count": 10}
  ]
}
```

### UI Summary (via _extract_summary)
```json
{
  "total": 25,
  "success": 10,
  "skipped": 15,
  "failed": 0
}
```

---

## 🐛 Known Issues / Limitations

1. **`---` separator rows in Product Ops sheet**
   - Warning logged but harmless
   - Skipped during sync (no DB entry exists)
   - Consider: Add validation to reject invalid initiative keys

2. **No conflict resolution for concurrent edits**
   - Last write wins (sheet → DB)
   - Consider: Add timestamp/version tracking

3. **No rollback mechanism**
   - Strong sync is irreversible without manual DB restore
   - Consider: Add "preview mode" that shows diff before committing

4. **No input validation**
   - Accepts any numeric values (could be negative, zero, etc.)
   - Consider: Add validation rules per parameter

---
The Complete Flow:

1. Flow 3 --sync          → Update initiative inputs in DB
2. Flow 3 --compute-all   → Compute RICE + WSJF scores (per-framework fields)
3. Flow 3 --write-scores  → Write per-framework scores to Product Ops
4. Flow 2 --all           → Update ACTIVE scores from per-framework scores ⬅️ THIS WAS MISSING
5. Flow 1 (backlog sync)  → Write active scores to Central Backlog

---

## Authoritative Propagation Path (Concise)

1) Product Ops changes → Flow 3 `--sync` (Sheet → DB)
2) Flow 3 `--compute-all` (per-framework only: `rice_value_score`, `rice_overall_score`, `wsjf_value_score`, `wsjf_overall_score`)
3) Flow 3 `--write-scores` (DB → Product Ops sheet, per-framework columns)
4) Flow 2 `--all` (Activate: copy per-framework based on `active_scoring_framework` into `value_score`, `overall_score`, and `effort_score` when applicable)
5) Flow 1 Backlog Sync (DB → Central Backlog)

Notes

- Flow 3 does NOT update `value_score`/`overall_score`; Flow 2 is REQUIRED to activate RICE/WSJF into active fields.
- Header normalization supports underscore variants (e.g., `active_scoring_framework`).

## Framework Switching: Central Backlog Test Case

Scenario: Change `active_scoring_framework` on Central Backlog (e.g., WSJF → RICE).

Steps:
- Backlog Update (Sheet → DB): run `run_backlog_update` (or CLI) to pull the change into DB.
- Flow 2 `--all`: update `value_score`/`overall_score` from the chosen per-framework fields.
- Backlog Sync: push updated active scores back to Central Backlog (DB → Sheet).