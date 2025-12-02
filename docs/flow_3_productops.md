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

   * Option A: add `score_initiative_with_inputs(initiative, framework, inputs)` that:

     * Uses `inputs` directly.
     * Still updates `Initiative` & `InitiativeScore` as now.
   * Option B: keep existing `score_initiative` and just ensure Initiative fields are up-to-date (since strong sync already did that).

   With strong sync, **Option B is enough**:

   * Flow 3:

     * Sync sheet values → Initiative fields.
     * Call existing `score_initiative(initiative, framework, ...)`.
   * The merge behavior is: sheet wrote into Initiative; scoring uses Initiative.

2. **Implement Flow 3 scoring job from Product Ops**

   In `flow3_product_ops_job.py`:

   ````python
   def run_flow3_scoring_from_sheet(db: Session) -> None:
       # Precondition: strong sync already done (or we do both in this job)
       # 1. Read scoring inputs (to know which frameworks have inputs)
       # 2. For each row:
       #    - Get Initiative
       #    - For each framework that has any non-empty inputs:
       #         - Decide: do we store multiple framework scores in InitiativeScore only?
       #         - Or also set Initiative.active_scoring_framework when appropriate
       #    - Call ScoringService.score_initiative(initiative, framework)
       # 3. Commit
       ```

   Key behavior:

   - Per initiative, you may run both RICE and WSJF if inputs exist.
   - Multiple `InitiativeScore` rows are created (one per framework).
   - On the Product Ops sheet:
     - You can write the per-framework outputs into `RICE: Overall Score`, `WSJF: Overall Score`, etc.

   ````

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

If you like, next concrete step would be:

👉 Start with **Phase 3.A + 3.B**:

* Create Product Ops workbook.
* Wire `PRODUCT_OPS` into config.
* Implement `ScoringInputsReader`.
* Implement strong sync job: read `Scoring_Inputs` → write to Initiative fields (with empty ⇒ `None` semantics).

Once that’s in, we can plug in scoring and sheet outputs on top.
