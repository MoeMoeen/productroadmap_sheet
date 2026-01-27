
# **Project Charter — Product Roadmap Intelligence Platform**

*(Python backend + Google Sheets frontend)*

## **1. Project Name**

**Product Roadmap Intelligence Platform (PRIP)**
A hybrid AI-powered system combining Google Sheets as the organizational UI with a Python backend for scoring, prioritization, and portfolio optimization.

---

## **2. Project Purpose & Vision**

The platform provides a **unified, intelligent, and structured** way for all departments to propose product initiatives, submit context, and collaborate with Product, Engineering, Finance, and Analytics on impact modeling, effort estimation, and prioritization.

The system transforms scattered requests into a **clean, dynamic, mathematically optimized roadmap**, powered by:

* AI-assisted value modeling
* Multi-framework scoring (RICE, WSJF, custom)
* Parameterized mathematical formulas
* Portfolio optimization & resource allocation
* Normalized, clean data structures across the whole organization
* **Sheet-native execution & control plane** (PM-driven triggers from Google Sheets)

Ultimately, the platform becomes the **single source of truth** for product decisions.

---

## **3. High-Level Goals**

### **3.1 Operational Goals**

* Create a **clean, centralized backlog** consolidating all initiative requests.
* Standardize initiative intake across departments.
* Ensure data completeness through automated validation and LLM-assisted checks.
* Provide transparent status tracking and collaboration workflows.
* **Enable PMs to trigger all scoring/activation flows from Google Sheets without terminal access.** *(Phase 4.5)*

### **3.2 Analytical & AI Goals**

* Support **multiple scoring frameworks**, including:

  * RICE
  * WSJF
  * Custom frameworks
  * Full mathematical-model scoring
  * LLM-assisted math model suggestion + explicit parameter seeding
* Auto-generate formulas and parameters using LLMs.
* Maintain consistent, normalized scoring data sets.
* Support Monte Carlo simulation and multi-objective prioritization.

### **3.3 Strategic Goals**

* Enable Product to make **quantifiable, defensible** decisions.
* Link initiatives to business objectives and strategic priorities.
* Provide PMs with powerful analysis while keeping Sheets as the day-to-day UI.
* Scale with organization growth without data chaos.
* **Establish sheet-native execution as a hard prerequisite before optimization.** *(Phase 4.5)*

---

## **4. Core Components**

### **4.1 Frontend (Google Sheets)**

* **Central Backlog Sheet**

  * One row per initiative
  * Clean fields, scores, meta, status, hypotheses
* **MathModels Sheet**

  * **Multiple rows per initiative** - each initiative can have multiple math models targeting different KPIs
  * **Columns**: initiative_key, model_name, target_kpi_key, metric_chain_text, formula_text, is_primary, computed_score, approved_by_user
  * **Metric Chain Flow**: PM documents "immediate_kpi → intermediate_kpi → target_kpi" (e.g., "signups → activation → revenue")
  * **KPI Targeting**: Each model specifies which KPI it impacts via target_kpi_key (north_star or strategic KPIs)
  * **Primary Model**: One model marked is_primary=true serves as representative score for displays
  * **Workflow**: Define metric chain → Suggest formula via LLM → PM review/approve → Seed Params → Fill values → Save → Score → KPI contributions computed
* **Params Sheet**

  * One row per (initiative, framework, parameter)
  * Centrally normalized parameter definition & approval workflow

### **4.2 Backend (Python)**

* **Sheets Integration Layer** (Google Sheets API)
* **Data model & DB** (SQLAlchemy ORM)
* **Action API** *(New in Phase 4.5)*

  * Single entry point: `POST /actions/run`
  * Validates action + scope, enqueues async job, returns `run_id`
  * Status polling: `GET /actions/run/{run_id}`
  * Backed by ActionRun execution ledger
* **Scoring Engine**

  * Framework factory (RICE, WSJF, MathModel, Custom frameworks)
  * LLM-assisted formula generation
  * Parameter auto-seeding (now via explicit PM job `pm.seed_math_params`)
* **Optimization Engine**

  * Linear / non-linear optimization
  * Multi-objective prioritization
  * Monte Carlo simulation
* **Validation & Notification Services**
* **Roadmap Generator**

  * Produces quarterly/annual roadmap versions
  * Supports scenarios (“growth-heavy”, “risk-minimizing”, etc.)

---

## **5. High-Level Workflow**

### **Phase 0–3: Scoring Setup** (Existing)

1. **Departments submit initiatives** → Intake to central backlog.
2. **Validation service** flags missing fields + auto-suggests improvements.
3. **PM chooses scoring framework** (e.g., RICE, WSJF, MathModel) in Central Backlog.
4. **Flow 3 – Product Ops Scoring** (optional for multi-framework comparison):
   - Backend seeds parameters → Product Ops sheet.
   - PM fills inputs, backend computes RICE + WSJF per-framework scores.
5. **Flow 2 – Score Activation** (required bridge):
   - Backend copies per-framework scores to active fields based on `active_scoring_framework`.
   - Active scores ready for optimization and Central Backlog sync.
6. **PM and stakeholders review/override scores** if needed.

### **Phase 4.5: Sheet-Native Execution & Control Plane** *(New)*

All flows (0–4) are now **triggerable from Google Sheets** via a custom menu:

#### **UI Layer (Apps Script)**

* Custom menu in ProductOps & Intake sheets: **"Roadmap AI"**
* Menu actions (examples):
  * Compute scores (all frameworks)
  * Write scores back to ProductOps
  * Activate framework (AUTO / forced)
  * Sync Central Backlog
  * Suggest Math Models (LLM, selected rows) — `pm.suggest_math_model_llm`
  * Seed Params (approved models) — `pm.seed_math_params`
  * Sync MathModels → DB
  * Sync Params → DB
  * Sync Intake → DB

* Flow per menu item:
  1. Collect scope (selected rows / all rows / filtered)
  2. Send `POST /actions/run` with action + scope
  3. Write run row to Control tab
  4. Poll `GET /actions/run/{run_id}` for status updates
  5. Display results (updated counts, errors)

#### **Backend Layer (Action API)**

* **Endpoint:** `POST /actions/run`
  * **Input:** `action`, `scope`, `sheet_context`, `options`, `requested_by`
  * **Output:** `{run_id, status: "queued"}`

* **Endpoint:** `GET /actions/run/{run_id}`
  * **Output:** `{run_id, status, started_at, finished_at, result, error}`

* **Action → Implementation Mapping:**

  | Action | Backend Callable |
  |--------|------------------|
  | `flow3.compute_all_frameworks` | `ScoringService.compute_all_frameworks()` |
  | `flow3.write_scores` | `write_flow3_scores_to_sheet()` |
  | `flow2.activate` | `run_scoring_activation()` |
  | `flow1.backlog_sync` | `run_all_backlog_sync()` |
  | `flow4.suggest_mathmodels` | `run_math_model_generation_job()` |
  | `flow4.seed_params` | `run_param_seeding_job()` |
  | `flow4.sync_mathmodels` | `MathModelSyncService.sync_sheet_to_db()` |
  | `flow4.sync_params` | `ParamsSyncService.sync_sheet_to_db()` |
  | `flow0.intake_sync` | `run_sync_all_intake_sheets()` |

#### **Status Surface (Control / RunLog Tab)**

* Dedicated tab in ProductOps (and optionally Intake)
* Columns: timestamp, run_id, action, scope_summary, status, started_at, finished_at, result_summary, error_snippet
* Live updates as job progresses
* Enables PM confidence, auditability, "did it run?" clarity

### **Phase 5+: Portfolio Optimization & Roadmap Generation**

7. **PM defines optimization scenario** in Optimization Center sheet:
   - Objective mode (north_star, weighted_kpis, lexicographic)
   - Objective weights (if weighted_kpis mode)
   - Capacity constraints (total tokens, per-dimension floors/caps)
   - KPI targets (constraints for all optimization modes, normalization scale for weighted_kpis mode)
   - Governance rules (mandatory initiatives, bundles, exclusions, prerequisites, synergy bonuses)
8. **Backend computes optimized portfolio** based on constraints (capacity, dependencies, strategic themes)
9. **Roadmap entries** are generated, versioned, and published.

---

## **6. Success Criteria**

### **Quantitative**

* 100% initiatives centrally tracked.
* 90%+ initiative entries complete (no missing core fields).
* 100% scoring frameworks executed programmatically.
* Significant reduction in manual spreadsheet engineering.
* Faster roadmap decision-cycle time (e.g., cut from weeks → days).

### **Qualitative**

* PMs trust scoring & prioritization outputs.
* Stakeholders understand “why initiative X is selected.”
* Increased transparency and alignment across departments.
* Improved strategic planning confidence and defensibility.

---

## **7. Key Stakeholders**

* **CPO / Head of Product** — Owner of prioritization logic.
* **Product Managers** — Define initiatives, formulas, parameters.
* **Engineering Leads** — Provide effort inputs.
* **Analytics/Finance** — Provide parameter values, validate assumptions.
* **All Departments** — Submit ideas through intake sheets.
* **AI/Backend Owner (You)** — Build, maintain, and evolve the system.

---

## **8. Rollout (Phase 4.5)**

### **Step 1: Backend Plumbing**
1. Add `ActionRun` ORM + migration
2. Build `app/api/actions.py` + `app/schemas/actions.py`
3. Build `app/services/action_runner.py`
4. Wire all 7 actions to their callables

### **Step 2: Apps Script UI**
1. Deploy custom menu in ProductOps sheet
2. Implement menu items → HTTP calls → `POST /actions/run`
3. Add Control tab with headers
4. Add polling logic → `GET /actions/run/{run_id}`
5. Live-update Control tab with results

### **Step 3: E2E Testing & Refinement**
1. Test each action (selected rows, all rows, filtered scope)
2. Test error handling (missing fields, invalid scopes)
3. Verify Control tab shows correct counts/status
4. Security validation (secret header, no data leaks)

### **Step 4: Documentation**
1. Update runbook: "How to trigger actions from Sheets"
2. Add Control tab interpretation guide
3. Document each action (scope options, expected results, error codes)

---

## **9. Phase 5 Status (In Progress - January 2026)**

Phase 5 foundational work has begun:

**Completed:**
* **Data Models & Schemas**: OptimizationScenario, OptimizationConstraintSet, OptimizationRun (DB models + Pydantic schemas)
* **Constraint Types**: Discriminated union with 9 types (capacity_floor, capacity_cap, mandatory, bundle, exclusion_pair, exclusion_initiative, prerequisite, synergy_bonus, targets)
* **Prerequisites Refactoring**: Migrated from `List[List[str]]` to `Dict[str, List[str]]` for O(1) lookup and semantic clarity (migration r20260109_prereq_dict)
* **Constraint Entry Separation** ✅ **(Jan 19, 2026)**:
  - **Constraints tab is sole entry surface** for all constraint types
  - **Candidates tab is read-only** for constraints (display-only indicators)
  - Removed Initiative-level constraint columns: `is_mandatory`, `mandate_reason`, `bundle_key`, `prerequisite_keys`, `exclusion_keys`, `synergy_group_keys`
  - Migration r20260119_drop_init_constr applied (breaking change - no backward compatibility)
  - Editable fields on Candidates shrunk to: `engineering_tokens`, `deadline_date`, `notes`, `is_selected_for_run`
* **Multi-Dimensional Targets**: Nested 3-level structure `{dimension: {dimension_key: {kpi_key: {type, value, notes?}}}}` supporting country, product, cross-sectional, and global targets
* **Sheet Readers/Writers**: Optimization Center tabs (Scenario_Config, Constraints, Targets) with header alias support and composite key scoping
* **Constraint Compiler**: Pure compilation service (validates, normalizes, buckets, deduplicates sheet rows into JSON constraint set)
* **Documentation**: Complete JSON shapes, PM guidance, glossary, implementation roadmap, status check-in

**ProductOps Config (Complete - Jan 22-25, 2026):**
* ~~ProductOps Metrics_Config tab (KPI universe: keys, names, levels, units)~~ ✅ **COMPLETE (Jan 22, 2026)**
* ~~ProductOps KPI_Contributions tab (kpi_contribution_json entry surface)~~ ✅ **COMPLETE (Jan 22, 2026)**
* ~~OrganizationMetricsConfig DB model~~ ✅ **COMPLETE (Jan 25, 2026)**
  - Migration r20260122_metric_chain moved metric_chain from Initiative to InitiativeMathModel
  - Migration r5ba3359a91c0_rename_level_to_kpi_level fixed column name mismatch (level → kpi_level)
  - Migration 20260125_add_metrics_config_columns added description, is_active (Boolean, default=true), notes columns
  - MetricsConfigSyncService: Sheet → DB sync with validation (only north_star/strategic, exactly one active north_star)
  - KPIContributionsSyncService: Sheet → DB sync with pm_override protection
  - KPI contributions now auto-computed from math model scores via kpi_contribution_adapter
  - PM can override via KPI_Contributions tab → sets kpi_contribution_source = "pm_override"

**Optimization Engine (In Progress - Jan 2026):**
* ~~Solver adapter interface design (OptimizationProblem, SolverAdapter protocol)~~ ✅ **COMPLETE**
* ~~Linear solver integration (OR-Tools CP-SAT)~~ ✅ **COMPLETE**
* ~~Portfolio selection algorithm with capacity + dependency constraints~~ ✅ **COMPLETE (Steps 1-7)**
* ~~Step 8.1 north_star objective mode~~ ✅ **COMPLETE (Jan 25, 2026)**
* ~~Step 8.2 weighted_kpis objective mode~~ ✅ **COMPLETE (Jan 25, 2026)**
* Step 8.3 lexicographic objective mode (TODO)
* Results publishing to sheets (TODO)
* Sheet-native execution via `pm.run_optimization` action (TODO)

All optimization runs will be triggered via Phase 4.5 control plane menu → `pm.run_optimization`.

---

# **Further Key Information**

## 1. Overall architecture (mental picture)

Python + Google Sheets is actually a very nice combo for this kind of internal “roadmap OS.

Conceptually:

* Initiative is the core domain entity.

* Backlog is: “all initiatives (in all states)”.

* Roadmap is: “a chosen subset of initiatives that are approved in principle, plus metadata about when/how they’re delivered”.

Think of it as 5 layers:

1. **Spreadsheet UI layer (Google Sheets)**

   * Each department / country has its own “Idea Intake” sheet in a standard template.
   * There is one **central product backlog sheet** that shows the consolidated, cleaned view.

2. **Sync & Data Model layer (Python)**

   * Python service regularly reads all intake sheets via Google Sheets API.
   * Normalizes them into a canonical schema (your “initiative” model).
   * Stores them in a **back-end data store** (could be just in memory at first, but ideally a DB like Postgres).

3. **Validation & Enrichment layer (Python + LLM)**

   * Checks each initiative against required fields & business rules.
   * Fills some fields automatically (e.g. derived metrics, value scores) and flags missing info.
   * Uses LLMs to:

     * Summarize context.
     * Suggest impact/value ranges.
     * Suggest effort / T-shirt size (for initial guess).

4. **Optimization & Simulation layer (Python OR / sim)**

   * Linear / mixed-integer optimization for portfolio selection.
   * Optional non-linear / multi-objective + Monte Carlo for uncertainty.
   * Produces prioritized, capacity-feasible “roadmap portfolios” / scenarios.

5. **Feedback & Output layer (Sheets + Notifications)**

   * Writes statuses, scores and priorities back into:

     * The central backlog sheet (for product).
     * Possibly each department’s sheet (e.g. “status: missing info”, “approved”, “scheduled Q3”).
   * Sends notifications (email/Slack) for:

     * Missing info.
     * Requests sent to engineering for estimates.
     * New prioritization run results.

All of this can be orchestrated with **one Python service** + **Google Sheets templates**.

---

## 2. How the spreadsheet side would actually work

### a) Templates for each department

You define a standard template, e.g. columns like:

* `initiative_id` (hidden or generated)
* `title`
* `requesting_team`
* `requester_name`
* `country / market`
* `problem_statement`
* `desired_outcome`
* `target_metrics` (e.g. uplift in conversion, GMV, NPS)
* `strategic_theme` (enum / dropdown)
* `dependencies`
* `deadline / time sensitivity`
* `assumed_value_low / expected / high`
* `effort_tshirt_size` (if they can guess)
* `status` (new / needs_info / under_review / approved / rejected)
* `product_owner`, etc.

Each country/department gets a **copy** of this sheet in their own workspace, with minimal formulas and clear constraints.

### b) Consolidation into a central backlog

Python cron job (or a small web service triggered by Sheets / Apps Script):

* Pulls all rows from each department intake sheet that are `status in {new, needs_info, under_review, approved}`.
* Ensures each one has a unique `initiative_id` (generate if missing).
* Normalizes into a central table (in DB and/or central Google Sheet).

From a *user*’s perspective: “I just log ideas in my sheet; product sees everything in the central backlog sheet.”

---

## 3. Validation & “gap detection” logic

This is where your platform becomes smart, even before LLMs.

### a) Hard validation rules (Python)

For each initiative:

* Required fields: title, problem_statement, requesting_team, country, desired_outcome, etc.
* Value must be either specified or derivable.
* If fields are missing:

  * Mark `status = needs_info`.
  * Fill a `missing_fields` column with a comma-separated list.
  * Optionally write a comment in the cell or an extra “Notes from Product” column.

Your Python service updates the sheet cells via API so teams see feedback directly where they work.

### b) LLM-assisted enrichment

Examples where LLM fits nicely:

* **Summarizing long context** into a crisp 2–3 line “initiative summary”.
* **Classifying** into strategic themes, product areas, customer segments.
* **Estimating value**: if they give a fuzzy qualitative description (“this will reduce ops overhead”), LLM can suggest plausible impact ranges or metrics.
* **Cleaning fields**: standardizing country codes, naming conventions, etc.

You’d always log LLM outputs as **“suggested_…” fields**, and let product/owners confirm or adjust.

---

## 4. Engineering estimates & T-shirt sizes

You mentioned:

> estimate the developer time and efforts needed or notify the engineering team…

You can do that as:

1. **LLM-first suggestion** (e.g. “this smells like M-L sized feature”).
2. **Routing to engineering**:

   * When an initiative reaches `status = ready_for_estimate`, Python:

     * either writes it to a special “Eng Estimation” sheet
     * or sends a Slack/email with link & details.
   * Engineers add T-shirt size and/or **man-days** or story points.
3. Python updates initiative with `effort_tshirt_size` + optionally `effort_days`.

Later, in optimization, you convert T-shirt size → numeric estimate (e.g. S=5, M=13, L=21, XL=34).

---

## 5. Scoring and Portfolio optimization: how it would work

We want:

1. A unified output for optimization:
For each initiative → some canonical numeric fields like:

* value_score

* effort_score

* overall_score

* score_framework (which framework produced it)

* maybe score_version or score_run_id

2. Multiple input frameworks for scoring:

* RICE: Reach, Impact, Confidence, Effort

* MoSCoW: Must/Should/Could/Won’t (mapped to numeric)

* “Weighted Shortest Job First” frameworks

* Full mathematical model: Value = f(parameters | assumptions)

3. LLM as a scoring assistant, not the source of truth:

* Suggests:

** Framework inputs (e.g. Reach, Impact, Confidence…),

** For the math model: the formula and assumptions and parameter estimates,

** Optional suggested final score.

* Human can:

** Accept / tweak inputs & assumptions,

** Accept / override score.

4. A way to store the formula & assumptions per initiative so we can:

* Recalculate when assumptions change,

* Show the logic to stakeholders,

* Run Monte Carlo on the model.

* This affects mainly the services, LLM, and DB/models layers.

At this point, you have a set of **“approved in principle”** initiatives with:

* Estimated value (maybe as a range).
* Estimated effort (person-days or story points).
* Strategic tags, markets, teams, deadlines.

### a) Single-objective linear optimization

Classic setup:

* Binary decision variable `x_i ∈ {0,1}` per initiative.
* Objective: maximize `Σ (value_i * x_i)`
  (or a weighted sum of different types of value: revenue, risk reduction, strategic alignment).
* Constraints:

  * Capacity per team per quarter: `Σ (effort_i_team * x_i) ≤ capacity_team`.
  * Must-do items forced: `x_i = 1` for mandated items.
  * Market / theme quotas: e.g., at least 30% of capacity on Market A, no more than 40% on experiments, etc.

You can implement with:

* `pulp`, `ortools.linear_solver`, `pyomo`, etc.

### b) Multi-objective / non-linear

You have options:

* **Weighted sum**: combine multiple objectives into one (easiest to implement).
* **Scenario runs**: e.g. “revenue-heavy”, “risk-avoidance”, “CX-focused” scenarios by changing weights.
* For non-linear stuff (e.g. diminishing returns, risk functions) you can:

  * Either approximate as piecewise linear,
  * Or use heuristic/meta-heuristic algorithms (genetic algorithms, etc.) if you want.

### c) Monte Carlo for uncertainty

For uncertain inputs (value, effort):

* Model them as distributions: e.g. triangular( low, mode, high ).
* For each simulation run:

  * Sample value & effort → run the optimizer → see which initiatives are selected.
* You end up with:

  * Probability of each initiative appearing in the optimal portfolio.
  * Distribution of total value, total cost, etc.

You can then write a **“robustness score”** back into the sheet:

* E.g. `robustness = 0.87` meaning 87% of simulations selected this initiative.

---

## 6. Integrating triggers & workflows

You said:

> prioritization periodically or even at any point of time when triggered manually…

Easy patterns:

* Have a “Control” sheet with a cell `RUN_OPTIMIZATION = TRUE/FALSE`.
  When it flips to TRUE (manually), your Python job kicks off a run, then sets back to FALSE.
* Or use a simple web UI (tiny FastAPI endpoint) with a “Run Prioritization” button.
* Or just run scheduled jobs weekly, and product can trigger “manual, ad-hoc” runs via API.

Results:

* Python writes:

  * Priority rank,
  * Scenario ID,
  * Selected release / quarter,
  * Decision explanation (optional, using LLM to summarize trade-offs),
    back into the central roadmap sheet.

---

## 7. Limitations / realism of “Sheets as frontend”

**Pros:**

* Zero onboarding — everyone already knows spreadsheets.
* Departments can live in their own tabs and still feel “local”.
* Fast to iterate and politically easier than “a new product tool”.

**Cons / risks:**

* Concurrency / people breaking formulas.
* Data validation is weaker than a proper web app.
* Performance if rows explode into tens of thousands.
* Harder to control access & auditing.

**Mitigation:**

* Treat **Python + DB** as the true source of truth; Sheets are views + input forms.
* Lock structural parts of sheets (protected ranges).
* Move heavy calculations & logic into Python/DB, keep Sheets lightweight.

Given your goal (internal tool + you know Python), this is totally fine as a v1/v2 architecture.

---

## 8. Implementation phases (current status & roadmap)

### **✅ COMPLETED:**

**Phase 0 – Design the initiative schema & templates**
- ✅ Comprehensive `initiative_schema.md` with all fields, derivations, and constraints
- ✅ Department intake template standardized with header normalization
- ✅ Central backlog model defined in DB + Google Sheets

**Phase 1 – Pure consolidation (Flow 1: Intake Sync)**
- ✅ Google Sheets API integration with batch updates (1 API call for N cells)
- ✅ All intake sheets read and consolidated into DB via `sync_intake_job.py`
- ✅ Central Backlog sheet as single source of truth (read-only view with formulas)
- ✅ Bidirectional sync: Sheets ↔ DB with atomic updates

**Phase 2 – Validation & simple scoring (Flow 1 + Flow 2 Score Activation)**
- ✅ Required field validation with `missing_fields` tracking
- ✅ Multi-framework scoring engine (RICE, WSJF pluggable via `BaseFramework`)
- ✅ **Flow 2 Score Activation**: Copies per-framework scores to active fields based on `active_scoring_framework`
- ✅ Dynamic framework switching on Central Backlog works end-to-end
- ✅ Parameter management and per-framework field isolation

### **🔄 IN PROGRESS:**

**Phase 3 – Product Ops Multi-Framework Scoring & Parameterization (Flow 3)**

- **Phase 3.A (Plumbing)** ✅
  * Product Ops workbook integration complete
  * Config loading and header normalization working
  * Department/initiative/framework row parsing functional
  
- **Phase 3.B (Strong Sync)** ✅
  * Product Ops sheet ↔ DB sync with batch updates
  * Parameter reads/writes optimized
  * Atomic transactional updates implemented
  
- **Phase 3.C (Multi-framework)** ✅
  * RICE + WSJF per-framework computation in isolated fields
  * Automatic scoring write-back to Central Backlog
  * Framework-specific field preservation
  
- **Phase 3.D (Config Tab)** ⏸️ **EXISTS BUT UNUSED**
  * Config tab exists in ProductOps sheet but contains no data (reserved for future config-driven system behaviors)

### **✅ COMPLETED:**

**Phase 4.5 – Sheet-Native Execution & Control Plane** *(✅ COMPLETE - PRE-OPTIMIZATION PREREQUISITE)*

**Status: FEATURE-COMPLETE (V2). Date: 28 December 2025**

   * **Backend Execution & Control Plane**
     - Action API: `POST /actions/run`, `GET /actions/run/{run_id}` (HTTP layer)
     - ActionRun Ledger: DB-backed execution tracking with full audit trail (run_id, action, status, payload_json, result_json, error_text, started_at, finished_at, requested_by)
     - Worker Process: Continuously polls DB for queued ActionRun rows; executes single job per ActionRun; atomic result capture
     - Two-process architecture: FastAPI web process (enqueues) + async worker process (executes) communicating via DB
     - Action Registry: Flow actions (Flow 0-5 including optimization) + 8 PM Jobs (backlog_sync, score_selected, switch_framework, save_selected, suggest_math_model_llm, seed_math_params, optimize_run_selected_candidates, optimize_run_all_candidates)

   * **PM Jobs (V2 – All 8 Implemented End-to-End)**:
     
     **Core Jobs (V1)**:
     - `pm.backlog_sync` – Sync all intake sheets to Central Backlog (no selection). Runs Flow 1 full sync pipeline.
       - UI: Central Backlog sheet → Roadmap AI menu → "See Latest Intake"
       - Behavior: Intake sync → DB update → backlog regeneration → per-row Status writes
       - Summary: updated_count, cells_updated
     
     - `pm.score_selected` – Score selected initiatives across all frameworks (RICE, WSJF, Math Model). Selection-based; skips blank keys.
       - UI: ProductOps Scoring_Inputs sheet → Roadmap AI menu → "Score Selected"
       - Behavior: Sync inputs → compute_all_frameworks → write scores → per-row Status
       - Summary: selected_count, saved_count, failed_count, skipped_no_key
     
     - `pm.switch_framework` – Change active scoring framework (local-only, sheet-specific). No recompute; copies already-computed per-framework scores to active fields.
       - UI: ProductOps Scoring_Inputs sheet → Roadmap AI menu → "Switch Framework"
       - Behavior: Tab-aware (Scoring_Inputs or Central Backlog); activate scores → write active fields → per-row Status
       - Summary: selected_count, saved_count, failed_count, skipped_no_key
       - Key detail: No cross-sheet propagation; changes only current sheet
     
     - `pm.save_selected` – Persist tab edits to DB (tab-aware branching). Selection-based; skips blank keys.
       - UI: ProductOps sheets → Roadmap AI menu → "Save Selected" (detects tab context)
       - Tab-aware branches:
         - **Scoring_Inputs**: Syncs scoring inputs via Flow3
         - **MathModels**: Syncs math models via MathModelSyncService
         - **Params**: Syncs parameters via ParamsSyncService
         - **Central Backlog**: Updates initiatives via Flow1
       - Summary: selected_count, saved_count, failed_count, skipped_no_key
     
     **Math Model Jobs (V2 – NEW)**:
     - `pm.suggest_math_model_llm` – LLM suggests draft formula + notes for selected rows. Writes only to LLM columns (llm_suggested_formula_text, llm_notes, suggested_by_llm).
       - UI: ProductOps MathModels sheet → Roadmap AI menu → "Suggest Math Model"
       - Behavior: Calls LLM for rows with empty formula_text; guards on insufficient context (no problem_statement/impact_description/metric and no model_prompt_to_llm)
       - Summary: selected_count, suggested_count, skipped_existing_formula, skipped_insufficient_context, failed_count
       - Key detail: Never overwrites user columns (formula_text, assumptions_text, approved_by_user)
     
     - `pm.seed_math_params` – Validates approved formulas, extracts variable names, seeds Params rows with metadata (values empty). Sheet-first; DB persistence via pm.save_selected.
       - UI: ProductOps MathModels sheet → Roadmap AI menu → "Seed Math Params"
       - Behavior: For rows with formula_text and approved_by_user=TRUE, parse formula → extract identifiers → seed new Params rows
       - Summary: selected_count, seeded_count, skipped_not_approved, skipped_no_formula, failed_count
       - Usage flow: Approve formula → Seed Params → Fill values on Params tab → pm.save_selected (Params) → pm.score_selected
     
     **Optimization Jobs (V2 – NEW)**:
     - `pm.optimize_run_selected_candidates` – Run portfolio optimization on user-selected candidates (Step 1+2+3: capacity + governance + targets).
       - UI: Optimization Center Candidates tab → Roadmap AI menu → "Optimize Selected"
       - Behavior: Selection scope → feasibility check → OR-Tools CP-SAT solver → write Results tab
       - Summary: selected_count, solved_count, feasibility_errors, selected_initiatives, total_objective
     
     - `pm.optimize_run_all_candidates` – Run portfolio optimization on ALL candidates in scenario (Step 1 capacity-only: no governance, no targets).
       - UI: Optimization Center Scenario_Config tab → Roadmap AI menu → "Optimize All"
       - Behavior: Scenario scope → fast capacity-constrained solver → write Results tab
       - Summary: candidate_count, solved_count, selected_initiatives, total_objective

   * **Apps Script UI Layer** (Bound scripts in ProductOps & Central Backlog sheets)
     - Custom menu "Roadmap AI" with items for all 6 jobs
     - Selection extraction: Reads initiative_keys from active selected rows; skips blanks
     - HTTP integration: config.gs (API URL + secret), api.gs (POST /actions/run, GET /actions/run/{run_id} helpers)
     - Authentication: Shared-secret header X-ROADMAP-AI-SECRET from Script Properties
     - Error handling: Try/catch blocks surface API errors via in-sheet toast notifications
     - Optional polling: Apps Script can poll status until completion for UX feedback
     - Tab-aware branching: pm.save_selected intelligently routes based on active sheet name

   * **Consistent Architecture Across All Jobs**:
     - Server-side orchestration: Single ActionRun per job (no nested enqueues)
     - Selection scoping: initiative_keys list passed in scope payload; blank keys filtered
     - Per-row Status writes: Generic write_status_to_sheet abstraction (supports any tab)
     - Accurate summary fields: selected_count, saved_count/suggested_count/seeded_count, failed_count, skipped_no_key (early bail: selected_count: 0)
     - Provenance: ActionRun uses PM job token (e.g., pm.score_selected); sheet Updated Source reflects actual writer (Flow 3 token, etc.)

   * **Provenance & Audit Trail Architecture** (Dual-Column):
     1. **updated_source (Provenance Token)**
        - Canonical "why" column: Flow token or PM job token
        - Examples: flow3.compute_all_frameworks, pm.score_selected, flow1.backlog_sheet_write
     
     2. **updated_at (UTC Timestamp)**
        - ISO-formatted timestamp of when row was modified
        - Set to datetime.now(timezone.utc).isoformat() on every update
        - Enables chronological auditing and change tracking
     
     - **Coverage**: All sheet writers stamp both columns
       - Params: append, update, backfill
       - MathModels: single & batch suggestions
       - ProductOps: scores, status updates
       - Backlog: full regeneration
       - Intake: key assignment
     
   * **Type Safety & Serialization**:
     - Fixed "Object of type datetime is not JSON serializable" crashes
     - Added `_to_sheet_value()` helper: converts datetime → ISO, Decimal → float, dict/list → JSON string
     - ProductOps writer skips updated_at when copying DB fields (only set via UTC timestamp, not from DB)
     - Prevents batch_update_values failures from non-JSON-serializable types
   
   * **Header Alias Coverage**:
     - PARAMS_HEADER_MAP, MATHMODELS_HEADER_MAP, INTAKE_HEADER_MAP support "updated at" alias
     - Aliases: [updated_at, Updated At, updated at]
     - Resolves header mismatches across sheet column name variants
   
   * **Key Files Changed**:
     - app/api/actions.py – Action API endpoints
     - app/api/schemas/actions.py – ActionRun + request/response schemas
     - app/services/action_runner.py – PM job orchestration logic + all 6 job implementations
     - app/workers/action_worker.py – Worker process polling + execution
     - app/db/models/action.py – ActionRun ORM
     - app/sheets/{params,mathmodels,productops,backlog,intake}_writer.py – Updated with UTC timestamp + type normalization
     - app/sheets/models.py – Header alias updates
     - Apps Script (ProductOps & Central Backlog sheets) – UI menus + HTTP calls
   
   * **Documentation**:
     - [PHASE_4.5_CHECKPOINT.md](docs/phase_4.5_sheetnative_execution/PHASE_4.5_CHECKPOINT.md) – Complete checkpoint with end-to-end flows and validation
     - [phase_4.5_pm_jobs.md](docs/phase_4.5_sheetnative_execution/phase_4.5_pm_jobs.md) – Detailed PM job specification (V1 + V2 math model jobs)
     - [phase_4.5_pm_cheatsheet.md](docs/phase_4.5_sheetnative_execution/phase_4.5_pm_cheatsheet.md) – Quick reference guide for all 6 jobs + status codes + best practices
     - [phase_4.5_worker_api_processes.md](docs/phase_4.5_sheetnative_execution/phase_4.5_worker_api_processes.md) – Two-process architecture explanation + polling semantics

### **📋 PLANNED (Future):**

**Phase 4.5.1 – Polish & Hardening** (FUTURE/NOT IMPLEMENTED)
   * **Control/RunLog Tab** – FUTURE FEATURE: Live dashboard of execution history in ProductOps sheet (ActionRun audit trail) - NOT YET IMPLEMENTED
   * **Flow Actions** – Optional: Implement flow-level actions if direct Flow 0-4 triggering needed (currently using PM job wrappers)
   * **Status**: Not blocking; Phase 4.5 is production-ready without these features

**Phase 4 – MathModel Framework & LLM-Assisted Scoring** *(NOT A NUMBERED FLOW - Integrated into Phase 4.5 PM Jobs)*
   * **Status: COMPLETE** – Math models fully integrated into Phase 4.5 sheet-native execution (pm.suggest_math_model_llm, pm.seed_math_params)
   * **Completed Components**:
     - MathModels sheet reader, writer, DB model (InitiativeMathModel)
     - MathModelFramework scoring engine (safe formula evaluation)
     - Parameter seeding from formulas (formula parser)
     - LLM prompts for formula suggestion + parameter metadata
     - Two-step workflow: Suggest (LLM) → Approve → Seed → Fill → Score
   * **Remaining (Polish, not blocking)**:
     - Fine-tune LLM prompts for formula quality
     - Enhance formula parser robustness
     - Add formula validation before seeding
   * **Notes**:
     - pm.suggest_math_model_llm and pm.seed_math_params are live in Phase 4.5 (V2)
     - Enables full custom-formula workflows alongside RICE/WSJF
     - Ready for production use via sheet UI

**Phase 5 – Portfolio Optimization & Roadmap Generation** *(IN PROGRESS - JAN 2026)*
   * **Status: SOLVER STEPS 1-8.2 COMPLETE** – OR-Tools CP-SAT adapter implementing capacity-constrained optimization with governance and production-grade objective modes.
   * **Completed Components (Jan 2026)**:
     - **Phase 5.0 (Cleanup)**: DB cleanup migrations, schema alignment
     - **Phase 5.2 (Optimization Center Pipeline)**: Complete ✅
     - **Phase 5.3 (Solver Implementation)**: Steps 1-8.2 Complete ✅
       * Step 1-2: Binary selection variables + capacity caps (engineering tokens per dimension slice)
       * Step 3: Exclusions (single initiative bans + pairwise mutual exclusions)
       * Step 4: Prerequisites (x_dep ≤ x_req dependency constraints with Dict[str, List[str]] structure)
       * Step 5: Bundles (all-or-nothing groupings)
       * Step 6: Capacity floors (minimum token allocations per dimension slice)
       * Step 7: Target floors (minimum KPI contribution requirements per dimension/KPI)
       * Step 8.1: North star objective mode ✅ (Jan 25, 2026)
         - Builder resolves active north_star KPI from OrganizationMetricsConfig (kpi_level="north_star", is_active=true)
         - Requires exactly one active north_star KPI (validation with actionable errors)
         - Maximizes Σ(contrib_i[ns_key] * x_i) scaled by KPI_SCALE=1,000,000
         - Comprehensive diagnostics: objective_mode, north_star_kpi_key, contributing_candidates, missing_contrib
       * Step 8.2: Weighted KPIs objective mode ✅ (Jan 25, 2026)
         - Builder validation: weighted KPI keys must exist, be active, and be north_star/strategic level only
         - Enhanced normalization: prefers targets["all"]["all"][kpi]["value"], else max aggregation across all dimensional targets, else fallback to 1.0
         - Maximizes Σ_i (Σ_k w_k * contrib_i,k / scale_k) * x_i scaled by KPI_SCALE
         - Comprehensive diagnostics: weights_sum, kpi_scale_map, scale_source_map, scale_targets_count, missing_target_scales, nonzero_coeff_candidates
       * Step 8.3: Lexicographic objective mode (TODO)
       * Feasibility checker: Pre-solver validation (cycle detection, reference validation, capacity checks)
       - OptimizationScenario, OptimizationConstraintSet, OptimizationRun DB models
       - ConstraintSetCompiled Pydantic schema with discriminated union constraint types (9 types)
       - Prerequisites refactored to dict structure: `Dict[str, List[str]]` (migration r20260109_prereq_dict)
       - Optimization Center sheet readers/writers (Scenario_Config, Constraints, Targets tabs)
       - Constraint compilation service (validates, normalizes, buckets, deduplicates)
       - Multi-dimensional targets support (country, product, cross-sectional, global)
       - Composite key scoping in writers (prevents row collision)
       - Documentation complete: shapes, PM guidance, glossary, status docs
   * **Remaining (Phase 5.3+ - Optimization Engine)**:
     - Step 8.3: Lexicographic objective mode (multi-stage solving with strict KPI prioritization)
     - Results publishing to Optimization Center Results tab
     - Roadmap sheet generation with selected initiatives
     - Sheet-native execution integration (pm.run_optimization action)
     - Production testing and validation across all objective modes
   * **Key Design Decisions**:
     - Prerequisites as dict provides O(1) lookup, semantic clarity, self-documenting structure
     - Targets use nested 3-level structure `{dimension: {dimension_key: {kpi_key: {}}}}` for consistency
     - Constraints apply to ALL optimization modes (not just lexicographic)
     - "all"."all" nesting maintains structural consistency (no special cases needed)
     - weighted_kpis normalization: 3-tier fallback (global all/all → max across dimensions → 1.0) with full diagnostics
     - Builder-side validation: All KPI resolution and constraint validation before solver invocation
     - Production-grade diagnostics: All objective modes persist comprehensive metadata to result_json

**Phase 6 – LLM Enrichment for General Operations**
   * Initiative summaries and classification
   * Strategic theme tagging
   * General context enrichment (non-MathModel)
   * Automated hypothesis generation

**Phase 7 – Advanced Simulation & Uncertainty Modeling**
   * Monte Carlo uncertainty modeling
   * Robustness scoring and risk indicators
   * Sensitivity analysis for key parameters
   * Portfolio risk assessment

**Phase 8 – UX & Governance Refinements**
   * Notifications, dashboards, scenario comparison views
   * Access control & workflows
   * Audit trails and decision history

---

## 9. Operational Notes (Current Implementation)

### **Architecture Overview**

The system is a **3-flow architecture** with **sheet-native execution** (Phase 4.5):

- **Flow 1**: Intake consolidation (departments → DB → Central Backlog)
- **Flow 2**: Score activation (per-framework scores → active fields)
- **Flow 3**: Product Ops multi-framework scoring (parameters → per-framework scores)
- **Phase 4.5**: All flows triggerable from Google Sheets via custom menu + Action API

### **Provenance & Audit Trail Architecture**

Every sheet writer now maintains a **dual-column provenance system**:

1. **`updated_source` (Provenance Token)**
   - Canonical source of why a row was changed
   - Examples: `flow3.compute_all_frameworks`, `flow4.sync_params`, `flow1.backlog_sheet_write`
   - Set by writers alongside data updates
   
2. **`updated_at` (UTC Timestamp)**
   - ISO-formatted timestamp of when the row was updated
   - Set to current UTC time (`datetime.now(timezone.utc).isoformat()`)
   - Enables chronological auditing and change tracking

**Coverage**:
   - **Params Writer**: Appends, updates, backfill all stamp both columns
   - **MathModels Writer**: Single/batch suggestions stamp both columns
   - **ProductOps Writer**: Score and status writes stamp both columns
   - **Backlog Writer**: Full regeneration stamps current UTC time
   - **Intake Writer**: Key assignment stamps both columns

**Type Safety**: All writers use `_to_sheet_value()` to convert:
   - `datetime` / `date` → ISO string
   - `Decimal` → float
   - `dict` / `list` → JSON string
   - Prevents "Object of type X is not JSON serializable" errors during Sheets API batch updates

### **Three-Flow Architecture**

The current system operates with three independent, coordinated data flows:

1. **Flow 1 – Intake Consolidation (Source of Truth)**
   - **What**: Department intake sheets → DB → Central Backlog sheet
   - **When**: Triggered manually or on schedule via `sync_intake_job.py` or `pm.backlog_sync` action
   - **Responsibility**: Consolidates all initiative requests into canonical DB model
   - **Key Operations**:
     - `backlog_update_cli --sync`: Pull Central Backlog sheet changes into DB
     - `sync_intake_job.py`: Pull all department intake sheets into DB
     - `backlog_sync_cli --log-level INFO`: Push DB state back to Central Backlog sheet

2. **Flow 2 – Score Activation (Required Bridge)**
   - **What**: Per-framework scores → Active scores (based on `active_scoring_framework`)
   - **When**: After any scoring change; REQUIRED before pushing to sheets
   - **Responsibility**: Makes per-framework isolation work; enables dynamic framework switching
   - **Key Operation**:
     - `flow2_scoring_cli --all`: Activates per-framework scores to active fields
   - **Example**: If `active_scoring_framework = RICE`, copies `rice_value_score` → `value_score`, `rice_overall_score` → `overall_score`

3. **Flow 3 – Product Ops Multi-Framework Scoring (Optional)**
   - **What**: Product Ops sheet → Per-framework scoring → Write back
   - **When**: On schedule or manual trigger via `pm.score_selected` action
   - **Responsibility**: Computes RICE + WSJF scores from Product Ops parameters
   - **Key Operations**:
     - `flow3_cli --sync`: Read Product Ops sheet into DB
     - `flow3_cli --compute-all`: Compute all RICE + WSJF scores
     - `flow3_cli --write-scores`: Write per-framework scores back to Central Backlog
   - **Important**: Flow 3 does NOT activate scores to active fields; Flow 2 must run afterward

### **Framework Switching Workflow**

To change the active scoring framework (e.g., WSJF → RICE):

1. **Edit Central Backlog** – Change `active_scoring_framework` cell
2. **Run Flow 1** – `pm.backlog_sync` or `backlog_update_cli --sync` (pulls framework change into DB)
3. **Run Flow 2** – `flow2_scoring_cli --all` (activates RICE scores to active fields)
4. **Sync Back** – `pm.backlog_sync` or `backlog_sync_cli --log-level INFO` (pushes updated active scores to sheet)

Result: Central Backlog now shows RICE scores in `value_score` / `overall_score` columns.

### **Key Architectural Concepts**

- **Per-Framework Fields**: Each initiative has isolated scoring fields (e.g., `rice_value_score`, `wsjf_value_score`) that preserve framework-specific computation
- **Active Fields**: `value_score` and `overall_score` are "view" fields that get populated by Flow 2 based on `active_scoring_framework`
- **Batch Updates**: All sheet writes use Google Sheets API `values().batchUpdate()` (1 API call for N cells) for efficiency
- **Header Normalization**: Sheet columns support underscore variants (e.g., `active_scoring_framework` or `ACTIVE_SCORING_FRAMEWORK`)
- **Atomicity**: DB transactions ensure data consistency; sheet updates batched to avoid partial writes
- **Type Normalization**: All DB values normalized to Sheets-safe types before batch updates to prevent serialization errors

### **Data Propagation Example**

Product Ops enters RICE parameters → Flow 3 `--sync` → DB updated → Flow 3 `--compute-all` → RICE per-framework scores computed → Flow 3 `--write-scores` → Scores written to Central Backlog sheet (with `updated_source` and `updated_at`) → Flow 2 activation skipped (scores already for current framework) → Flow 1 backlog_sync reads updated Central Backlog back into DB for next iteration.

---

## 10. Glossary

**Active Scoring Framework**
- The currently selected scoring framework (RICE, WSJF, etc.) whose per-framework scores are copied to active fields via Flow 2.

**Batch Update**
- Single Google Sheets API call that updates N cells atomically. Optimizes API quota usage and ensures consistency.

**Flow 1 – Intake Consolidation**
- Syncs all department intake sheets into central DB and Central Backlog sheet. Source of truth for all initiatives.

**Flow 2 – Score Activation**
- Copies per-framework scores to active fields based on `active_scoring_framework`. Required bridge for framework switching and active display.

**Flow 3 – Product Ops Multi-Framework Scoring**
- Reads Product Ops parameters, computes RICE + WSJF scores per initiative, writes isolated per-framework scores to Central Backlog.

**Header Normalization**
- Sheets support multiple column name variants (e.g., `active_scoring_framework` or `ACTIVE_SCORING_FRAMEWORK`) without breaking parsing.

**Per-Framework Fields**
- Isolated scoring columns for each framework (e.g., `rice_value_score`, `rice_overall_score`, `wsjf_value_score`, `wsjf_overall_score`). Preserve framework-specific logic.

**Score Activation**
- Process of copying per-framework scores to active fields. Enables framework switching and prevents score pollution from unused frameworks.

**Prerequisites (Optimization)**
- Dependency constraints in portfolio optimization stored as `Dict[str, List[str]]` mapping dependent initiative_key → list of required prerequisite initiative_keys. If dependent is selected, ALL prerequisites must be selected. Dict structure (implemented Jan 2026, migration r20260109_prereq_dict) provides O(1) lookup, semantic clarity, and self-documenting code vs deprecated list-of-lists format.

---

## Original Project Structure Notes:

Python is perfect for:

* Data cleaning & consolidation (pandas),

* Optimization (ortools, pulp, pyomo),

* Simulation (NumPy / SciPy),

* LLM orchestration (OpenAI API, LangChain/LangGraph if you want structure later).

* Sheets are a pragmatic “UI” for an org that doesn’t want another tool yet.

---

## 9. Project Structure:

**NOTE**: For the complete, up-to-date project structure, see the **Codebase Registry** section below (auto-generated from `app/` directory via AST parsing).

The codebase follows a clean architecture with clear separation:
- **`app/db/`** - SQLAlchemy models and database session management
- **`app/schemas/`** - Pydantic schemas for validation and serialization
- **`app/sheets/`** - Google Sheets API integration (readers, writers, client)
- **`app/services/`** - Core business logic (intake, scoring, optimization, sync services)
- **`app/jobs/`** - Batch job orchestration (Flow 1-5 jobs)
- **`app/llm/`** - LLM integration for math model suggestions
- **`app/api/`** - FastAPI REST endpoints for Action API
- **`app/workers/`** - Background worker processes (ActionRun execution)
- **`app/utils/`** - Shared utilities (safe_eval, header normalization, provenance)

---


Let's review 4 main scenarios:

1. **Intake → Central Backlog Sync**
2. **Known Framework Scoring (e.g. RICE)**
3. **Math Model + LLM Flow**
4. **Optimization → Roadmap Generation**

---

## 1. Department Intake → Central Backlog & DB

**Scenario:** A Sales PM adds/edits a row in their local intake sheet. You run a sync job. That row becomes/updates an `Initiative` in the DB and shows up in the central backlog sheet.

### Entry point

* **Module:** `app/jobs/sync_intake_job.py`
* **Function:** `run_sync_for_sheet(sheet_id: str, tab_name: str)`

**1.1. Job pulls rows from Google Sheets**

* **Module:** `app/sheets/intake_reader.py`
* **Function:** `get_rows_for_sheet(sheet_id: str, tab_name: str) -> list[tuple[int, dict]]`

  * Uses `app/sheets/client.py.get_values(range=...)` under the hood.
  * Returns e.g. `[(5, {"Title": "Improve Checkout", "Requesting Team": "Sales", ...}), ...]`.

**1.2. For each row, call IntakeService**

* **Module:** `app/services/intake_service.py`
* **Function:** `IntakeService.sync_row(row: dict, sheet_id: str, tab_name: str, row_number: int) -> Initiative`

  Internally:

  1. **Map row → Pydantic**

     * **Module:** `app/services/intake_mapper.py`
     * **Function:** `map_sheet_row_to_initiative_create(row: dict) -> InitiativeCreate`

  2. **Find existing initiative (by source metadata)**

     ```python
     existing = (
         db.query(Initiative)
           .filter(
               Initiative.source_sheet_id == sheet_id,
               Initiative.source_tab_name == tab_name,
               Initiative.source_row_number == row_number,
           )
           .first()
     )
     ```

  3. **If not found → create new**

     * **Module:** `app/services/initiative_key.py`

     * **Function:** `generate_initiative_key(db: Session) -> str`

     * Create instance:

       ```python
       initiative = Initiative(
           initiative_key=initiative_key,
           source_sheet_id=sheet_id,
           source_tab_name=tab_name,
           source_row_number=row_number,
           **data.model_dump(),
       )
       db.add(initiative)
       ```

  4. **If found → update fields**

     * **Private method:** `_update_existing_initiative(initiative, data: InitiativeCreate)`

  5. `commit` + `refresh` and return the `Initiative`.

**1.3. Update central backlog sheet**

Once all rows are synced:

* **Module:** `app/sheets/backlog_writer.py`
* **Function:** `write_backlog_from_db(db: Session)`

  * `db.query(Initiative).all()`
  * Convert each `Initiative` to a row dict (using `InitiativeRead.model_validate(initiative)`).
  * Use `client.update_values(backlog_sheet_id, range, rows)` to push:

    * `initiative_key`, `title`, `requesting_team`, `status`, `value_score`, `overall_score`, etc.

Now central backlog is **the consolidated view** of all initiatives, backed by DB.

---

## 2. Known Framework Scoring (e.g. RICE) with Params

**Scenario:** PM sets `active_scoring_framework = "RICE"` for an initiative. Backend seeds RICE params in `Params` sheet. PM fills them. A scoring job computes `value_score / effort_score / overall_score` and writes them back.

### Entry point: PM sets framework

* **Where:** Central backlog sheet: column `active_scoring_framework` = `"RICE"` for `INIT-000123`.
* **Triggered by:** a scheduled job or webhook (for now, cron).

### 2.1. Param seeding job

* **Module:** `app/jobs/param_seeding_job.py`

* **Function:** `run_param_seeding_job()`

  1. Fetch initiatives that have `active_scoring_framework` set but **no params seeded yet**.

     ```python
     initiatives = (
         db.query(Initiative)
           .filter(Initiative.active_scoring_framework != None)
           .all()
     )
     ```

  2. For each initiative, call param seeding service.

* **Module:** `app/services/param_seeding_service.py`

* **Function:** `seed_params_for_initiative(initiative: Initiative)`

  * If `initiative.active_scoring_framework == "RICE"`:

    * Known param names: `["reach", "impact", "confidence", "effort"]`.

    * For each param name:

      * Create a `Params` row in the **Params Sheet** via:

        * **Module:** `app/sheets/params_writer.py`
        * **Function:** `ensure_param_row(initiative_key, framework, param_name, defaults: dict)`

        `defaults` may come from:

        * Hard-coded template in `rice_framework.py`, or
        * **Module:** `app/llm/scoring_assistant.py.suggest_param_metadata(...)`.

    * Also create corresponding records in DB if you want (`InitiativeScore` or a `Param` model, but at minimum we store in sheet and `parameters_json` later).

### 2.2. PM fills/approves params in Params sheet

PM/analytics:

* Filter `Params` sheet by `initiative_key = "INIT-000123"` and `framework = "RICE"`.
* Fill `value` for `reach`, `impact`, `confidence`, `effort`.
* Set `approved = TRUE` when done.

### 2.3. Scoring job reads params and computes scores

* **Module:** `app/jobs/scoring_job.py`

* **Function:** `run_scoring_job()`

  1. Fetch initiatives whose scoring needs update:

     ```python
     initiatives = (
         db.query(Initiative)
           .filter(Initiative.active_scoring_framework != None)
           .all()
     )
     ```

  2. For each initiative:

     * Rehydrate its params:

       * **Module:** `app/sheets/params_reader.py`
       * **Function:** `get_params_for_initiative(initiative_key: str, framework: str) -> list[ParamRow]`

       `ParamRow` could be a small Pydantic model with `param_name`, `value`, `approved` etc.

     * Optionally map param rows into a dict:

       ```python
       params = {row.param_name: row.value for row in rows if row.approved}
       ```

  3. Call ScoringService.

* **Module:** `app/services/scoring_service.py`

* **Function:** `ScoringService.score_initiative(initiative: Initiative) -> Initiative`

  Internals:

  * **Module:** `app/services/scoring/factory.py`

    * `framework = framework_factory.get(initiative.active_scoring_framework or "RICE")`

  * The framework (e.g. `RiceFramework`) pulls params either from:

    * The `params` dict you pass in, or
    * Directly via relationships (if you mirror params in DB).

  * **Module:** `app/services/scoring/rice_framework.py`

    * **Function:** `RiceFramework.score(initiative: Initiative) -> ScoreResult`

      * Uses `reach`, `impact`, `confidence`, `effort` to compute:

        ```python
        value_score = reach * impact * confidence
        effort_score = effort
        overall = value_score / effort_score
        ```

  * `ScoringService` updates:

    ```python
    initiative.value_score = result.value_score
    initiative.effort_score = result.effort_score
    initiative.overall_score = result.overall_score
    db.add(initiative)
    db.add(InitiativeScore(...history...))
    db.commit()
    ```

### 2.4. Write scores back to central backlog

Still in `scoring_job` after scoring:

* **Module:** `app/sheets/backlog_writer.py`
* **Function:** `update_backlog_scores(db: Session)`

  * Query initiatives with updated scores.
  * Map them to sheet rows.
  * Use `client.update_values` to fill `value_score`, `effort_score`, `overall_score` columns for their `initiative_key`.

---

## 3. Math Model + LLM Flow (Formula + Params + Scoring)

**Scenario:** PM creates multiple mathematical models per initiative to quantify impact on different KPIs.

### 3.1. Define Metric Chains & KPI Targets

* **Metric Chain Documentation**: PM identifies the impact pathway for each initiative
  * Example: "signups → activation → purchases → revenue"
  * Documents in `metric_chain_text` column per math model
  * System parses into `metric_chain_json` for validation & LLM context

* **Multiple Models per Initiative**: Each initiative can have N models targeting different KPIs
  * Model 1: targets `north_star` KPI (e.g., "revenue")
  * Model 2: targets strategic KPI (e.g., "user_retention")
  * Model 3: targets strategic KPI (e.g., "engagement_score")

* **Primary Model**: One model marked `is_primary = TRUE` serves as representative score for displays

### 3.2. PM describes models in MathModels sheet

* PM opens **MathModels** sheet:

  * Adds/edits rows (multiple per initiative):

    * `initiative_key = "INIT-000456"`
    * `model_name = "Revenue Impact Model"` (descriptive name)
    * `target_kpi_key = "revenue"` (which KPI this model affects)
    * `metric_chain_text = "signups → activation → purchases → revenue"`
    * `is_primary = TRUE` (if this is the representative model)
    * `framework = "MATH_MODEL"`
    * `model_description_free_text` (or leaves blank for LLM suggestion).

### 3.3. Backend LLM job suggests formula & assumptions

* **Module:** `app/jobs/math_model_generation_job.py`
* **Function:** `run_math_model_generation_job()`

  1. **Read MathModels needing suggestions**

     * **Module:** `app/sheets/math_models_reader.py`
     * **Function:** `get_pending_math_models() -> list[MathModelRow]`

       * Filter `formula_text_approved == FALSE` and `llm_suggested_formula_text` is empty or outdated.

  2. **Fetch context**

     * For each `MathModelRow`, load `Initiative`:

       ```python
       initiative = db.query(Initiative).filter_by(initiative_key=row.initiative_key).one()
       ```

  3. **Call LLM scoring assistant**

     * **Module:** `app/llm/scoring_assistant.py`
     * **Function:** `suggest_math_model(initiative: Initiative, description: str | None) -> MathModelSuggestion`

       Where `MathModelSuggestion` has:

       ```python
       formula_text: str
       assumptions_text: str
       param_suggestions: list[ParamSuggestion]
       llm_notes: str
       ```

  4. **Write suggestions back to MathModels**

     * **Module:** `app/sheets/math_models_writer.py`
     * **Function:** `write_math_model_suggestion(row_id, suggestion: MathModelSuggestion)`

       * Fills:

         * `llm_suggested_formula_text`
         * `assumptions_text`
         * `llm_notes`

### 3.4. PM approves formula

* PM reviews `llm_suggested_formula_text` in MathModels sheet.
* Either:

  * Copies it into `formula_text_final`, or
  * Edits `formula_text_final` manually.
* Sets `formula_text_approved = TRUE`.

### 3.5. Backend parses formula & seeds Params rows

* **Module:** `app/jobs/param_seeding_job.py`
* **Function:** `run_param_seeding_job()` (same job as before, but now with math model branch)

  * For initiatives where:

    * `use_math_model = TRUE`
    * `active_scoring_framework = "MATH_MODEL"`
    * `formula_text_approved = TRUE`
    * And **no params yet seeded for (initiative, "MATH_MODEL")**

  * Call:

    * **Module:** `app/services/param_seeding_service.py`
    * **Function:** `seed_params_from_math_model(initiative: Initiative, formula_text: str, param_suggestions: list[ParamSuggestion])`

      Inside:

      1. Parse formula to extract variable names:

         * **Module:** `app/utils/formula_parser.py`

           * `parse_parameters(formula_text: str) -> list[str]`
             e.g. from `"value = traffic * conversion_uplift * margin - infra_cost"` → `[ "traffic", "conversion_uplift", "margin", "infra_cost" ]`

      2. Combine with `param_suggestions` from LLM to attach units, labels, ranges.

      3. For each param, create or update row in `Params`:

         * **Module:** `app/sheets/params_writer.py`
         * **Function:** `ensure_param_row(initiative_key, framework="MATH_MODEL", param_name, metadata)`

### 3.6. PM fills/approves param values

* PM / Analytics / Finance open **Params** sheet, filtered by:

  * `initiative_key = "INIT-000456", framework = "MATH_MODEL"`

* They:

  * Fill `value`.
  * Adjust `unit`, `min`, `max`, `source`.
  * Set `approved = TRUE`.

### 3.7. Scoring job computes math-model-based scores

Same `run_scoring_job()` as in flow 2, but:

* `active_scoring_framework = "MATH_MODEL"`.

* `ScoringService` calls:

  * **Module:** `app/services/scoring/math_model_framework.py`
  * **Function:** `MathModelFramework.score(initiative: Initiative) -> ScoreResult`

    Inside:

    1. Access `initiative.math_models` (1:N relationship - multiple models per initiative).

    2. **For each math model:**

       ```python
       for model in initiative.math_models:
           params = get_params_for_initiative(
               initiative.initiative_key, 
               framework="MATH_MODEL",
               model_id=model.id
           )
           
           # Evaluate formula
           score = evaluate_formula(model.formula_text, params)
           
           # Store computed score on model
           model.computed_score = score
       ```

    3. **Select representative score** (for Initiative.overall_score):
       - Primary model (`is_primary=True`) OR
       - North star KPI model OR
       - Highest score

    4. **Compute KPI contributions** from all model scores:

       ```python
       from app.services.product_ops.kpi_contribution_adapter import update_initiative_contributions
       
       # Aggregates all models' target_kpi_key + computed_score into unified JSON
       update_initiative_contributions(db, initiative, commit=True)
       # Updates: initiative.kpi_contribution_computed_json (always)
       #          initiative.kpi_contribution_json (if not pm_override)
       ```

* `ScoringService` then updates `initiative.value_score`, `initiative.overall_score`, persists `InitiativeScore`, and `backlog_writer` pushes numbers back to central sheet.

### 3.9. KPI Contributions Flow (System-Derived + PM Override)

**Architecture**: KPI contributions are **derived from math model scores**, not manually entered upfront.

1. **System Computes Contributions** (after scoring):
   - Each math model has `target_kpi_key` (e.g., "revenue", "user_retention")
   - Each model has `computed_score` (e.g., 85.5)
   - Adapter aggregates: `{"revenue": 85.5, "user_retention": 72.3}`
   - Writes to `Initiative.kpi_contribution_computed_json` (always updated)
   - Writes to `Initiative.kpi_contribution_json` (active, unless overridden)

2. **PM Can Override** (via KPI_Contributions tab):
   - PM edits `kpi_contribution_json` in sheet
   - Save action sets `kpi_contribution_source = "pm_override"`
   - System preserves PM edits, continues updating `kpi_contribution_computed_json` for reference

3. **Validation** (against Metrics_Config):
   - Only KPIs defined in `OrganizationMetricConfig` with `is_active=true` are allowed
   - Only `north_star` and `strategic` KPI levels are eligible
   - Invalid keys rejected during sync

4. **Representative Score Selection**:
   - If multiple models target same KPI → primary model wins
   - Else highest score used
   - Primary model (`is_primary=true`) determines Initiative.overall_score for displays

---

## 4. Optimization → Roadmap Generation → Roadmap Sheet

**Scenario:** You run an optimization job to pick the best set of initiatives for Q1, respecting capacity & dependencies, then write a roadmap sheet.

### 4.1. Optimization job

* **Module:** `app/jobs/optimization_job.py` (you’ll create this)
* **Function:** `run_optimization_for_period(period: str)`

  1. Fetch candidates from DB:

     ```python
     initiatives = (
         db.query(Initiative)
           .filter(Initiative.status == "approved_in_principle")
           .all()
     )
     ```

  2. Build an optimization input structure:

     * **Module:** `app/services/optimization_service.py`
     * **Function:** `build_portfolio_model(initiatives: list[Initiative], constraints: OptimizationConstraints) -> OptimizationModel`

  3. Solve:

     * **Module:** `app/services/optimization_service.py`
     * **Function:** `solve_portfolio(model: OptimizationModel) -> OptimizationResult`

       * Uses OR-Tools / PuLP / Pyomo under the hood.

  4. Get selected initiatives and their assigned periods (e.g. Q1, Q2).

### 4.2. Create/update Roadmap & RoadmapEntries

* **Module:** `app/services/roadmap_service.py`
* **Function:** `create_roadmap_from_result(name: str, result: OptimizationResult) -> Roadmap`

  Steps:

  1. Create `Roadmap`:

     ```python
     roadmap = Roadmap(name=name, timeframe_label=period, owner_team="Product")
     db.add(roadmap); db.flush()
     ```

  2. For each selected initiative:

     ```python
     for item in result.selected_items:
         entry = RoadmapEntry(
             roadmap_id=roadmap.id,
             initiative_id=item.initiative_id,
             priority_rank=item.rank,
             planned_quarter=item.planned_quarter,
             planned_year=item.planned_year,
             is_selected=True,
             value_score_used=item.value_score,
             effort_score_used=item.effort_score,
             overall_score_used=item.overall_score,
             optimization_run_id=result.run_id,
             scenario_label=result.scenario_name,
         )
         db.add(entry)
     ```

  3. `db.commit()` and return `roadmap`.

### 4.3. Write Roadmap to Sheets

* **Module:** `app/sheets/backlog_writer.py` or a dedicated `app/sheets/roadmap_writer.py`
* **Function:** `write_roadmap_sheet(roadmap: Roadmap, db: Session)`

  1. Load entries:

     ```python
     entries = (
         db.query(RoadmapEntry)
           .filter(RoadmapEntry.roadmap_id == roadmap.id)
           .join(RoadmapEntry.initiative)
           .all()
     )
     ```

  2. Build rows like:

     | Priority | Initiative Key | Title | Product Area | Value Score | Effort | Overall | Quarter | Notes |
     | -------- | -------------- | ----- | ------------ | ----------- | ------ | ------- | ------- | ----- |

  3. Use `client.update_values(roadmap_sheet_id, range, rows)` to create/update a dedicated “Roadmap - Q1 2026” sheet.

Now PMs and stakeholders see the **optimized roadmap** as a familiar spreadsheet.

---


# **Glossary**

**Core entity definitions**

1. Initiative  
Canonical object representing a proposed product change. Aggregates identity (initiative_key, source_*), requester info, problem/context, strategic classification, impact (low/expected/high), effort (t‑shirt, days), risk/dependencies, workflow status, scoring summary (value_score, effort_score, overall_score), **multiple math models** (use_math_model, math_models relationship 1:N), **KPI contributions** (kpi_contribution_json computed from model scores, PM-editable via KPI_Contributions tab).

2. Intake sheet (department / local idea sheet)  
Source spreadsheet where a department enters raw initiative rows. Editable fields: title, problem_statement, desired_outcome, impact ranges, preliminary effort guess, strategic tags, etc. Each row mapped into Initiative (with source_sheet_id, source_tab_name, source_row_number).

3. Central Backlog sheet  
Consolidated, cleaned view: one row per Initiative across all intake sheets. Shows normalized fields, computed scores, status, missing_fields, llm_summary, active_scoring_framework, use_math_model flag. Acts as the operational UI for Product; backend remains source of truth.

4. Backlog (conceptual)  
Set of all Initiatives in any status (new → approved_in_principle → scheduled/rejected). Persisted in DB; rendered in Central Backlog sheet.

5. Roadmap  
A curated, time‑bound subset of Initiatives selected for delivery (e.g. “2025 H1 Growth”). Stored as Roadmap (meta: name, timeframe_label) plus RoadmapEntries linking initiatives with scheduling/prioritization metadata.

6. RoadmapEntry  
Association object between Roadmap and Initiative. Holds per‑roadmap fields: priority_rank, planned_quarter/year, is_selected, is_locked_in, scenario_label, optimization_run_id, and snapshot scores (value_score_used, effort_score_used, overall_score_used).

7. MathModels sheet  
**Multiple-models-per-initiative** workspace for quantitative impact modeling. Each initiative can have N models targeting different KPIs. Columns: initiative_key, model_name, **target_kpi_key** (which KPI this model affects), **metric_chain_text** ("immediate → intermediate → target"), formula_text, **is_primary** (representative score flag), **computed_score** (model's calculated impact), approved_by_user. PM defines metric chains → LLM suggests formulas → PM approves → system computes scores → **KPI contributions derived** from model scores.

8. InitiativeMathModel (DB)  
**Multiple math models per Initiative** (1:N relationship via initiative_id FK). Each model targets a specific KPI and defines the impact pathway. Fields: **initiative_id** (FK), **target_kpi_key** (which KPI: north_star/strategic), **metric_chain_text** (PM input: "signups → activation → revenue"), **metric_chain_json** (parsed chain), formula_text (approved formula), **is_primary** (representative model flag), **computed_score** (model's calculated impact), parameters_json, assumptions_text, suggested_by_llm flag. **KPI Contributions Flow**: Model scores aggregate into Initiative.kpi_contribution_json via kpi_contribution_adapter.

9. Params sheet  
Normalized parameter table: one row per (initiative_key, framework, param_name). Columns: display_name, value, unit, min, max, source, approved flag, last_updated. Used by any scoring framework (RICE inputs, math model variables) to avoid wide sheets.

10. Scoring frameworks  
Pluggable algorithms (RICE, MathModel, WSJF, etc.) implementing a common interface to produce ScoreResult (value_score, effort_score, overall_score, details). Selection indicated by Initiative.active_scoring_framework.

11. InitiativeScore (history)  
Optional historical snapshots per scoring run (framework name, scores, timestamp, llm_suggested boolean, approved_by_user). Enables audit and re‑calculation tracking.

12. Status (workflow)  
Lifecycle marker on Initiative: e.g. new, needs_info, under_review, ready_for_estimate, approved_in_principle, scheduled, rejected. Driven by validation, manual product decisions, and optimization outcomes.

13. missing_fields  
Computed validation summary listing required fields absent for an Initiative. Written to DB and central sheet to prompt completion; can flip status to needs_info.

14. llm_summary / llm_notes  
Auto‑generated short textual artifacts: summary of context (llm_summary) and reasoning/explanations or formula notes (llm_notes). Read‑only to users.

15. use_math_model  
Boolean flag on Initiative signaling that scores come from a custom quantitative model rather than simple heuristic (enables MathModelFramework path).

16. active_scoring_framework  
String identifier (e.g. "RICE", "MATH_MODEL") telling ScoringService which framework to apply.

17. Parameter seeding  
Backend process that, upon framework activation or formula approval, creates required parameter rows in Params sheet (either known set for RICE or parsed variables for math model) with metadata defaults.

18. Optimization scenario  
Result of running portfolio selection (capacity/constraints) producing selected initiatives, ranks, timing. Scenario metadata stored via optimization_run_id + scenario_label; reflected in Roadmap & RoadmapEntries.

19. Overall score fields  
value_score: normalized or raw value estimate from chosen framework/model.  
effort_score: normalized effort proxy (e.g. RICE effort or engineering_days).  
overall_score: composite (e.g. value/effort or weighted sum) used by optimization; can be overridden manually.

20. Sheet IDs / tab names (clarification)  
Sheet ID: unique Google Sheets document identifier (in URL).  
Tab name: worksheet title inside that document (e.g. “UK_Intake”, “Central_Backlog”, “Params”). Backend uses (sheet_id, tab_name) to trace original row locations.

## Live Sheets Registry
*Last synced: 2026-01-27 13:54 UTC*

This section is auto-generated by `scripts/sync_sheets_registry.py`.
First 3 rows per tab: Row 1 = main header, Rows 2-3 = metadata/comments.

### Intake Sheets

#### Intake Sheet: intake_emea
- **Spreadsheet ID**: `1mQLVtMhgC-09fQ2xczyxghiIwZFb2e5ac5JVODkyJsU`
- **Region**: EMEA
- **Description**: Test EMEA intake sheet

##### Tab: `Marketing_EMEA`
- **Department**: Marketing
- **Active**: True
  - **Total Columns**: 7

  - **Column A**: `Title`
    - Row 1 (Header): `Title`
    - Row 2 (Meta1): `Test initiative 1`
    - Row 3 (Meta2): `data 2`

  - **Column B**: `Department`
    - Row 1 (Header): `Department`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): ``

  - **Column C**: `Requesting Team`
    - Row 1 (Header): `Requesting Team`
    - Row 2 (Meta1): `Growth`
    - Row 3 (Meta2): `data 3`

  - **Column D**: `Requester Name`
    - Row 1 (Header): `Requester Name`
    - Row 2 (Meta1): `Alice`
    - Row 3 (Meta2): `data 4`

  - **Column E**: `Lifecycle_status`
    - Row 1 (Header): `Lifecycle_status`
    - Row 2 (Meta1): `new`
    - Row 3 (Meta2): `data 5`

  - **Column F**: `Country`
    - Row 1 (Header): `Country`
    - Row 2 (Meta1): `UK`
    - Row 3 (Meta2): `data 6`

  - **Column G**: `Initiative Key`
    - Row 1 (Header): `Initiative Key`
    - Row 2 (Meta1): `INIT-000001`
    - Row 3 (Meta2): `INIT-000002`


##### Tab: `Sales_EMEA`
- **Department**: N/A
  - *No data found*

### Central Backlog Sheet(s)

#### Central Backlog: global
- **Spreadsheet ID**: `1dd5ux4iapJtHWNb1E0gK7wQF644csy30M40dhs_XGH8`

##### Tab: `Backlog` (Primary)
  - **Total Columns**: 31

  - **Column A**: `Initiative Key`
    - Row 1 (Header): `Initiative Key`
    - Row 2 (Meta1): `Initiative.initiative_key`
    - Row 3 (Meta2): `Backend → Sheet`

  - **Column B**: `Title`
    - Row 1 (Header): `Title`
    - Row 2 (Meta1): `Initiative.title`
    - Row 3 (Meta2): `Intake sheet → DB → Backlog Sync - PM can edit`

  - **Column C**: `Department`
    - Row 1 (Header): `Department`
    - Row 2 (Meta1): `Initiative.department`
    - Row 3 (Meta2): `Intake sheet → DB → Backlog Sync - PM can edit`

  - **Column D**: `Requesting Team`
    - Row 1 (Header): `Requesting Team`
    - Row 2 (Meta1): `Initiative.requesting_team`
    - Row 3 (Meta2): `Intake sheet → DB → Backlog Sync - PM can edit`

  - **Column E**: `Requester Name`
    - Row 1 (Header): `Requester Name`
    - Row 2 (Meta1): `Initiative.requester_name`
    - Row 3 (Meta2): `Intake sheet → DB → Backlog Sync - PM can edit`

  - **Column F**: `Requester Email`
    - Row 1 (Header): `Requester Email`
    - Row 2 (Meta1): `Initiative.requester_email`
    - Row 3 (Meta2): `Intake → DB → Backlog sync`

  - **Column G**: `Country`
    - Row 1 (Header): `Country`
    - Row 2 (Meta1): `Initiative.country`
    - Row 3 (Meta2): `Intake sheet → DB → Backlog Sync - PM can edit`

  - **Column H**: `Product Area`
    - Row 1 (Header): `Product Area`
    - Row 2 (Meta1): `Initiative.product_area`
    - Row 3 (Meta2): `PM input → DB`

  - **Column I**: `Lifecycle Status`
    - Row 1 (Header): `Lifecycle Status`
    - Row 2 (Meta1): `Initiative.lifecycle_status`
    - Row 3 (Meta2): `PM input → DB`

  - **Column J**: `Customer Segment`
    - Row 1 (Header): `Customer Segment`
    - Row 2 (Meta1): `Initiative.customer_segment`
    - Row 3 (Meta2): `PM input → DB`

  - **Column K**: `Initiative Type`
    - Row 1 (Header): `Initiative Type`
    - Row 2 (Meta1): `Initiative.initiative_type`
    - Row 3 (Meta2): `PM input → DB`

  - **Column L**: `Hypothesis`
    - Row 1 (Header): `Hypothesis`
    - Row 2 (Meta1): `Initiative.hypothesis`
    - Row 3 (Meta2): `PM input → DB`

  - **Column M**: `Problem Statement`
    - Row 1 (Header): `Problem Statement`
    - Row 2 (Meta1): `Initiative.problem_statement`
    - Row 3 (Meta2): `PM input → DB`

  - **Column N**: `Value Score`
    - Row 1 (Header): `Value Score`
    - Row 2 (Meta1): `Initiative.value_score`
    - Row 3 (Meta2): `Backend computes ← DB (scores)`

  - **Column O**: `Effort Score`
    - Row 1 (Header): `Effort Score`
    - Row 2 (Meta1): `Initiative.effort_score`
    - Row 3 (Meta2): `Backend computes ← DB`

  - **Column P**: `Overall Score`
    - Row 1 (Header): `Overall Score`
    - Row 2 (Meta1): `Initiative.overall_score`
    - Row 3 (Meta2): `Backend computes ← DB`

  - **Column Q**: `Active Scoring Framework`
    - Row 1 (Header): `Active Scoring Framework`
    - Row 2 (Meta1): `Initiative.active_scoring_framework`
    - Row 3 (Meta2): `PM choice → DB`

  - **Column R**: `Use Math Model`
    - Row 1 (Header): `Use Math Model`
    - Row 2 (Meta1): `Initiative.use_math_model`
    - Row 3 (Meta2): `PM choice → DB`

  - **Column S**: `Dependencies Initiatives`
    - Row 1 (Header): `Dependencies Initiatives`
    - Row 2 (Meta1): `Initiative.dependencies_initiatives`
    - Row 3 (Meta2): `PM input → DB`

  - **Column T**: `Dependencies Others`
    - Row 1 (Header): `Dependencies Others`
    - Row 2 (Meta1): `Initiative.dependencies_others`
    - Row 3 (Meta2): `PM input → DB`

  - **Column U**: `LLM Summary`
    - Row 1 (Header): `LLM Summary`
    - Row 2 (Meta1): `Initiative.llm_summary`
    - Row 3 (Meta2): `LLM text (editable) → DB`

  - **Column V**: `Strategic Priority Coefficient`
    - Row 1 (Header): `Strategic Priority Coefficient`
    - Row 2 (Meta1): `Initiative.strategic_priority_coefficient`
    - Row 3 (Meta2): `PM input → DB (or default=1.0)`

  - **Column W**: `Updated At`
    - Row 1 (Header): `Updated At`
    - Row 2 (Meta1): `Initiative.updated_at`
    - Row 3 (Meta2): `Backend writes → Sheet (read-only)`

  - **Column X**: `Updated Source`
    - Row 1 (Header): `Updated Source`
    - Row 2 (Meta1): `Initiative.updated_source`
    - Row 3 (Meta2): `Backend writes → Sheet (read-only)`

  - **Column Y**: `Immediate KPI Key`
    - Row 1 (Header): `Immediate KPI Key`
    - Row 2 (Meta1): `Initiative.immediate_kpi_key`
    - Row 3 (Meta2): `ENTRY: ProductOps/MathModels; FLOW: ProductOps→DB→Backlog (read-only).`

  - **Column Z**: `Metric Chain JSON`
    - Row 1 (Header): `Metric Chain JSON`
    - Row 2 (Meta1): `Initiative.metric_chain_json`
    - Row 3 (Meta2): `ENTRY: ProductOps/MathModels; FLOW: ProductOps→DB→Backlog (read-only).`

  - **Column AA**: `engineering_tokens`
    - Row 1 (Header): `engineering_tokens`
    - Row 2 (Meta1): `Initiative.engineering_tokens`
    - Row 3 (Meta2): `Copied from optimization_cetner/candidates tab to Central Backlog optionally too via formula
Entry surgace is optimization_cetner/candidates`

  - **Column AB**: `deadline_date`
    - Row 1 (Header): `deadline_date`
    - Row 2 (Meta1): `Initiative.deadline_date`
    - Row 3 (Meta2): `Copied from optimization_cetner/candidates tab to Central Backlog optionally too via formula
Entry surgace is optimization_cetner/candidates`

  - **Column AC**: `is_mandatory`
    - Row 1 (Header): `is_mandatory`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): `Copied from optimization_cetner/candidates tab to Central Backlog optionally too via formula
Entry surgace is optimization_cetner/candidates`

  - **Column AD**: `Is Optimization Candidate`
    - Row 1 (Header): `Is Optimization Candidate`
    - Row 2 (Meta1): `Initiative.is_optimization_candidate`
    - Row 3 (Meta2): `PM input → DB`

  - **Column AE**: `Candidate Period Key`
    - Row 1 (Header): `Candidate Period Key`
    - Row 2 (Meta1): `Initiative.candidate_period_key`
    - Row 3 (Meta2): `PM input → DB`


##### Tab: `Test`
  - *No data found*

### ProductOps Sheet

- **Spreadsheet ID**: `1zfxk-qQram2stUWYytiXapOeVh3yNulb32QYVJrOGt8`

#### Tab: `Scoring_Inputs` (Scoring Inputs)
  - **Total Columns**: 28

  - **Column A**: `initiative_key`
    - Row 1 (Header): `initiative_key`
    - Row 2 (Meta1): `Initiative.initiative_key`
    - Row 3 (Meta2): `ENTRY: Copied via formula from Backlog; FLOW: Sheet→Sheet (formula), read-only.`

  - **Column B**: `updated at`
    - Row 1 (Header): `updated at`
    - Row 2 (Meta1): `Initiative.updated_at`
    - Row 3 (Meta2): `Backend writes → Sheet (timestamp)`

  - **Column C**: `active_scoring_framework`
    - Row 1 (Header): `active_scoring_framework`
    - Row 2 (Meta1): `Initiative.active_scoring_framework`
    - Row 3 (Meta2): `PM input → DB (Flow3 sync)`

  - **Column D**: `use_math_model`
    - Row 1 (Header): `use_math_model`
    - Row 2 (Meta1): `Initiative.use_math_model`
    - Row 3 (Meta2): `PM input → DB (Flow3 sync)`

  - **Column E**: `status`
    - Row 1 (Header): `status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Sheet-only status (optional) written by backend`

  - **Column F**: `active_value_score`
    - Row 1 (Header): `active_value_score`
    - Row 2 (Meta1): `Initiative.value_score`
    - Row 3 (Meta2): `Backend writes ← DB (Flow2 activation)`

  - **Column G**: `active_effort_score`
    - Row 1 (Header): `active_effort_score`
    - Row 2 (Meta1): `Initiative.effort_score`
    - Row 3 (Meta2): `Backend writes ← DB`

  - **Column H**: `active_overall_score`
    - Row 1 (Header): `active_overall_score`
    - Row 2 (Meta1): `Initiative.overall_score`
    - Row 3 (Meta2): `Backend writes ← DB`

  - **Column I**: `math_value_score`
    - Row 1 (Header): `math_value_score`
    - Row 2 (Meta1): `Initiative.math_value_score`
    - Row 3 (Meta2): `Backend writes ← DB (Flow3 compute)`

  - **Column J**: `math_effort_score`
    - Row 1 (Header): `math_effort_score`
    - Row 2 (Meta1): `Initiative.math_effort_score`
    - Row 3 (Meta2): `Backend writes ← DB`

  - **Column K**: `math_overall_score`
    - Row 1 (Header): `math_overall_score`
    - Row 2 (Meta1): `Initiative.math_overall_score`
    - Row 3 (Meta2): `Backend writes ← DB`

  - **Column L**: `math_warnings`
    - Row 1 (Header): `math_warnings`
    - Row 2 (Meta1): `Initiative.math_warnings`
    - Row 3 (Meta2): `Backend writes → Sheet (Sheet only)`

  - **Column M**: `rice_reach`
    - Row 1 (Header): `rice_reach`
    - Row 2 (Meta1): `Initiative.rice_reach`
    - Row 3 (Meta2): `PM input → DB (Flow3 sync)`

  - **Column N**: `rice_impact`
    - Row 1 (Header): `rice_impact`
    - Row 2 (Meta1): `Initiative.rice_impact`
    - Row 3 (Meta2): `PM input → DB`

  - **Column O**: `rice_confidence`
    - Row 1 (Header): `rice_confidence`
    - Row 2 (Meta1): `Initiative.rice_confidence`
    - Row 3 (Meta2): `PM input → DB`

  - **Column P**: `rice_effort`
    - Row 1 (Header): `rice_effort`
    - Row 2 (Meta1): `Initiative.rice_effort`
    - Row 3 (Meta2): `PM input → DB`

  - **Column Q**: `wsjf_business_value`
    - Row 1 (Header): `wsjf_business_value`
    - Row 2 (Meta1): `Initiative.wsjf_business_value`
    - Row 3 (Meta2): `PM input → DB`

  - **Column R**: `wsjf_time_criticality`
    - Row 1 (Header): `wsjf_time_criticality`
    - Row 2 (Meta1): `Initiative.wsjf_time_criticality`
    - Row 3 (Meta2): `PM input → DB`

  - **Column S**: `wsjf_risk_reduction`
    - Row 1 (Header): `wsjf_risk_reduction`
    - Row 2 (Meta1): `Initiative.wsjf_risk_reduction`
    - Row 3 (Meta2): `PM input → DB`

  - **Column T**: `wsjf_job_size`
    - Row 1 (Header): `wsjf_job_size`
    - Row 2 (Meta1): `Initiative.wsjf_job_size`
    - Row 3 (Meta2): `PM input → DB`

  - **Column U**: `rice_value_score`
    - Row 1 (Header): `rice_value_score`
    - Row 2 (Meta1): `Initiative.rice_value_score`
    - Row 3 (Meta2): `Backend writes ← DB (Flow3 compute)`

  - **Column V**: `rice_effort_score`
    - Row 1 (Header): `rice_effort_score`
    - Row 2 (Meta1): `Initiative.rice_effort_score`
    - Row 3 (Meta2): `Backend writes ← DB`

  - **Column W**: `rice_overall_score`
    - Row 1 (Header): `rice_overall_score`
    - Row 2 (Meta1): `Initiative.rice_overall_score`
    - Row 3 (Meta2): `Backend writes ← DB`

  - **Column X**: `wsjf_value_score`
    - Row 1 (Header): `wsjf_value_score`
    - Row 2 (Meta1): `Initiative.wsjf_value_score`
    - Row 3 (Meta2): `Backend writes ← DB`

  - **Column Y**: `wsjf_effort_score`
    - Row 1 (Header): `wsjf_effort_score`
    - Row 2 (Meta1): `Initiative.wsjf_effort_score`
    - Row 3 (Meta2): `Backend writes ← DB`

  - **Column Z**: `wsjf_overall_score`
    - Row 1 (Header): `wsjf_overall_score`
    - Row 2 (Meta1): `Initiative.wsjf_overall_score`
    - Row 3 (Meta2): `Backend writes ← DB`

  - **Column AA**: `comment`
    - Row 1 (Header): `comment`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Sheet-only PM notes`

  - **Column AB**: `Updated Source`
    - Row 1 (Header): `Updated Source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`


#### Tab: `MathModels` (Math Models)
  - **Total Columns**: 19

  - **Column A**: `initiative_key`
    - Row 1 (Header): `initiative_key`
    - Row 2 (Meta1): `Initiative.initiative_key`
    - Row 3 (Meta2): `PM Copies via formula from Backlog; FLOW: Sheet→Sheet (formula), read-only.`

  - **Column B**: `target KPI key`
    - Row 1 (Header): `target KPI key`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): ``

  - **Column C**: `model_name`
    - Row 1 (Header): `model_name`
    - Row 2 (Meta1): `InitiativeMathModel.model_name`
    - Row 3 (Meta2): `PM input →DB (MathModelSync).`

  - **Column D**: `model_description_free_text`
    - Row 1 (Header): `model_description_free_text`
    - Row 2 (Meta1): `InitiativeMathModel.model_description_free_text`
    - Row 3 (Meta2): `PM input →DB (MathModelSync).`

  - **Column E**: `is_primary`
    - Row 1 (Header): `is_primary`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): ``

  - **Column F**: `metric_chain_text`
    - Row 1 (Header): `metric_chain_text`
    - Row 2 (Meta1): `Initiative.metric_chain_json`
    - Row 3 (Meta2): `PM input → DB (parsed → metric_chain_json) - source of truth`

  - **Column G**: `immediate KPI key`
    - Row 1 (Header): `immediate KPI key`
    - Row 2 (Meta1): `Initiative.immediate_kpi_key`
    - Row 3 (Meta2): `PM input → DB (will be used as read only on central backlog too) - source of truth`

  - **Column H**: `computed_score`
    - Row 1 (Header): `computed_score`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): ``

  - **Column I**: `llm_suggested_metric_chain_text`
    - Row 1 (Header): `llm_suggested_metric_chain_text`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `LLM writes → Sheet (PM may copy)`

  - **Column J**: `formula_text`
    - Row 1 (Header): `formula_text`
    - Row 2 (Meta1): `InitiativeMathModel.formula_text`
    - Row 3 (Meta2): `PM input → DB - source of truth`

  - **Column K**: `status`
    - Row 1 (Header): `status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Sheet-only status (optional) written by backend`

  - **Column L**: `approved_by_user`
    - Row 1 (Header): `approved_by_user`
    - Row 2 (Meta1): `InitiativeMathModel.approved_by_user`
    - Row 3 (Meta2): `PM input approval → DB`

  - **Column M**: `llm_suggested_formula_text`
    - Row 1 (Header): `llm_suggested_formula_text`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `LLM writes → Sheet (PM may copy)`

  - **Column N**: `llm_notes`
    - Row 1 (Header): `llm_notes`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `LLM writes → Sheet (sheet only)`

  - **Column O**: `assumptions_text`
    - Row 1 (Header): `assumptions_text`
    - Row 2 (Meta1): `InitiativeMathModel.assumptions_text`
    - Row 3 (Meta2): `PM input → DB`

  - **Column P**: `model_prompt_to_llm`
    - Row 1 (Header): `model_prompt_to_llm`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `PM input - Sheet only`

  - **Column Q**: `suggested_by_llm`
    - Row 1 (Header): `suggested_by_llm`
    - Row 2 (Meta1): `InitiativeMathModel.suggested_by_llm`
    - Row 3 (Meta2): `Backend sets → Sheet →DB (on save)`

  - **Column R**: `updated source`
    - Row 1 (Header): `updated source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes: DB → Sheet (provenance)`

  - **Column S**: `updated at`
    - Row 1 (Header): `updated at`
    - Row 2 (Meta1): `InitiativeMathModel.updated_at`
    - Row 3 (Meta2): `Backend timestamps: DB→Sheet (timestamp)`


#### Tab: `Params` (Parameters)
  - **Total Columns**: 16

  - **Column A**: `initiative_key`
    - Row 1 (Header): `initiative_key`
    - Row 2 (Meta1): `Initiative.initiative_key`
    - Row 3 (Meta2): `Autoseeded by backend Seed Params job OR PM Copies via formula from Backlog sheet in manual entries`

  - **Column B**: `framework`
    - Row 1 (Header): `framework`
    - Row 2 (Meta1): `InitiativeParam.framework`
    - Row 3 (Meta2): `Backend in autoseed cases /PM in manual cases sets → DB`

  - **Column C**: `model name`
    - Row 1 (Header): `model name`
    - Row 2 (Meta1): `InitiativeMathModel.model_name`
    - Row 3 (Meta2): `Backend seeds from model_name; FLOW: Backend→Sheet (read-only).`

  - **Column D**: `param_name`
    - Row 1 (Header): `param_name`
    - Row 2 (Meta1): `InitiativeParam.param_name`
    - Row 3 (Meta2): `Backend seeded / PM edits → DB`

  - **Column E**: `value`
    - Row 1 (Header): `value`
    - Row 2 (Meta1): `InitiativeParam.value`
    - Row 3 (Meta2): `PM input → DB`

  - **Column F**: `approved`
    - Row 1 (Header): `approved`
    - Row 2 (Meta1): `InitiativeParam.approved`
    - Row 3 (Meta2): `PM input approval → DB`

  - **Column G**: `is_auto_seeded`
    - Row 1 (Header): `is_auto_seeded`
    - Row 2 (Meta1): `InitiativeParam.is_auto_seeded`
    - Row 3 (Meta2): `Backend sets (seed) → DB`

  - **Column H**: `param_display`
    - Row 1 (Header): `param_display`
    - Row 2 (Meta1): `InitiativeParam.param_display`
    - Row 3 (Meta2): `LLM seeds metadata → Sheet (editable) → DB (on save)`

  - **Column I**: `description`
    - Row 1 (Header): `description`
    - Row 2 (Meta1): `InitiativeParam.description`
    - Row 3 (Meta2): `LLM seeds metadata → Sheet → DB (editable)`

  - **Column J**: `unit`
    - Row 1 (Header): `unit`
    - Row 2 (Meta1): `InitiativeParam.unit`
    - Row 3 (Meta2): `LLM seeds metadata → Sheet → DB (editable)`

  - **Column K**: `min`
    - Row 1 (Header): `min`
    - Row 2 (Meta1): `InitiativeParam.min`
    - Row 3 (Meta2): `PM input Optional Sheet → DB `

  - **Column L**: `max`
    - Row 1 (Header): `max`
    - Row 2 (Meta1): `InitiativeParam.max`
    - Row 3 (Meta2): `PM input Optional Sheet → DB `

  - **Column M**: `source`
    - Row 1 (Header): `source`
    - Row 2 (Meta1): `InitiativeParam.source`
    - Row 3 (Meta2): `PM input Optional Sheet → DB `

  - **Column N**: `notes`
    - Row 1 (Header): `notes`
    - Row 2 (Meta1): `InitiativeParam.notes`
    - Row 3 (Meta2): `PM input Optional Sheet → DB `

  - **Column O**: `updated source`
    - Row 1 (Header): `updated source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`

  - **Column P**: `updated at`
    - Row 1 (Header): `updated at`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend timestamps: DB→Sheet (timestamp)`


#### Tab: `Metrics_Config` (Metrics Config)
  - **Total Columns**: 10

  - **Column A**: `kpi_key`
    - Row 1 (Header): `kpi_key`
    - Row 2 (Meta1): `OrganizationMetricsConfig.kpi_key`
    - Row 3 (Meta2): `PM input Sheet → DB (Save)`

  - **Column B**: `kpi_name`
    - Row 1 (Header): `kpi_name`
    - Row 2 (Meta1): `OrganizationMetricsConfig.kpi_name`
    - Row 3 (Meta2): `PM input Sheet → DB (Save)`

  - **Column C**: `kpi_level`
    - Row 1 (Header): `kpi_level`
    - Row 2 (Meta1): `OrganizationMetricsConfig.kpi_level`
    - Row 3 (Meta2): `PM input Sheet → DB (Save)`

  - **Column D**: `unit`
    - Row 1 (Header): `unit`
    - Row 2 (Meta1): `OrganizationMetricsConfig.unit`
    - Row 3 (Meta2): `PM input Sheet → DB (Save)`

  - **Column E**: `description`
    - Row 1 (Header): `description`
    - Row 2 (Meta1): `OrganizationMetricsConfig.description`
    - Row 3 (Meta2): `PM input Sheet → DB (Save)`

  - **Column F**: `is_active`
    - Row 1 (Header): `is_active`
    - Row 2 (Meta1): `OrganizationMetricsConfig.is_active`
    - Row 3 (Meta2): `PM input Sheet → DB (Save)`

  - **Column G**: `notes`
    - Row 1 (Header): `notes`
    - Row 2 (Meta1): `OrganizationMetricsConfig.notes`
    - Row 3 (Meta2): `PM notes Sheet → DB`

  - **Column H**: `run_status`
    - Row 1 (Header): `run_status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (status)`

  - **Column I**: `updated_source`
    - Row 1 (Header): `updated_source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`

  - **Column J**: `updated_at`
    - Row 1 (Header): `updated_at`
    - Row 2 (Meta1): `OrganizationMetricsConfig.updated_at`
    - Row 3 (Meta2): `Backend writes → Sheet (timestamp)`


#### Tab: `KPI_Contributions` (KPI Contributions)
  - **Total Columns**: 8

  - **Column A**: `initiative_key`
    - Row 1 (Header): `initiative_key`
    - Row 2 (Meta1): `Initiative.initiative_key`
    - Row 3 (Meta2): `Always updated with system-computed values`

  - **Column B**: `kpi_contribution_json`
    - Row 1 (Header): `kpi_contribution_json`
    - Row 2 (Meta1): `Initiative.kpi_contribution_json`
    - Row 3 (Meta2): `PM input edits here; FLOW: ProductOps/KPI_Contributions → DB; validate keys & units vs Metrics_Config`

  - **Column C**: `kpi_contribution_computed_json`
    - Row 1 (Header): `kpi_contribution_computed_json`
    - Row 2 (Meta1): `kpi_contribution_computed_json`
    - Row 3 (Meta2): `Always updated with system-computed values`

  - **Column D**: `kpi_contribution_source`
    - Row 1 (Header): `kpi_contribution_source`
    - Row 2 (Meta1): `kpi_contribution_source`
    - Row 3 (Meta2): `Always updated with system-computed values`

  - **Column E**: `notes`
    - Row 1 (Header): `notes`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Optional PM notes: Sheet-only notes; FLOW: none`

  - **Column F**: `run_status`
    - Row 1 (Header): `run_status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend status; FLOW: Backend → Sheet`

  - **Column G**: `updated_source`
    - Row 1 (Header): `updated_source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend provenance; FLOW: Backend → Sheet`

  - **Column H**: `updated_at`
    - Row 1 (Header): `updated_at`
    - Row 2 (Meta1): `Initiative.updated_at`
    - Row 3 (Meta2): `Backend timestamp; FLOW: DB → Sheet`


#### Tab: `Config` (Config)
  - *No data found*

### Optimization Center Sheet

- **Spreadsheet ID**: `1ctCxdh4awipo_mXf_gdMTL3aVf8QZVaKAukOwBhygfU`

#### Tab: `Candidates` (Candidates)
  - **Total Columns**: 25

  - **Column A**: `initiative_key`
    - Row 1 (Header): `initiative_key`
    - Row 2 (Meta1): `Initiative.initiative_key`
    - Row 3 (Meta2): `PM Copies via formula from Backlog; Sheet→Sheet (formula), read-only.`

  - **Column B**: `is_selected_for_run`
    - Row 1 (Header): `is_selected_for_run`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `PM input: Sheet-only checkbox`

  - **Column C**: `title`
    - Row 1 (Header): `title`
    - Row 2 (Meta1): `Initiative.title`
    - Row 3 (Meta2): `PM Copies via formula from Backlog; Sheet→Sheet (formula), read-only.`

  - **Column D**: `country`
    - Row 1 (Header): `country`
    - Row 2 (Meta1): `Initiative.country`
    - Row 3 (Meta2): `PM Copies via formula from Backlog; Sheet→Sheet (formula), read-only.`

  - **Column E**: `department`
    - Row 1 (Header): `department`
    - Row 2 (Meta1): `Initiative.department`
    - Row 3 (Meta2): `PM Copies via formula from Backlog; Sheet→Sheet (formula), read-only.`

  - **Column F**: `category`
    - Row 1 (Header): `category`
    - Row 2 (Meta1): `Initiative.category`
    - Row 3 (Meta2): `PM input - categorize work type for optimization`

  - **Column G**: `program_key`
    - Row 1 (Header): `program_key`
    - Row 2 (Meta1): `Initiative.program_key`
    - Row 3 (Meta2): `PM input - assign initiative to a program for cross-functional tracking`

  - **Column H**: `engineering_tokens`
    - Row 1 (Header): `engineering_tokens`
    - Row 2 (Meta1): `Initiative.engineering_tokens`
    - Row 3 (Meta2): `PM input Sheet → DB + copied from optimization/candidates tab to Central Backlog optionally too via formula`

  - **Column I**: `deadline_date`
    - Row 1 (Header): `deadline_date`
    - Row 2 (Meta1): `Initiative.deadline_date`
    - Row 3 (Meta2): `PM input Sheet → DB + copied from optimization/candidates tab to Central Backlog optionally too via formula`

  - **Column J**: `north_star_contribution`
    - Row 1 (Header): `north_star_contribution`
    - Row 2 (Meta1): `(derived from Initiative.kpi_contribution_json[north_star])`
    - Row 3 (Meta2): `Backend derives ← DB (display only here)
entry surface is ProductOps/KPI_contributions`

  - **Column K**: `strategic_kpi_contributions`
    - Row 1 (Header): `strategic_kpi_contributions`
    - Row 2 (Meta1): `(derived from Initiative.kpi_contribution_json)`
    - Row 3 (Meta2): `Backend derives ← DB (display only here)
entry surface is ProductOps/KPI_contributions`

  - **Column L**: `is_mandatory`
    - Row 1 (Header): `is_mandatory`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): `READ-ONLY. Derived from Constraints tab. Edit constraints on Constraints tab only.`

  - **Column M**: `mandate_reason`
    - Row 1 (Header): `mandate_reason`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): `?`

  - **Column N**: `bundle_key`
    - Row 1 (Header): `bundle_key`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): `READ-ONLY. Derived from Constraints tab (bundle_all_or_nothing). Display only.`

  - **Column O**: `prerequisite_keys`
    - Row 1 (Header): `prerequisite_keys`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): `READ-ONLY. Derived from Constraints tab (require_prereq). Display only.`

  - **Column P**: `exclusion_keys`
    - Row 1 (Header): `exclusion_keys`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): `READ-ONLY. Derived from Constraints tab (exclude_* constraints). Display only.`

  - **Column Q**: `synergy_group_keys`
    - Row 1 (Header): `synergy_group_keys`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): `READ-ONLY. Derived from Constraints tab (synergy_bonus). Display only.`

  - **Column R**: `active_scoring_framework`
    - Row 1 (Header): `active_scoring_framework`
    - Row 2 (Meta1): `Initiative.active_scoring_framework`
    - Row 3 (Meta2): `Copied from Central Backlog via formula (PM sets in backlog)`

  - **Column S**: `active_overall_score`
    - Row 1 (Header): `active_overall_score`
    - Row 2 (Meta1): `Initiative.overall_score`
    - Row 3 (Meta2): `Copied from Central Backlog via formula (PM sets in backlog)`

  - **Column T**: `immediate_kpi_key`
    - Row 1 (Header): `immediate_kpi_key`
    - Row 2 (Meta1): `Initiative.immediate_kpi_key`
    - Row 3 (Meta2): `Copied from Product Ops MathModels tab`

  - **Column U**: `lifecycle_status`
    - Row 1 (Header): `lifecycle_status`
    - Row 2 (Meta1): `Initiative.status`
    - Row 3 (Meta2): `PM Copies via formula from Backlog; Sheet→Sheet (formula), read-only.`

  - **Column V**: `notes`
    - Row 1 (Header): `notes`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `PM input: Sheet-only notes`

  - **Column W**: `run_status`
    - Row 1 (Header): `run_status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (status)`

  - **Column X**: `updated_source`
    - Row 1 (Header): `updated_source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`

  - **Column Y**: `updated_at`
    - Row 1 (Header): `updated_at`
    - Row 2 (Meta1): `Initiative.updated_at`
    - Row 3 (Meta2): `Backend writes → Sheet (timestamp)`


#### Tab: `Scenario_Config` (Scenario_Config)
  - **Total Columns**: 9

  - **Column A**: `scenario_name`
    - Row 1 (Header): `scenario_name`
    - Row 2 (Meta1): `OptimizationScenario.name`
    - Row 3 (Meta2): `PM input → DB (Save)`

  - **Column B**: `period_key`
    - Row 1 (Header): `period_key`
    - Row 2 (Meta1): `OptimizationScenario.period_key`
    - Row 3 (Meta2): `PM input → DB`

  - **Column C**: `capacity_total_tokens`
    - Row 1 (Header): `capacity_total_tokens`
    - Row 2 (Meta1): `OptimizationScenario.capacity_total_tokens`
    - Row 3 (Meta2): `PM input → DB`

  - **Column D**: `objective_mode`
    - Row 1 (Header): `objective_mode`
    - Row 2 (Meta1): `OptimizationScenario.objective_mode`
    - Row 3 (Meta2): `PM input → DB`

  - **Column E**: `objective_weights_json`
    - Row 1 (Header): `objective_weights_json`
    - Row 2 (Meta1): `OptimizationScenario.objective_weights_json`
    - Row 3 (Meta2): `PM input → DB (KPI keys ∈ {north_star + strategic})`

  - **Column F**: `notes`
    - Row 1 (Header): `notes`
    - Row 2 (Meta1): `OptimizationScenario.notes`
    - Row 3 (Meta2): `PM notes → DB`

  - **Column G**: `run_status`
    - Row 1 (Header): `run_status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (status)`

  - **Column H**: `updated_source`
    - Row 1 (Header): `updated_source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`

  - **Column I**: `updated_at`
    - Row 1 (Header): `updated_at`
    - Row 2 (Meta1): `OptimizationScenario.updated_at`
    - Row 3 (Meta2): `Backend writes → Sheet (timestamp)`


#### Tab: `Constraints` (Constraints)
  - **Total Columns**: 13

  - **Column A**: `constraint_set_name`
    - Row 1 (Header): `constraint_set_name`
    - Row 2 (Meta1): `OptimizationConstraintSet.name`
    - Row 3 (Meta2): `PM input → DB (Save)`

  - **Column B**: `scenario_name`
    - Row 1 (Header): `scenario_name`
    - Row 2 (Meta1): `n/a`
    - Row 3 (Meta2): `PM input (sheet only)`

  - **Column C**: `constraint_type`
    - Row 1 (Header): `constraint_type`
    - Row 2 (Meta1): `OptimizationConstraintSet.(rows/json)`
    - Row 3 (Meta2): `PM input → DB (Save)`

  - **Column D**: `dimension`
    - Row 1 (Header): `dimension`
    - Row 2 (Meta1): `OptimizationConstraintSet.(rows/json)`
    - Row 3 (Meta2): `PM input → DB`

  - **Column E**: `dimension_key`
    - Row 1 (Header): `dimension_key`
    - Row 2 (Meta1): `OptimizationConstraintSet.(rows/json)`
    - Row 3 (Meta2): `PM input → DB`

  - **Column F**: `min_tokens`
    - Row 1 (Header): `min_tokens`
    - Row 2 (Meta1): `OptimizationConstraintSet.(rows/json)`
    - Row 3 (Meta2): `PM input → DB`

  - **Column G**: `max_tokens`
    - Row 1 (Header): `max_tokens`
    - Row 2 (Meta1): `OptimizationConstraintSet.(rows/json)`
    - Row 3 (Meta2): `PM input → DB`

  - **Column H**: `bundle_member_keys`
    - Row 1 (Header): `bundle_member_keys`
    - Row 2 (Meta1): `OptimizationConstraintSet.(rows/json)`
    - Row 3 (Meta2): `PM input → DB`

  - **Column I**: `prereq_member_keys`
    - Row 1 (Header): `prereq_member_keys`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): ``

  - **Column J**: `notes`
    - Row 1 (Header): `notes`
    - Row 2 (Meta1): `OptimizationConstraintSet.notes`
    - Row 3 (Meta2): `PM notes → DB`

  - **Column K**: `run_status`
    - Row 1 (Header): `run_status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (status)`

  - **Column L**: `updated_source`
    - Row 1 (Header): `updated_source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`

  - **Column M**: `updated_at`
    - Row 1 (Header): `updated_at`
    - Row 2 (Meta1): `OptimizationConstraintSet.updated_at`
    - Row 3 (Meta2): `Backend writes → Sheet (timestamp)`


#### Tab: `Targets` (Targets)
  - **Total Columns**: 11

  - **Column A**: `constraint_set_name`
    - Row 1 (Header): `constraint_set_name`
    - Row 2 (Meta1): `OptimizationConstraintSet.name`
    - Row 3 (Meta2): `PM Copies via formula from Constraints; FLOW: Sheet→Sheet (formula), read-only.`

  - **Column B**: `scenario_name`
    - Row 1 (Header): `scenario_name`
    - Row 2 (Meta1): `n/a`
    - Row 3 (Meta2): `PM Copies via formula from Scenario_Config; FLOW: Sheet→Sheet (formula), read-only.`

  - **Column C**: `dimension`
    - Row 1 (Header): `dimension`
    - Row 2 (Meta1): `OptimizationConstraintSet.targets_json[dimension]`
    - Row 3 (Meta2): `PM input → DB (KPI key restricted)`

  - **Column D**: `dimension_key`
    - Row 1 (Header): `dimension_key`
    - Row 2 (Meta1): `OptimizationConstraintSet.targets_json`
    - Row 3 (Meta2): `PM input → DB (KPI key restricted)`

  - **Column E**: `kpi_key`
    - Row 1 (Header): `kpi_key`
    - Row 2 (Meta1): `OptimizationConstraintSet.targets_json`
    - Row 3 (Meta2): `PM input → DB (KPI key restricted)`

  - **Column F**: `floor_or_goal`
    - Row 1 (Header): `floor_or_goal`
    - Row 2 (Meta1): `OptimizationConstraintSet.targets_json`
    - Row 3 (Meta2): `PM input → DB`

  - **Column G**: `target_value`
    - Row 1 (Header): `target_value`
    - Row 2 (Meta1): `OptimizationConstraintSet.targets_json`
    - Row 3 (Meta2): `PM input → DB`

  - **Column H**: `notes`
    - Row 1 (Header): `notes`
    - Row 2 (Meta1): `OptimizationConstraintSet.notes`
    - Row 3 (Meta2): `PM input → DB`

  - **Column I**: `run_status`
    - Row 1 (Header): `run_status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (status)`

  - **Column J**: `updated_source`
    - Row 1 (Header): `updated_source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`

  - **Column K**: `updated_at`
    - Row 1 (Header): `updated_at`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (timestamp)`


#### Tab: `Runs` (Runs)
  - **Total Columns**: 15

  - **Column A**: `run_id`
    - Row 1 (Header): `run_id`
    - Row 2 (Meta1): `OptimizationRun.run_id`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column B**: `scenario_name`
    - Row 1 (Header): `scenario_name`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column C**: `period_key`
    - Row 1 (Header): `period_key`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column D**: `optimization_db_status`
    - Row 1 (Header): `optimization_db_status`
    - Row 2 (Meta1): `OptimizationRun.status`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column E**: `created_at`
    - Row 1 (Header): `created_at`
    - Row 2 (Meta1): `OptimizationRun.started_at`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column F**: `finished_at`
    - Row 1 (Header): `finished_at`
    - Row 2 (Meta1): `OptimizationRun.finished_at`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column G**: `selected_count`
    - Row 1 (Header): `selected_count`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column H**: `capacity_used`
    - Row 1 (Header): `capacity_used`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column I**: `total_objective_raw`
    - Row 1 (Header): `total_objective_raw`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column J**: `total_objective`
    - Row 1 (Header): `total_objective`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column K**: `gap_summary`
    - Row 1 (Header): `gap_summary`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column L**: `results_tab_ref`
    - Row 1 (Header): `results_tab_ref`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column M**: `run_status`
    - Row 1 (Header): `run_status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (status)`

  - **Column N**: `updated_source`
    - Row 1 (Header): `updated_source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`

  - **Column O**: `updated_at`
    - Row 1 (Header): `updated_at`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (timestamp)`


#### Tab: `Results` (Results)
  - **Total Columns**: 19

  - **Column A**: `run_id`
    - Row 1 (Header): `run_id`
    - Row 2 (Meta1): `OptimizationRun.run_id`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column B**: `initiative_key`
    - Row 1 (Header): `initiative_key`
    - Row 2 (Meta1): `PortfolioItem.(initiative_key)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column C**: `selected`
    - Row 1 (Header): `selected`
    - Row 2 (Meta1): `PortfolioItem.selected`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column D**: `allocated_tokens`
    - Row 1 (Header): `allocated_tokens`
    - Row 2 (Meta1): `PortfolioItem.allocated_tokens`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column E**: `country`
    - Row 1 (Header): `country`
    - Row 2 (Meta1): `OptimizationProblem.candidates.country`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column F**: `department`
    - Row 1 (Header): `department`
    - Row 2 (Meta1): `OptimizationProblem.candidates.department`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column G**: `category`
    - Row 1 (Header): `category`
    - Row 2 (Meta1): `OptimizationProblem.candidates.category`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column H**: `program`
    - Row 1 (Header): `program`
    - Row 2 (Meta1): `OptimizationProblem.candidates.program`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column I**: `product`
    - Row 1 (Header): `product`
    - Row 2 (Meta1): `OptimizationProblem.candidates.product`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column J**: `segment`
    - Row 1 (Header): `segment`
    - Row 2 (Meta1): `OptimizationProblem.candidates.segment`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column K**: `objective_mode`
    - Row 1 (Header): `objective_mode`
    - Row 2 (Meta1): `OptimizationProblem.objective.mode`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column L**: `objective_contribution`
    - Row 1 (Header): `objective_contribution`
    - Row 2 (Meta1): `_compute_objective_contribution`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column M**: `north_star_gain`
    - Row 1 (Header): `north_star_gain`
    - Row 2 (Meta1): `OptmizationProblem.candidates.kpi_contributions[north_star_kpi_key]`
    - Row 3 (Meta2): `Backend writes → Sheet (derived)`

  - **Column N**: `active_overall_score`
    - Row 1 (Header): `active_overall_score`
    - Row 2 (Meta1): `Initiative.overall_score`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column O**: `dependency_status`
    - Row 1 (Header): `dependency_status`
    - Row 2 (Meta1): `future`
    - Row 3 (Meta2): `Backend writes → Sheet (derived)`

  - **Column P**: `notes`
    - Row 1 (Header): `notes`
    - Row 2 (Meta1): `PortfolioItem.notes`
    - Row 3 (Meta2): `PM input → DB`

  - **Column Q**: `run_status`
    - Row 1 (Header): `run_status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (status)`

  - **Column R**: `updated_source`
    - Row 1 (Header): `updated_source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`

  - **Column S**: `updated_at`
    - Row 1 (Header): `updated_at`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (timestamp)`


#### Tab: `Gaps_and_Alerts` (Gaps_and_Alerts)
  - **Total Columns**: 13

  - **Column A**: `run_id`
    - Row 1 (Header): `run_id`
    - Row 2 (Meta1): `OptimizationRun.run_id`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column B**: `dimension`
    - Row 1 (Header): `dimension`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column C**: `dimension_key`
    - Row 1 (Header): `dimension_key`
    - Row 2 (Meta1): ``
    - Row 3 (Meta2): ``

  - **Column D**: `kpi_key`
    - Row 1 (Header): `kpi_key`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column E**: `target`
    - Row 1 (Header): `target`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column F**: `achieved`
    - Row 1 (Header): `achieved`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column G**: `gap`
    - Row 1 (Header): `gap`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column H**: `severity`
    - Row 1 (Header): `severity`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `Backend writes → Sheet`

  - **Column I**: `notes`
    - Row 1 (Header): `notes`
    - Row 2 (Meta1): `(derived)`
    - Row 3 (Meta2): `PM input → DB`

  - **Column J**: `recommendation`
    - Row 1 (Header): `recommendation`
    - Row 2 (Meta1): `future`
    - Row 3 (Meta2): `LLM optional → Sheet (later)`

  - **Column K**: `run_status`
    - Row 1 (Header): `run_status`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (status)`

  - **Column L**: `updated_source`
    - Row 1 (Header): `updated_source`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (provenance)`

  - **Column M**: `updated_at`
    - Row 1 (Header): `updated_at`
    - Row 2 (Meta1): `NONE`
    - Row 3 (Meta2): `Backend writes → Sheet (timestamp)`


## Codebase Registry
*Auto-generated: 2026-01-27 13:54 UTC*

This section is auto-generated by `scripts/generate_codebase_registry.py`.
Comprehensive map of `app/` directory structure, modules, classes, and functions.

### Directory Structure
```
app/
├── api
│   ├── routes
│   │   ├── __init__.py
│   │   └── actions.py
│   ├── schemas
│   │   ├── __init__.py
│   │   └── actions.py
│   ├── __init__.py
│   └── deps.py
├── db
│   ├── models
│   │   ├── __init__.py
│   │   ├── action_run.py
│   │   ├── initiative.py
│   │   ├── optimization.py
│   │   ├── roadmap.py
│   │   ├── roadmap_entry.py
│   │   └── scoring.py
│   ├── __init__.py
│   ├── base.py
│   ├── schema_ensure.py
│   └── session.py
├── jobs
│   ├── __init__.py
│   ├── backlog_sync_job.py
│   ├── backlog_update_job.py
│   ├── flow1_full_sync_job.py
│   ├── flow2_scoring_activation_job.py
│   ├── flow3_product_ops_job.py
│   ├── math_model_generation_job.py
│   ├── optimization_job.py
│   ├── param_seeding_job.py
│   ├── sync_intake_job.py
│   └── validation_job.py
├── llm
│   ├── __init__.py
│   ├── client.py
│   ├── models.py
│   └── scoring_assistant.py
├── schemas
│   ├── __init__.py
│   ├── feasibility.py
│   ├── initiative.py
│   ├── optimization_center.py
│   ├── optimization_problem.py
│   ├── optimization_solution.py
│   ├── roadmap.py
│   ├── roadmap_entry.py
│   └── scoring.py
├── services
│   ├── optimization
│   │   ├── __init__.py
│   │   ├── feasibility_checker.py
│   │   ├── feasibility_filters.py
│   │   ├── feasibility_persistence.py
│   │   ├── optimization_compiler.py
│   │   ├── optimization_problem_builder.py
│   │   ├── optimization_results_service.py
│   │   ├── optimization_run_persistence.py
│   │   └── optimization_sync_service.py
│   ├── product_ops
│   │   ├── scoring
│   │   │   ├── engines
│   │   │   │   ├── __init__.py
│   │   │   │   ├── math_model.py
│   │   │   │   ├── rice.py
│   │   │   │   └── wsjf.py
│   │   │   ├── __init__.py
│   │   │   ├── interfaces.py
│   │   │   ├── registry.py
│   │   │   └── utils.py
│   │   ├── __init__.py
│   │   ├── kpi_contribution_adapter.py
│   │   ├── kpi_contributions_sync_service.py
│   │   ├── math_model_service.py
│   │   ├── metric_chain_parser.py
│   │   ├── metrics_config_sync_service.py
│   │   ├── params_sync_service.py
│   │   └── scoring_service.py
│   ├── solvers
│   │   ├── __init__.py
│   │   └── ortools_cp_sat_adapter.py
│   ├── __init__.py
│   ├── action_runner.py
│   ├── backlog_mapper.py
│   ├── backlog_service.py
│   ├── initiative_key.py
│   ├── intake_mapper.py
│   ├── intake_service.py
│   └── roadmap_service.py
├── sheets
│   ├── __init__.py
│   ├── backlog_reader.py
│   ├── backlog_writer.py
│   ├── client.py
│   ├── intake_reader.py
│   ├── intake_writer.py
│   ├── kpi_contributions_reader.py
│   ├── kpi_contributions_writer.py
│   ├── math_models_reader.py
│   ├── math_models_writer.py
│   ├── metrics_config_reader.py
│   ├── models.py
│   ├── optimization_candidates_writer.py
│   ├── optimization_center_readers.py
│   ├── optimization_center_writers.py
│   ├── params_reader.py
│   ├── params_writer.py
│   ├── productops_writer.py
│   ├── scoring_inputs_reader.py
│   └── sheet_protection.py
├── utils
│   ├── __init__.py
│   ├── header_utils.py
│   ├── periods.py
│   ├── provenance.py
│   └── safe_eval.py
├── workers
│   ├── __init__.py
│   └── action_worker.py
├── __init__.py
├── config.py
└── main.py
```

### Modules Registry

#### Directory: `app/api/`

##### Module: `__init__.py`
*Path*: `app/api/__init__.py`

*No classes or functions defined*

##### Module: `deps.py`
*Path*: `app/api/deps.py`

**Imports from**: __future__, app.config, app.db.session, fastapi, sqlalchemy.orm

**Functions**:
- **Function `get_db() -> Generator[(Session, None, None)]`**
- **Function `require_shared_secret(x_roadmap_ai_secret: str | None) -> None`**
  - *Doc*: v1 security: shared secret header from Apps Script.

#### Directory: `app/api/routes/`

##### Module: `__init__.py`
*Path*: `app/api/routes/__init__.py`

*No classes or functions defined*

##### Module: `actions.py`
*Path*: `app/api/routes/actions.py`

**Imports from**: __future__, app.api.deps, app.api.schemas.actions, app.db.models.action_run, app.services.action_runner

**Functions**:
- **Function `run_action(req: ActionRunRequest, db: Session) -> ActionRunEnqueueResponse`**
  - *Doc*: Enqueue an action and return run_id immediately.
- **Function `get_run_status(run_id: str, db: Session) -> ActionRunStatusResponse`**
  - *Doc*: Get the status of a specific action run by run_id.

#### Directory: `app/api/schemas/`

##### Module: `__init__.py`
*Path*: `app/api/schemas/__init__.py`

*No classes or functions defined*

##### Module: `actions.py`
*Path*: `app/api/schemas/actions.py`

**Imports from**: __future__, pydantic, typing

**Classes**:
- **Class `ActionRunRequest`** (inherits: BaseModel)
  - *No methods*
- **Class `ActionRunEnqueueResponse`** (inherits: BaseModel)
  - *No methods*
- **Class `ActionRunStatusResponse`** (inherits: BaseModel)
  - *No methods*

#### Directory: `app/` (root)

##### Module: `__init__.py`
*Path*: `app/__init__.py`

*No classes or functions defined*

##### Module: `config.py`
*Path*: `app/config.py`

**Imports from**: dotenv, pathlib, pydantic, pydantic_settings, pythonjsonlogger.json

**Classes**:
- **Class `CustomJsonFormatter`** (inherits: JsonFormatter)
  - *Doc*: Custom JSON formatter that only includes fields with non-None values.
  - `add_fields(self, log_record, record, message_dict)`
- **Class `IntakeTabConfig`** (inherits: BaseModel)
  - *No methods*
- **Class `IntakeSheetConfig`** (inherits: BaseModel)
  - `active_tabs(self)`
- **Class `BacklogSheetConfig`** (inherits: BaseModel)
  - *Doc*: Configuration for a central backlog Google Sheet.
  - *No methods*
- **Class `ProductOpsConfig`** (inherits: BaseModel)
  - *Doc*: Configuration for ProductOps Google Sheet
  - `validate_spreadsheet_id(cls, v: str)`
- **Class `OptimizationCenterConfig`** (inherits: BaseModel)
  - *Doc*: Configuration for Optimization Center Google Sheet
  - `validate_spreadsheet_id(cls, v: str)`
- **Class `Settings`** (inherits: BaseSettings)
  - `load_intake_sheets_from_file(self)`
  - `load_product_ops_from_file(self)`
  - `load_optimization_center_from_file(self)`

**Functions**:
- **Function `setup_json_logging(log_level: int) -> None`**
  - *Doc*: Initialize JSON logging configuration for the application.

##### Module: `main.py`
*Path*: `app/main.py`

**Imports from**: __future__, app.api.routes.actions, app.config, fastapi

**Functions**:
- **Function `create_app() -> FastAPI`**

#### Directory: `app/db/`

##### Module: `__init__.py`
*Path*: `app/db/__init__.py`

*No classes or functions defined*

##### Module: `base.py`
*Path*: `app/db/base.py`

**Imports from**: app.db, sqlalchemy.orm

*No classes or functions defined*

##### Module: `schema_ensure.py`
*Path*: `app/db/schema_ensure.py`

**Imports from**: __future__, sqlalchemy, sqlalchemy.engine

**Functions**:
- **Function `ensure_math_scoring_columns(engine: Engine) -> None`**
  - *Doc*: Ensure math_* and active_scoring_framework columns exist on initiatives.

##### Module: `session.py`
*Path*: `app/db/session.py`

**Imports from**: app.config, sqlalchemy, sqlalchemy.orm

*No classes or functions defined*

#### Directory: `app/db/models/`

##### Module: `__init__.py`
*Path*: `app/db/models/__init__.py`

**Imports from**: action_run, initiative, optimization, roadmap, roadmap_entry

*No classes or functions defined*

##### Module: `action_run.py`
*Path*: `app/db/models/action_run.py`

**Imports from**: __future__, app.db.base, datetime, sqlalchemy

**Classes**:
- **Class `ActionRun`** (inherits: Base)
  - *Doc*: Execution ledger entry for sheet-triggered or system actions.
  - *No methods*

##### Module: `initiative.py`
*Path*: `app/db/models/initiative.py`

**Imports from**: app.db.base, datetime, sqlalchemy, sqlalchemy.orm

**Classes**:
- **Class `Initiative`** (inherits: Base)
  - *No methods*

##### Module: `optimization.py`
*Path*: `app/db/models/optimization.py`

**Imports from**: __future__, app.db.base, datetime, sqlalchemy, sqlalchemy.orm

**Classes**:
- **Class `OrganizationMetricConfig`** (inherits: Base)
  - *Doc*: Authoritative KPI registry from ProductOps Metrics_Config.
  - *No methods*
- **Class `OptimizationScenario`** (inherits: Base)
  - *Doc*: Scenario config for optimization runs.
  - *No methods*
- **Class `OptimizationConstraintSet`** (inherits: Base)
  - *Doc*: Compiled constraints and targets for a scenario.
  - *No methods*
- **Class `OptimizationRun`** (inherits: Base)
  - *Doc*: Execution record for optimization jobs.
  - *No methods*
- **Class `Portfolio`** (inherits: Base)
  - *Doc*: Persisted portfolio results for a scenario/run.
  - *No methods*
- **Class `PortfolioItem`** (inherits: Base)
  - *Doc*: Membership of initiatives in a portfolio.
  - *No methods*

##### Module: `roadmap.py`
*Path*: `app/db/models/roadmap.py`

**Imports from**: app.db.base, datetime, sqlalchemy, sqlalchemy.orm

**Classes**:
- **Class `Roadmap`** (inherits: Base)
  - *No methods*

##### Module: `roadmap_entry.py`
*Path*: `app/db/models/roadmap_entry.py`

**Imports from**: app.db.base, sqlalchemy, sqlalchemy.orm

**Classes**:
- **Class `RoadmapEntry`** (inherits: Base)
  - *Doc*: Link between Roadmap and Initiative, with metadata per roadmap.
  - *No methods*

##### Module: `scoring.py`
*Path*: `app/db/models/scoring.py`

**Imports from**: app.db.base, datetime, sqlalchemy, sqlalchemy.orm

**Classes**:
- **Class `InitiativeMathModel`** (inherits: Base)
  - *Doc*: Stores mathematical models for initiatives.
  - *No methods*
- **Class `InitiativeScore`** (inherits: Base)
  - *Doc*: Optional scoring history table (per framework / per run).
  - *No methods*
- **Class `InitiativeParam`** (inherits: Base)
  - *Doc*: Normalized parameter table: one row per (initiative, framework, param_name).
  - *No methods*

#### Directory: `app/jobs/`

##### Module: `__init__.py`
*Path*: `app/jobs/__init__.py`

*No classes or functions defined*

##### Module: `backlog_sync_job.py`
*Path*: `app/jobs/backlog_sync_job.py`

**Imports from**: __future__, app.config, app.sheets.backlog_writer, app.sheets.client, sqlalchemy.orm

**Functions**:
- **Function `_resolve_backlog_target(spreadsheet_id: Optional[str], tab_name: Optional[str], product_org: Optional[str]) -> BacklogSheetConfig`**
  - *Doc*: Pick a backlog sheet config based on overrides or settings.
- **Function `run_backlog_sync(db: Session, spreadsheet_id: str | None, tab_name: str | None, product_org: str | None) -> None`**
  - *Doc*: Regenerate a backlog Google Sheet from DB Initiatives.
- **Function `run_all_backlog_sync(db: Session) -> None`**
  - *Doc*: Regenerate all configured backlog sheets (multi-org scenario).

##### Module: `backlog_update_job.py`
*Path*: `app/jobs/backlog_update_job.py`

**Imports from**: __future__, app.config, app.services.backlog_service, app.sheets.backlog_reader, app.sheets.client

**Functions**:
- **Function `_resolve_backlog_target(spreadsheet_id: Optional[str], tab_name: Optional[str], product_org: Optional[str]) -> BacklogSheetConfig`**
  - *Doc*: Pick a backlog sheet config based on overrides or settings.
- **Function `run_backlog_update(db: Session, spreadsheet_id: str | None, tab_name: str | None, product_org: str | None, commit_every: int | None, initiative_keys: list[str] | None) -> int`**
  - *Doc*: Read central backlog and apply updates into DB.

##### Module: `flow1_full_sync_job.py`
*Path*: `app/jobs/flow1_full_sync_job.py`

*Doc*: Flow 1 is the end-to-end sync cycle for departmental intake sheets feeding into a central backlog sheet.

**Imports from**: __future__, app.jobs.backlog_sync_job, app.jobs.backlog_update_job, app.jobs.sync_intake_job, sqlalchemy.orm

**Classes**:
- **Class `Flow1SyncResult`** (inherits: TypedDict)
  - *Doc*: Result of Flow 1 full sync execution.
  - *No methods*

**Functions**:
- **Function `run_flow1_full_sync(db: Session) -> Flow1SyncResult`**
  - *Doc*: Run the full Flow 1 cycle.

##### Module: `flow2_scoring_activation_job.py`
*Path*: `app/jobs/flow2_scoring_activation_job.py`

*Doc*: Flow 2 Scoring Activation Job

**Imports from**: __future__, app.services.product_ops.scoring, app.services.product_ops.scoring_service, sqlalchemy.orm, typing

**Functions**:
- **Function `run_scoring_batch(db: Session) -> int`**
  - *Doc*: Run an activation batch for the given framework.

##### Module: `flow3_product_ops_job.py`
*Path*: `app/jobs/flow3_product_ops_job.py`

**Imports from**: __future__, app.config, app.db.models.initiative, app.sheets.client, app.sheets.productops_writer

**Classes**:
- **Class `ScoringInputsFormatter`** (inherits: logging.Formatter)
  - *Doc*: Custom formatter that includes scoring-specific fields when present.
  - `format(self, record: logging.LogRecord)`

**Functions**:
- **Function `_get_product_ops_reader(spreadsheet_id: Optional[str], tab_name: Optional[str]) -> ScoringInputsReader`**
- **Function `run_flow3_preview_inputs() -> List[ScoringInputsRow]`**
  - *Doc*: Fetch and parse the Product Ops Scoring_Inputs tab; return parsed rows for inspection.
- **Function `run_flow3_sync_inputs_to_initiatives(db: Session) -> int`**
  - *Doc*: Strong sync: write Scoring_Inputs values into Initiative fields.
- **Function `run_flow3_write_scores_to_sheet(db: Session) -> int`**
  - *Doc*: Flow 3.C Phase 2: Write per-framework scores from DB back to Product Ops sheet.

##### Module: `math_model_generation_job.py`
*Path*: `app/jobs/math_model_generation_job.py`

**Imports from**: __future__, app.db.models.initiative, app.llm.client, app.llm.scoring_assistant, app.sheets.client

**Functions**:
- **Function `needs_suggestion(row: object, force: bool) -> bool`**
- **Function `run_math_model_generation_job(db: Session, sheets_client: SheetsClient, llm_client: LLMClient, spreadsheet_id: str, tab_name: str, max_rows: Optional[int], force: bool, max_llm_calls: int) -> Dict[(str, int)]`**

##### Module: `optimization_job.py`
*Path*: `app/jobs/optimization_job.py`

*Doc*: Flow 5 (Phase 5) - Optimization run orchestration.

**Imports from**: __future__, app.config, app.schemas.feasibility, app.schemas.optimization_solution, app.services.optimization

**Functions**:
- **Function `run_flow5_optimization() -> Dict[(str, Any)]`**
  - *Doc*: Flow 5 (Phase 5) - Complete optimization run orchestration.
- **Function `_publish_results_to_sheets() -> None`**
  - *Doc*: Publish optimization results to Optimization Center sheet.

##### Module: `param_seeding_job.py`
*Path*: `app/jobs/param_seeding_job.py`

*Doc*: Job to seed Params sheet from approved MathModels formulas.

**Imports from**: __future__, app.config, app.llm.client, app.llm.scoring_assistant, app.sheets.client

**Classes**:
- **Class `ParamSeedingStats`**
  - *Doc*: Statistics for param seeding job run.
  - `__init__(self)`
  - `summary(self)`

**Functions**:
- **Function `run_param_seeding_job(sheets_client: SheetsClient, spreadsheet_id: str, mathmodels_tab: str, params_tab: str, llm_client: LLMClient, max_llm_calls: int, limit: int | None) -> ParamSeedingStats`**
  - *Doc*: Seed Params sheet from approved MathModels.

##### Module: `sync_intake_job.py`
*Path*: `app/jobs/sync_intake_job.py`

**Imports from**: __future__, app.config, app.services.intake_service, app.sheets.client, app.sheets.intake_reader

**Functions**:
- **Function `run_sync_for_sheet(db: Session, spreadsheet_id: str, tab_name: str, sheets_service, allow_status_override: bool, commit_every: Optional[int], header_row: int, start_data_row: int, max_rows: Optional[int]) -> None`**
  - *Doc*: Run intake sync for one sheet tab end-to-end.
- **Function `run_sync_all_intake_sheets(db: Session, allow_status_override_global: bool) -> None`**
  - *Doc*: Run intake sync for all configured hierarchical sheets / tabs.

##### Module: `validation_job.py`
*Path*: `app/jobs/validation_job.py`

*No classes or functions defined*

#### Directory: `app/llm/`

##### Module: `__init__.py`
*Path*: `app/llm/__init__.py`

*No classes or functions defined*

##### Module: `client.py`
*Path*: `app/llm/client.py`

**Imports from**: __future__, app.config, app.db.models.optimization, app.llm.models, app.services.product_ops.metric_chain_parser

**Classes**:
- **Class `LLMClient`**
  - *Doc*: Thin wrapper around OpenAI client for math-model suggestions.
  - `__init__(self, client: Optional[OpenAI], db: Optional[Session])`
  - `suggest_math_model(self, payload: MathModelPromptInput)`
  - `suggest_param_metadata(self, initiative_key: str, identifiers: list[str], formula_text: str)`

**Functions**:
- **Function `_build_system_prompt() -> str`**
- **Function `_build_user_prompt(payload: MathModelPromptInput, db: Optional[Session]) -> str`**

##### Module: `models.py`
*Path*: `app/llm/models.py`

**Imports from**: __future__, pydantic, typing

**Classes**:
- **Class `MathModelPromptInput`** (inherits: BaseModel)
  - *No methods*
- **Class `MathModelSuggestion`** (inherits: BaseModel)
  - *Doc*: LLM response for math-model suggestions.
  - `formula_text(self)`
  - `metric_chain_text(self)`
  - `notes(self)`
- **Class `ParamSuggestion`** (inherits: BaseModel)
  - `_coerce_example_value(self)`
- **Class `ParamMetadataSuggestion`** (inherits: BaseModel)
  - *No methods*

##### Module: `scoring_assistant.py`
*Path*: `app/llm/scoring_assistant.py`

**Imports from**: __future__, app.db.models.initiative, app.llm.client, app.llm.models, app.sheets.models

**Functions**:
- **Function `suggest_math_model_for_initiative(initiative: Initiative, row: MathModelRow, llm: LLMClient) -> MathModelSuggestion`**
  - *Doc*: Construct prompt input from Initiative + MathModelRow and call LLM.
- **Function `suggest_param_metadata_for_model(initiative_key: str, identifiers: list[str], formula_text: str, llm: LLMClient) -> ParamMetadataSuggestion`**
  - *Doc*: Call LLM to suggest param metadata for formula identifiers.

#### Directory: `app/schemas/`

##### Module: `__init__.py`
*Path*: `app/schemas/__init__.py`

**Imports from**: initiative, optimization_center, roadmap, roadmap_entry, scoring

*No classes or functions defined*

##### Module: `feasibility.py`
*Path*: `app/schemas/feasibility.py`

*Doc*: Feasibility report schemas for pre-solver validation.

**Imports from**: __future__, pydantic, typing

**Classes**:
- **Class `FeasibilityIssue`** (inherits: BaseModel)
  - *Doc*: A single feasibility issue (error or warning).
  - *No methods*
- **Class `FeasibilityReport`** (inherits: BaseModel)
  - *Doc*: Structured feasibility check report.
  - `from_issues(cls, issues: List[FeasibilityIssue])`

##### Module: `initiative.py`
*Path*: `app/schemas/initiative.py`

**Imports from**: datetime, pydantic, typing

**Classes**:
- **Class `InitiativeBase`** (inherits: BaseModel)
  - *No methods*
- **Class `InitiativeCreate`** (inherits: InitiativeBase)
  - *No methods*
- **Class `InitiativeUpdate`** (inherits: BaseModel)
  - *No methods*
- **Class `InitiativeRead`** (inherits: InitiativeBase)
  - *No methods*

##### Module: `optimization_center.py`
*Path*: `app/schemas/optimization_center.py`

*Doc*: Pydantic schemas + validation helpers for Optimization Center sheets.

**Imports from**: __future__, pydantic, typing, typing_extensions

**Classes**:
- **Class `ValidationMessage`** (inherits: BaseModel)
  - *No methods*
- **Class `ScenarioConfigSchema`** (inherits: BaseModel)
  - `to_float(cls, v)`
  - `validate_weights(cls, v)`
- **Class `ConstraintRowBase`** (inherits: BaseModel)
  - `not_blank(cls, v: str)`
  - `to_float(cls, v)`
  - `non_negative(cls, v)`
  - `normalize_type(cls, v: str)`
  - `normalize_dimension(cls, v: str)`
  - `normalize_constraint_set(cls, v: str)`
  - `normalize_dimension_key(cls, v: Optional[str])`
  - `forbid_special_keys_for_wrong_types(self)`
- **Class `CapacityFloorRowSchema`** (inherits: ConstraintRowBase)
  - `validate_capacity_floor(self)`
- **Class `CapacityCapRowSchema`** (inherits: ConstraintRowBase)
  - `validate_capacity_cap(self)`
- **Class `MandatoryRowSchema`** (inherits: ConstraintRowBase)
  - `validate_mandatory(self)`
- **Class `BundleRowSchema`** (inherits: ConstraintRowBase)
  - `validate_bundle(self)`
- **Class `ExcludePairRowSchema`** (inherits: ConstraintRowBase)
  - `validate_exclude_pair(self)`
- **Class `ExcludeInitiativeRowSchema`** (inherits: ConstraintRowBase)
  - `validate_exclude(self)`
- **Class `RequirePrereqRowSchema`** (inherits: ConstraintRowBase)
  - `validate_prereq(self)`
- **Class `SynergyBonusRowSchema`** (inherits: ConstraintRowBase)
  - `validate_synergy(self)`
- **Class `TargetRowSchema`** (inherits: BaseModel)
  - `not_blank(cls, v: str)`
  - `normalize_dimension(cls, v: Optional[str])`
  - `normalize_dimension_key(cls, v: Optional[str])`
  - `require_value_and_goal(self)`
  - `to_float(cls, v)`
  - `non_negative(cls, v)`
  - `validate_floor_goal(cls, v: Optional[str])`
- **Class `ConstraintSetCompiled`** (inherits: BaseModel)
  - *Doc*: Compiled, system-generated representation of a constraint set (not a sheet row).
  - *No methods*
- **Class `BundleCompiled`** (inherits: BaseModel)
  - *No methods*
- **Class `CapacityFloor`** (inherits: BaseModel)
  - *No methods*
- **Class `CapacityCap`** (inherits: BaseModel)
  - *No methods*
- **Class `TargetConstraint`** (inherits: BaseModel)
  - *No methods*

**Functions**:
- **Function `validate_constraint_row(row_num: int, data: dict) -> ValidationMessage`**
- **Function `validate_target_row(row_num: int, data: dict, valid_kpis: Optional[set[str]]) -> ValidationMessage`**
- **Function `validate_scenario_config(row_num: int, data: dict, allowed_objective_modes: Optional[set[str]], weights_required_modes: Optional[set[str]]) -> ValidationMessage`**

##### Module: `optimization_problem.py`
*Path*: `app/schemas/optimization_problem.py`

*Doc*: Frozen solver-facing problem schema (Phase 5).

**Imports from**: __future__, pydantic, typing

**Classes**:
- **Class `ObjectiveSpec`** (inherits: BaseModel)
  - *Doc*: Defines the optimization objective function configuration.
  - `_validate_objective(self)`
- **Class `Candidate`** (inherits: BaseModel)
  - *Doc*: A single initiative candidate for optimization.
  - *No methods*
- **Class `ConstraintSetPayload`** (inherits: BaseModel)
  - *Doc*: Compiled constraint set JSON payload (matches DB structure).
  - *No methods*
- **Class `RunScope`** (inherits: BaseModel)
  - *Doc*: Defines how the candidate pool was selected.
  - `_validate_scope(self)`
- **Class `OptimizationProblem`** (inherits: BaseModel)
  - *Doc*: Complete solver-facing problem object (Phase 5).
  - *No methods*

##### Module: `optimization_solution.py`
*Path*: `app/schemas/optimization_solution.py`

*Doc*: Optimization solution schemas for solver output.

**Imports from**: __future__, pydantic, typing, typing_extensions

**Classes**:
- **Class `SelectedItem`** (inherits: BaseModel)
  - *Doc*: A single candidate's selection status and allocated resources.
  - *No methods*
- **Class `OptimizationSolution`** (inherits: BaseModel)
  - *Doc*: Structured solver output.
  - *No methods*

##### Module: `roadmap.py`
*Path*: `app/schemas/roadmap.py`

**Imports from**: datetime, pydantic, typing

**Classes**:
- **Class `RoadmapBase`** (inherits: BaseModel)
  - *No methods*
- **Class `RoadmapCreate`** (inherits: RoadmapBase)
  - *No methods*
- **Class `RoadmapRead`** (inherits: RoadmapBase)
  - *No methods*

##### Module: `roadmap_entry.py`
*Path*: `app/schemas/roadmap_entry.py`

**Imports from**: pydantic, typing

**Classes**:
- **Class `RoadmapEntryBase`** (inherits: BaseModel)
  - *No methods*
- **Class `RoadmapEntryCreate`** (inherits: RoadmapEntryBase)
  - *No methods*
- **Class `RoadmapEntryRead`** (inherits: RoadmapEntryBase)
  - *No methods*

##### Module: `scoring.py`
*Path*: `app/schemas/scoring.py`

**Imports from**: datetime, pydantic, typing

**Classes**:
- **Class `InitiativeMathModelRead`** (inherits: BaseModel)
  - *No methods*
- **Class `InitiativeParamRead`** (inherits: BaseModel)
  - *No methods*
- **Class `InitiativeMathModelBase`** (inherits: BaseModel)
  - *No methods*
- **Class `InitiativeScoreRead`** (inherits: BaseModel)
  - *No methods*

#### Directory: `app/services/`

##### Module: `__init__.py`
*Path*: `app/services/__init__.py`

*No classes or functions defined*

##### Module: `action_runner.py`
*Path*: `app/services/action_runner.py`

*Doc*: Action runner service for enqueuing and executing sheet-triggered actions.

**Imports from**: __future__, app.config, app.db.models.action_run, app.jobs.backlog_sync_job, app.jobs.backlog_update_job

**Classes**:
- **Class `ActionContext`**
  - *Doc*: Convenience wrapper around payload and resolved runtime dependencies.
  - *No methods*

**Functions**:
- **Function `_now() -> datetime`**
- **Function `_make_run_id() -> str`**
- **Function `enqueue_action_run(db: Session, payload: Dict[(str, Any)]) -> ActionRun`**
  - *Doc*: Create an ActionRun row with status=queued and return the ORM object.
- **Function `_build_scope_summary(scope: Any) -> Optional[str]`**
  - *Doc*: Short human-friendly text for UI display (action runs table, Apps Script response).
- **Function `_extract_summary(action: str, result: Dict[(str, Any)]) -> Dict[(str, Any)]`**
  - *Doc*: Extract standardized summary from action-specific result for UI display.
- **Function `execute_next_queued_run(db: Session) -> Optional[ActionRun]`**
  - *Doc*: Atomically claim one queued ActionRun, execute it, update status/result.
- **Function `_claim_one_queued(db: Session) -> Optional[ActionRun]`**
  - *Doc*: Claim one queued action run.
- **Function `_build_action_context(payload: Dict[(str, Any)]) -> ActionContext`**
  - *Doc*: Build execution context with lazy dependency resolution.
- **Function `_resolve_action(action: str) -> ActionFn`**
- **Function `_action_flow3_compute_all(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow3_write_scores(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow3_sync_inputs(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow2_activate(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow1_backlog_sync(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow1_full_sync(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow4_suggest_mathmodels(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow4_seed_params(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow4_sync_mathmodels(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow4_sync_params(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_flow0_intake_sync(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
- **Function `_action_pm_backlog_sync(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
  - *Doc*: PM Job #1: Sync intake to backlog.
- **Function `_action_pm_score_selected(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
  - *Doc*: PM Job #2: Score selected initiatives.
- **Function `_action_pm_suggest_math_model_llm(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
  - *Doc*: PM Job #4a: Suggest math model formulas via LLM.
- **Function `_action_pm_seed_math_params(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
  - *Doc*: PM Job #5: Seed math model parameters from approved formulas.
- **Function `_action_pm_switch_framework(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
  - *Doc*: PM Job #3: Switch active scoring framework for selected initiatives.
- **Function `_action_pm_save_selected(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
  - *Doc*: PM Job #4: Save selected rows from current tab into DB (selection-scoped).
- **Function `_action_pm_populate_candidates(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
  - *Doc*: PM Job: Populate Optimization Candidates tab from DB (KPI contributions, constraints, status).
- **Function `_action_pm_optimize_run_selected_candidates(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
  - *Doc*: PM Job: Run optimization (Step 1+2+3 solver) on user-selected candidates.
- **Function `_action_pm_optimize_run_all_candidates(db: Session, ctx: ActionContext) -> Dict[(str, Any)]`**
  - *Doc*: PM Job: Run optimization (Step 1 capacity-only solver) on all candidates in scenario.

##### Module: `backlog_mapper.py`
*Path*: `app/services/backlog_mapper.py`

**Imports from**: __future__, app.sheets.backlog_reader, typing

**Functions**:
- **Function `_to_float(value: Any) -> Optional[float]`**
- **Function `_to_bool(value: Any) -> bool`**
- **Function `_split_keys(value: Any) -> List[str]`**
- **Function `backlog_row_to_update_data(row: BacklogRow) -> Dict[(str, Any)]`**
  - *Doc*: Map central backlog sheet columns to Initiative fields.

##### Module: `backlog_service.py`
*Path*: `app/services/backlog_service.py`

**Imports from**: __future__, app.config, app.db.models.initiative, app.sheets.backlog_reader, app.sheets.models

**Classes**:
- **Class `BacklogService`**
  - *Doc*: Updates Initiatives in the database based on edits in the central backlog sheet.
  - `__init__(self, db: Session)`
  - `update_from_backlog_row(self, row: BacklogRow)`
  - `_extract_initiative_key(row: BacklogRow)`
  - `update_many(self, rows: List[BacklogRow] | List[tuple[int, BacklogRow]], commit_every: Optional[int])`
  - `_apply_central_update(initiative: Initiative, data: Dict[(str, Any)])`

##### Module: `initiative_key.py`
*Path*: `app/services/initiative_key.py`

*Doc*: Generate unique initiative keys.

**Imports from**: __future__, app.db.models.initiative, sqlalchemy.orm

**Functions**:
- **Function `generate_initiative_key(db: Session) -> str`**
  - *Doc*: Generate a new unique initiative_key.

##### Module: `intake_mapper.py`
*Path*: `app/services/intake_mapper.py`

*Doc*: Map a single intake sheet row (dict of column -> value) to InitiativeCreate.

**Imports from**: __future__, app.schemas.initiative, datetime, typing

**Functions**:
- **Function `_to_float(value: Any) -> Optional[float]`**
  - *Doc*: Convert a cell value to float if possible, otherwise return None.
- **Function `_to_bool(value: Any) -> bool`**
  - *Doc*: Convert a cell value to bool using common truthy values.
- **Function `_to_date(value: Any) -> Any`**
  - *Doc*: Convert a cell value to date if possible, otherwise return None.
- **Function `map_sheet_row_to_initiative_create(row: Dict[(str, Any)]) -> InitiativeCreate`**
  - *Doc*: Map a single Google Sheets intake row (column_name -> value)

##### Module: `intake_service.py`
*Path*: `app/services/intake_service.py`

*Doc*: IntakeService implementation (Flow 1 - Step 2).

**Imports from**: __future__, app.config, app.db.models.initiative, app.schemas.initiative, app.services.initiative_key

**Classes**:
- **Class `InitiativeKeyWriter`** (inherits: Protocol)
  - `write_initiative_key(self, sheet_id: str, tab_name: str, row_number: int, initiative_key: str)`
- **Class `IntakeService`**
  - `__init__(self, db: Session, key_writer: Optional[InitiativeKeyWriter])`
  - `_queue_key_backfill(self, sheet_id: str, tab_name: str, row_number: int, initiative: Initiative)`
  - `upsert_from_intake_row(self, row: IntakeRow, source_sheet_id: str, source_tab_name: str, source_row_number: int, allow_status_override: bool, auto_commit: bool)`
  - `upsert_many(self, rows: list[IntakeRow], source_sheet_id: str, source_tab_name: str, start_row_number: int, commit_every: Optional[int], allow_status_override: bool)`
  - `_find_existing_initiative(self, row: IntakeRow, source_sheet_id: str, source_tab_name: str, source_row_number: int)`
  - `_extract_initiative_key(row: IntakeRow)`
  - `_create_from_intake(self, dto: InitiativeCreate, source_sheet_id: str, source_tab_name: str, source_row_number: int)`
  - `_apply_intake_update(self, initiative: Initiative, dto: InitiativeCreate, allow_status_override: bool)`
  - `_backfill_initiative_key(self, sheet_id: str, tab_name: str, row_number: int, initiative_key: str)`
  - `flush_pending_key_backfills(self)`

##### Module: `roadmap_service.py`
*Path*: `app/services/roadmap_service.py`

*No classes or functions defined*

#### Directory: `app/services/optimization/`

##### Module: `__init__.py`
*Path*: `app/services/optimization/__init__.py`

*Doc*: Optimization-related services (compiler, problem builder, feasibility, persistence).

*No classes or functions defined*

##### Module: `feasibility_checker.py`
*Path*: `app/services/optimization/feasibility_checker.py`

*Doc*: Fast, deterministic feasibility checks BEFORE calling the solver.

**Imports from**: __future__, app.schemas.feasibility, app.schemas.optimization_problem, dataclasses, datetime

**Classes**:
- **Class `PeriodWindow`**
  - *Doc*: Time period with start and end dates (for future time-aware checks).
  - *No methods*
- **Class `FeasibilityChecker`**
  - *Doc*: Fast, deterministic feasibility checks BEFORE calling the solver.
  - `check(self, problem: OptimizationProblem, period_window: Optional[PeriodWindow])`
  - `_check_candidate_tokens(self, problem: OptimizationProblem)`
  - `_check_mandatory_references(self, problem: OptimizationProblem, candidate_keys: Set[str])`
  - `_check_exclusions(self, problem: OptimizationProblem, candidate_keys: Set[str])`
  - `_check_bundles(self, problem: OptimizationProblem, candidate_keys: Set[str])`
  - `_check_prerequisites(self, problem: OptimizationProblem, candidate_keys: Set[str])`
  - `_check_synergy_pairs(self, problem: OptimizationProblem, candidate_keys: Set[str])`
  - `_check_capacity_bounds(self, problem: OptimizationProblem, candidate_keys: Set[str])`
  - `_compute_slice_token_totals(self, problem: OptimizationProblem)`
  - `_check_target_floors_upper_bound(self, problem: OptimizationProblem)`
  - `_compute_optimistic_kpi_totals(self, problem: OptimizationProblem)`
  - `_detect_prereq_cycles(self, prereqs: Dict[(str, List[str])])`

##### Module: `feasibility_filters.py`
*Path*: `app/services/optimization/feasibility_filters.py`

*Doc*: Pre-solver feasibility filters for candidate initiatives.

**Imports from**: __future__, app.db.models.initiative, datetime

**Functions**:
- **Function `is_deadline_feasible(initiative: Initiative, period_end: date) -> bool`**
  - *Doc*: Check if an initiative's deadline is feasible for a given period.
- **Function `is_time_feasible(initiative: Initiative, period_start: date, period_end: date) -> bool`**
  - *Doc*: Extended time feasibility check (for future phases).

##### Module: `feasibility_persistence.py`
*Path*: `app/services/optimization/feasibility_persistence.py`

*Doc*: Feasibility report persistence utilities.

**Imports from**: __future__, datetime, typing

**Functions**:
- **Function `persist_feasibility_report(db: 'Session', optimization_run: 'OptimizationRun', report: 'FeasibilityReport') -> 'OptimizationRun'`**
  - *Doc*: Persist feasibility output to OptimizationRun.result_json under a stable key.

##### Module: `optimization_compiler.py`
*Path*: `app/services/optimization/optimization_compiler.py`

*Doc*: Pure compilation logic for Optimization Center constraints.

**Imports from**: __future__, app.schemas.optimization_center, pydantic, typing

**Functions**:
- **Function `_bucket(compiled: Dict[(Tuple[(str, str)], ConstraintSetCompiled)], scenario: str, cset: str) -> ConstraintSetCompiled`**
- **Function `compile_constraint_sets(constraint_rows: List[Tuple[(int, Dict[(str, Any)])]], target_rows: List[Tuple[(int, Dict[(str, Any)])]], valid_kpis: Optional[set[str]]) -> Tuple[(Dict[(Tuple[(str, str)], ConstraintSetCompiled)], List[ValidationMessage])]`**
  - *Doc*: Validate and compile sheet rows into grouped ConstraintSetCompiled objects.

##### Module: `optimization_problem_builder.py`
*Path*: `app/services/optimization/optimization_problem_builder.py`

*Doc*: Builder service for OptimizationProblem objects.

**Imports from**: __future__, app.db.models.initiative, app.db.models.optimization, app.schemas.optimization_problem, app.services.optimization.feasibility_filters

**Functions**:
- **Function `_resolve_active_north_star_kpi_key(db: Session) -> str`**
  - *Doc*: Resolve the single active North Star KPI key from OrganizationMetricConfig.
- **Function `build_optimization_problem(db: Session, scenario_name: str, constraint_set_name: str, scope_type: ScopeType, selected_initiative_keys: Optional[List[str]], period_end_date: Optional[date]) -> OptimizationProblem`**
  - *Doc*: Build a complete OptimizationProblem ready for solver.
- **Function `_validate_governance_references(constraint_payload: ConstraintSetPayload, candidate_keys: set[str]) -> None`**
  - *Doc*: Validate that all governance constraint references

##### Module: `optimization_results_service.py`
*Path*: `app/services/optimization/optimization_results_service.py`

*Doc*: Pure computation service for optimization results artifacts.

**Imports from**: __future__, app.db.models.optimization, app.schemas.optimization_problem, app.schemas.optimization_solution, datetime

**Functions**:
- **Function `build_runs_row() -> Dict[(str, Any)]`**
  - *Doc*: Build single row dict for Runs tab (one row per optimization run).
- **Function `build_results_rows() -> List[Dict[(str, Any)]]`**
  - *Doc*: Build N rows for Results tab (one per candidate in problem).
- **Function `build_gaps_rows() -> List[Dict[(str, Any)]]`**
  - *Doc*: Build M rows for Gaps_and_Alerts tab (one per target constraint).
- **Function `_compute_objective_contribution() -> float`**
  - *Doc*: Recompute objective contribution for a candidate (deterministic).
- **Function `_compute_achieved_contribution() -> float`**
  - *Doc*: Sum KPI contributions over selected candidates matching dimension slice.
- **Function `_compute_severity(gap: float, target: float) -> str`**
  - *Doc*: Compute severity level based on gap and target.
- **Function `_build_gap_summary(problem: OptimizationProblem, solution: OptimizationSolution) -> str`**
  - *Doc*: Build short gap summary string for Runs tab.

##### Module: `optimization_run_persistence.py`
*Path*: `app/services/optimization/optimization_run_persistence.py`

*Doc*: Persistence utilities for OptimizationRun objects.

**Imports from**: __future__, app.db.models.optimization, app.schemas.optimization_problem, datetime, sqlalchemy.orm

**Functions**:
- **Function `persist_inputs_snapshot(db: Session, optimization_run: OptimizationRun, problem: OptimizationProblem, extra_snapshot_metadata: Optional[Dict[(str, Any)]]) -> OptimizationRun`**
  - *Doc*: Store the exact solver input into OptimizationRun.inputs_snapshot_json for reproducibility.
- **Function `persist_result(db: Session, optimization_run: OptimizationRun, result_json: Dict[(str, Any)], status: str, error_text: Optional[str]) -> OptimizationRun`**
  - *Doc*: Store solver result into OptimizationRun.result_json.
- **Function `create_run_record(db: Session, run_id: str, scenario_id: int, constraint_set_id: int, solver_name: Optional[str], solver_version: Optional[str], status: str, requested_by_email: Optional[str], requested_by_ui: Optional[str]) -> OptimizationRun`**
  - *Doc*: Create a new OptimizationRun record in the database.

##### Module: `optimization_sync_service.py`
*Path*: `app/services/optimization/optimization_sync_service.py`

*Doc*: Optimization Center sync orchestration.

**Imports from**: __future__, app.db.models.initiative, app.db.models.optimization, app.db.session, app.schemas.optimization_center

**Functions**:
- **Function `_capacity_to_json(items: Sequence[CapacityFloor | CapacityCap], value_attr: str) -> Dict[(str, Dict[(str, float)])]`**
- **Function `_targets_to_json(targets: List[TargetConstraint]) -> Dict[(str, Dict[(str, Dict[(str, Any)])])]`**
  - *Doc*: Convert targets to JSON structure: {dimension: {dimension_key: {kpi_key: {type, value, notes?}}}}
- **Function `sync_constraint_sets_from_sheets(sheets_client: SheetsClient, spreadsheet_id: str, constraints_tab: str, targets_tab: str, session: Optional[Session]) -> Tuple[(List[OptimizationConstraintSet], List[ValidationMessage])]`**
  - *Doc*: Read constraints/targets tabs, compile, and upsert OptimizationConstraintSet rows.
- **Function `sync_candidates_from_sheet(sheets_client: SheetsClient, spreadsheet_id: str, candidates_tab: str, initiative_keys: Optional[List[str]], commit_every: int, session: Optional[Session]) -> Dict[(str, Any)]`**
  - *Doc*: Sync Optimization Candidates tab editable fields to Initiative DB records.

#### Directory: `app/services/product_ops/`

##### Module: `__init__.py`
*Path*: `app/services/product_ops/__init__.py`

*Doc*: ProductOps-related services (scoring, sync, adapters).

*No classes or functions defined*

##### Module: `kpi_contribution_adapter.py`
*Path*: `app/services/product_ops/kpi_contribution_adapter.py`

*Doc*: KPI Contributions Adapter

**Imports from**: __future__, app.db.models.initiative, app.db.models.optimization, sqlalchemy.orm, typing

**Functions**:
- **Function `compute_kpi_contributions(initiative: Initiative) -> Dict[(str, float)]`**
  - *Doc*: Compute KPI contributions from initiative's math models.
- **Function `update_initiative_contributions(db: Session, initiative: Initiative, commit: bool) -> Dict[(str, Any)]`**
  - *Doc*: Update initiative's KPI contributions from its math models.
- **Function `get_representative_score(initiative: Initiative) -> Optional[float]`**
  - *Doc*: Get representative score for initiative from its math models.
- **Function `validate_kpi_keys(db: Session, kpi_keys: list[str], kpi_levels: Optional[list[str]]) -> Dict[(str, Any)]`**
  - *Doc*: Validate KPI keys against OrganizationMetricConfig.

##### Module: `kpi_contributions_sync_service.py`
*Path*: `app/services/product_ops/kpi_contributions_sync_service.py`

**Imports from**: __future__, app.db.models.initiative, app.db.models.optimization, app.sheets.client, app.sheets.kpi_contributions_reader

**Classes**:
- **Class `KPIContributionsSyncService`**
  - *Doc*: Sheet → DB sync for ProductOps KPI_Contributions tab.
  - `__init__(self, client: SheetsClient)`
  - `preview_rows(self, spreadsheet_id: str, tab_name: str, max_rows: Optional[int])`
  - `sync_sheet_to_db(self, db: Session, spreadsheet_id: str, tab_name: str, commit_every: int, initiative_keys: Optional[List[str]])`
  - `_load_allowed_kpis(self, db: Session)`
  - `_normalize_contribution(self, raw: Any)`
  - `_values_are_numeric(self, contrib: Dict[(str, float)])`

##### Module: `math_model_service.py`
*Path*: `app/services/product_ops/math_model_service.py`

**Imports from**: __future__, app.db.models.initiative, app.db.models.scoring, app.services.product_ops.metric_chain_parser, app.sheets.client

**Classes**:
- **Class `MathModelSyncService`**
  - *Doc*: Sheet ↔ DB sync for MathModels (Sheet → DB for Step 4).
  - `__init__(self, client: SheetsClient)`
  - `preview_rows(self, spreadsheet_id: str, tab_name: str, max_rows: Optional[int])`
  - `sync_sheet_to_db(self, db: Session, spreadsheet_id: str, tab_name: str, commit_every: int, initiative_keys: Optional[List[str]])`

##### Module: `metric_chain_parser.py`
*Path*: `app/services/product_ops/metric_chain_parser.py`

*Doc*: Metric Chain Parser (Token Extractor)

**Imports from**: __future__, app.db.models.optimization, sqlalchemy.orm, typing

**Functions**:
- **Function `parse_metric_chain(text: Optional[str]) -> Optional[Dict[(str, Any)]]`**
  - *Doc*: Parse metric chain text into structured JSON.
- **Function `validate_metric_chain(db: Session, metric_chain_json: Dict[(str, Any)], kpi_levels: Optional[List[str]]) -> Dict[(str, Any)]`**
  - *Doc*: Validate metric chain keys against OrganizationMetricConfig.
- **Function `parse_and_validate(db: Session, text: Optional[str], kpi_levels: Optional[List[str]]) -> Optional[Dict[(str, Any)]]`**
  - *Doc*: Parse and validate metric chain in one step.
- **Function `format_chain_for_llm(metric_chain_json: Optional[Dict[(str, Any)]], kpi_configs: Optional[List[Dict[(str, Any)]]]) -> str`**
  - *Doc*: Format metric chain for LLM prompt context.

##### Module: `metrics_config_sync_service.py`
*Path*: `app/services/product_ops/metrics_config_sync_service.py`

**Imports from**: __future__, app.db.models.optimization, app.sheets.client, app.sheets.metrics_config_reader, sqlalchemy.orm

**Classes**:
- **Class `MetricsConfigSyncService`**
  - *Doc*: Sheet → DB sync for ProductOps Metrics_Config tab.
  - `__init__(self, client: SheetsClient)`
  - `preview_rows(self, spreadsheet_id: str, tab_name: str, max_rows: Optional[int])`
  - `sync_sheet_to_db(self, db: Session, spreadsheet_id: str, tab_name: str, commit_every: int, kpi_keys: Optional[List[str]])`
  - `_validate_unique_keys(self, rows: List[MetricRowPair])`
  - `_validate_active_north_star(self, rows: List[MetricRowPair])`

##### Module: `params_sync_service.py`
*Path*: `app/services/product_ops/params_sync_service.py`

**Imports from**: __future__, app.db.models.initiative, app.db.models.scoring, app.sheets.client, app.sheets.params_reader

**Classes**:
- **Class `ParamsSyncService`**
  - *Doc*: Sheet → DB sync for Initiative Parameters (Step 4).
  - `__init__(self, client: SheetsClient)`
  - `preview_rows(self, spreadsheet_id: str, tab_name: str, max_rows: Optional[int])`
  - `sync_sheet_to_db(self, db: Session, spreadsheet_id: str, tab_name: str, commit_every: int, initiative_keys: Optional[List[str]])`

##### Module: `scoring_service.py`
*Path*: `app/services/product_ops/scoring_service.py`

**Imports from**: __future__, app.config, app.db.models.initiative, app.db.models.scoring, app.services.product_ops.kpi_contribution_adapter

**Classes**:
- **Class `ScoringService`**
  - *Doc*: Service layer for computing and persisting initiative scores.
  - `__init__(self, db: Session)`
  - `score_initiative(self, initiative: Initiative, framework: ScoringFramework, enable_history: Optional[bool], activate: bool)`
  - `_score_individual_math_models(self, initiative: Initiative)`
  - `score_initiative_all_frameworks(self, initiative: Initiative, enable_history: Optional[bool])`
  - `activate_all(self, framework: Optional[ScoringFramework], commit_every: Optional[int], only_missing_active: bool)`
  - `compute_all_frameworks(self, commit_every: Optional[int])`
  - `compute_for_initiatives(self, initiative_keys: list[str], commit_every: Optional[int])`
  - `activate_initiative_framework(self, initiative: Initiative, framework: ScoringFramework, enable_history: Optional[bool])`
  - `activate_for_initiatives(self, initiative_keys: list[str], commit_every: Optional[int])`
  - `_resolve_framework_for_initiative(self, initiative: Initiative, explicit_override: Optional[ScoringFramework])`
  - `_build_score_inputs(self, initiative: Initiative, framework: ScoringFramework)`
  - `_build_rice_inputs(self, initiative: Initiative)`
  - `_build_wsjf_inputs(self, initiative: Initiative)`
  - `_build_math_model_inputs(self, initiative: Initiative)`

#### Directory: `app/services/product_ops/scoring/`

##### Module: `__init__.py`
*Path*: `app/services/product_ops/scoring/__init__.py`

**Imports from**: interfaces, registry

*No classes or functions defined*

##### Module: `interfaces.py`
*Path*: `app/services/product_ops/scoring/interfaces.py`

**Imports from**: __future__, enum, pydantic, typing

**Classes**:
- **Class `ScoringFramework`** (inherits: str, Enum)
  - *Doc*: Supported scoring framework identifiers.
  - *No methods*
- **Class `ScoreInputs`** (inherits: BaseModel)
  - *Doc*: Normalized numeric inputs for scoring engines.
  - *No methods*
- **Class `ScoreResult`** (inherits: BaseModel)
  - *Doc*: Result returned by a scoring engine.
  - *No methods*
- **Class `ScoringEngine`** (inherits: Protocol)
  - *Doc*: Protocol that all scoring engines must satisfy.
  - `compute(self, inputs: ScoreInputs)`

##### Module: `registry.py`
*Path*: `app/services/product_ops/scoring/registry.py`

*Doc*: Registry for scoring frameworks and their engines. This module defines available scoring frameworks,

**Imports from**: __future__, app.services.product_ops.scoring.engines, app.services.product_ops.scoring.interfaces, dataclasses, typing

**Classes**:
- **Class `FrameworkInfo`**
  - *No methods*

**Functions**:
- **Function `get_engine(framework: ScoringFramework) -> ScoringEngine`**

##### Module: `utils.py`
*Path*: `app/services/product_ops/scoring/utils.py`

**Imports from**: __future__, typing

**Functions**:
- **Function `safe_div(numerator: Optional[float], denominator: Optional[float]) -> Tuple[(float, Optional[str])]`**
  - *Doc*: Safely divide two optional floats.
- **Function `clamp(value: Optional[float], min_value: float, max_value: float) -> float`**
  - *Doc*: Clamp a possibly None float into [min_value, max_value]. None -> min_value.

#### Directory: `app/services/product_ops/scoring/engines/`

##### Module: `__init__.py`
*Path*: `app/services/product_ops/scoring/engines/__init__.py`

**Imports from**: math_model, rice, wsjf

*No classes or functions defined*

##### Module: `math_model.py`
*Path*: `app/services/product_ops/scoring/engines/math_model.py`

**Imports from**: __future__, app.services.product_ops.scoring.interfaces, app.utils.safe_eval, typing

**Classes**:
- **Class `MathModelScoringEngine`**
  - *Doc*: Scoring engine for custom math models using safe_eval.
  - `score_single_model(self, formula_text: str, params_env: Dict[(str, float)], approved_by_user: bool, effort_fallback: Optional[float])`
  - `compute(self, inputs: ScoreInputs)`

##### Module: `rice.py`
*Path*: `app/services/product_ops/scoring/engines/rice.py`

**Imports from**: __future__, app.services.product_ops.scoring.interfaces, app.services.product_ops.scoring.utils

**Classes**:
- **Class `RiceScoringEngine`**
  - *Doc*: RICE scoring engine.
  - `compute(self, inputs: ScoreInputs)`

##### Module: `wsjf.py`
*Path*: `app/services/product_ops/scoring/engines/wsjf.py`

**Imports from**: __future__, app.services.product_ops.scoring.interfaces, app.services.product_ops.scoring.utils

**Classes**:
- **Class `WsjfScoringEngine`**
  - *Doc*: WSJF scoring engine.
  - `compute(self, inputs: ScoreInputs)`

#### Directory: `app/services/solvers/`

##### Module: `__init__.py`
*Path*: `app/services/solvers/__init__.py`

*Doc*: Solver adapters for optimization problems.

*No classes or functions defined*

##### Module: `ortools_cp_sat_adapter.py`
*Path*: `app/services/solvers/ortools_cp_sat_adapter.py`

*Doc*: OR-Tools CP-SAT solver adapter for Phase 5 optimization.

**Imports from**: __future__, dataclasses, ortools.sat.python, typing

**Classes**:
- **Class `CpSatConfig`**
  - *Doc*: Configuration for OR-Tools CP-SAT solver.
  - *No methods*
- **Class `OrtoolsCpSatSolverAdapter`**
  - *Doc*: Phase 5 v1 solver adapter using OR-Tools CP-SAT.
  - `__init__(self, config: Optional[CpSatConfig])`
  - `solve(self, problem: 'OptimizationProblem')`

**Functions**:
- **Function `_scaled_int(value: float, scale: int) -> int`**
  - *Doc*: Convert float to scaled integer (production-friendly: deterministic rounding).
- **Function `_get_candidate_dim_value(c: 'Candidate', dimension: str) -> Optional[str]`**
  - *Doc*: Map constraint dimensions to Candidate attributes.
- **Function `_get_candidate_dim_value_for_targets(c: 'Candidate', dimension: str) -> Optional[str]`**
  - *Doc*: Extract dimension value from candidate for target matching.
- **Function `_resolve_kpi_scale_from_targets_any(targets: Dict[(str, Any)], kpi_key: str) -> tuple[(float, str, int)]`**
  - *Doc*: Resolve normalization scale for a KPI from targets with fallback aggregation.

#### Directory: `app/sheets/`

##### Module: `__init__.py`
*Path*: `app/sheets/__init__.py`

*No classes or functions defined*

##### Module: `backlog_reader.py`
*Path*: `app/sheets/backlog_reader.py`

**Imports from**: __future__, app.config, app.sheets.client, app.utils.header_utils, typing

**Classes**:
- **Class `BacklogReader`**
  - *Doc*: Reads the central backlog sheet and returns rows as (row_number, dict) pairs.
  - `__init__(self, client: SheetsClient)`
  - `get_rows(self, spreadsheet_id: str, tab_name: str, header_row: int, start_data_row: int, max_rows: int | None)`
  - `_row_to_dict(self, header: List[Any], row_cells: List[Any])`
  - `_is_empty_row(row_cells: List[Any])`
  - `_extract_initiative_key(row: BacklogRow)`

**Functions**:
- **Function `_col_index_to_a1(idx: int) -> str`**

##### Module: `backlog_writer.py`
*Path*: `app/sheets/backlog_writer.py`

**Imports from**: __future__, app.db.models.initiative, app.sheets.client, app.sheets.models, app.utils.header_utils

**Functions**:
- **Function `_to_sheet_value(value: Any) -> Any`**
  - *Doc*: Normalize Python values into something Sheets API can accept.
- **Function `_list_join(values: Any) -> str`**
  - *Doc*: Render list-like values as comma-separated string for Sheets.
- **Function `_initiative_field_value(field: str, initiative: Initiative, now_ts: datetime) -> Any`**
- **Function `initiative_cell_values(header: List[str], initiative: Initiative, sheet_to_canonical: Dict[(str, str)], now_ts: datetime) -> Dict[(str, Any)]`**
  - *Doc*: Map header names (owned columns) to outgoing sheet values for this initiative.
- **Function `_col_index_to_a1(idx: int) -> str`**
- **Function `write_backlog_from_db(db: Session, client: SheetsClient, backlog_spreadsheet_id: str, backlog_tab_name: str) -> None`**
  - *Doc*: Upsert initiatives into the backlog sheet without overwriting unknown columns.
- **Function `_apply_backlog_protected_ranges(client: SheetsClient, spreadsheet_id: str, tab_name: str, header: List[str]) -> None`**
  - *Doc*: Protect all columns that are NOT in CENTRAL_EDITABLE_FIELDS (warning-only).

##### Module: `client.py`
*Path*: `app/sheets/client.py`

**Imports from**: __future__, app.config, google.oauth2.service_account, googleapiclient.discovery, typing

**Classes**:
- **Class `SheetsClient`**
  - *Doc*: Thin wrapper around Google Sheets API values endpoints.
  - `__init__(self, service)`
  - `get_values(self, spreadsheet_id: str, range_: str, value_render_option: str)`
  - `batch_get_values(self, spreadsheet_id: str, ranges: list[str], value_render_option: str)`
  - `update_values(self, spreadsheet_id: str, range_: str, values: List[List[Any]], value_input_option: str)`
  - `get_sheet_grid_size(self, spreadsheet_id: str, tab_name: str)`
  - `get_sheet_properties(self, spreadsheet_id: str, tab_name: str)`
  - `append_values(self, spreadsheet_id: str, range_: str, values: List[List[Any]], value_input_option: str)`
  - `batch_update(self, spreadsheet_id: str, requests: list[dict])`
  - `batch_update_values(self, spreadsheet_id: str, data: List[Dict[(str, Any)]], value_input_option: str)`

**Functions**:
- **Function `get_sheets_service() -> Any`**
  - *Doc*: Create and return a Google Sheets API service client.

##### Module: `intake_reader.py`
*Path*: `app/sheets/intake_reader.py`

**Imports from**: __future__, app.sheets.client, typing

**Classes**:
- **Class `IntakeReader`**
  - *Doc*: Reads department intake sheets and returns rows as (row_number, dict) pairs.
  - `__init__(self, client: SheetsClient)`
  - `get_rows_for_sheet(self, spreadsheet_id: str, tab_name: str, header_row: int, start_data_row: int, max_rows: int | None)`
  - `_row_to_dict(self, header: List[Any], row_cells: List[Any])`
  - `_is_empty_row(self, row_cells: Iterable[Any])`

**Functions**:
- **Function `_col_index_to_a1(idx: int) -> str`**
  - *Doc*: Convert 1-based column index to A1 letter(s).

##### Module: `intake_writer.py`
*Path*: `app/sheets/intake_writer.py`

**Imports from**: __future__, app.config, app.sheets.client, app.sheets.models, app.utils.header_utils

**Classes**:
- **Class `GoogleSheetsIntakeWriter`**
  - *Doc*: Concrete writer for writing initiative_key back to intake sheet.
  - `__init__(self, client: SheetsClient)`
  - `_find_key_column_index(self, sheet_id: str, tab_name: str)`
  - `_find_updated_at_column_index(self, sheet_id: str, tab_name: str)`
  - `write_initiative_key(self, sheet_id: str, tab_name: str, row_number: int, initiative_key: str)`

**Functions**:
- **Function `_col_index_to_a1(idx: int) -> str`**

##### Module: `kpi_contributions_reader.py`
*Path*: `app/sheets/kpi_contributions_reader.py`

*Doc*: KPI_Contributions sheet reader for ProductOps sheet.

**Imports from**: __future__, app.sheets.client, app.sheets.models, app.utils.header_utils, typing

**Classes**:
- **Class `KPIContributionsReader`**
  - *Doc*: Reads KPI_Contributions tab from ProductOps sheet.
  - `__init__(self, client: SheetsClient)`
  - `get_rows_for_sheet(self, spreadsheet_id: str, tab_name: str, header_row: int, start_data_row: int, max_rows: Optional[int])`
  - `_row_to_dict(self, header: List[Any], row_cells: List[Any])`
  - `_parse_contribution(self, value: Any)`
  - `_is_empty_row(self, row_cells: Iterable[Any])`

**Functions**:
- **Function `_blank_to_none(v: Any) -> Any`**
- **Function `_col_index_to_a1(idx: int) -> str`**

##### Module: `kpi_contributions_writer.py`
*Path*: `app/sheets/kpi_contributions_writer.py`

*Doc*: Writer module for Product Ops KPI_Contributions sheet output (DB → sheet writeback).

**Imports from**: __future__, app.db.models.initiative, app.sheets.client, app.sheets.models, app.utils.header_utils

**Functions**:
- **Function `_now_iso() -> str`**
- **Function `_to_sheet_value(value: Any) -> Any`**
  - *Doc*: Normalize values before sending to Sheets to avoid JSON serialization errors.
- **Function `write_kpi_contributions_to_sheet(db: Session, client: SheetsClient, spreadsheet_id: str, tab_name: str) -> int`**
  - *Doc*: Write system-computed KPI contributions from DB to KPI_Contributions sheet.
- **Function `_cell_range_for_update(tab_name: str, col_idx: int, row_idx: int) -> str`**
  - *Doc*: Build A1 notation cell range for a single cell update.
- **Function `_col_index_to_a1(idx: int) -> str`**
  - *Doc*: Convert column index (1-based) to A1 letter notation.

##### Module: `math_models_reader.py`
*Path*: `app/sheets/math_models_reader.py`

*Doc*: MathModels sheet reader for ProductOps sheet.

**Imports from**: __future__, app.sheets.client, app.sheets.models, app.utils.header_utils, typing

**Classes**:
- **Class `MathModelsReader`**
  - *Doc*: Reads MathModels tab from ProductOps sheet.
  - `__init__(self, client: SheetsClient)`
  - `get_rows_for_sheet(self, spreadsheet_id: str, tab_name: str, header_row: int, start_data_row: int, max_rows: Optional[int])`
  - `_row_to_dict(self, header: List[Any], row_cells: List[Any])`
  - `_is_empty_row(self, row_cells: Iterable[Any])`

**Functions**:
- **Function `_blank_to_none(v) -> Any`**
- **Function `_coerce_bool(v) -> Any`**
- **Function `_col_index_to_a1(idx: int) -> str`**
  - *Doc*: Convert 1-based column index to A1 letter(s).

##### Module: `math_models_writer.py`
*Path*: `app/sheets/math_models_writer.py`

*Doc*: MathModels sheet writer for ProductOps sheet.

**Imports from**: __future__, app.sheets.client, app.sheets.models, app.utils.header_utils, app.utils.provenance

**Classes**:
- **Class `MathModelsWriter`**
  - *Doc*: Writer for LLM suggestions in MathModels tab.
  - `__init__(self, client: SheetsClient)`
  - `write_formula_suggestion(self, spreadsheet_id: str, tab_name: str, row_number: int, llm_suggested_formula_text: str)`
  - `write_llm_notes(self, spreadsheet_id: str, tab_name: str, row_number: int, llm_notes: str)`
  - `write_suggestions_batch(self, spreadsheet_id: str, tab_name: str, suggestions: List[Dict[(str, Any)]])`
  - `_find_column_index(self, spreadsheet_id: str, tab_name: str, column_name: str)`
  - `_get_approved_status_for_rows(self, spreadsheet_id: str, tab_name: str, row_numbers: List[int], approved_col_idx: int)`

**Functions**:
- **Function `_now_iso() -> str`**
- **Function `_col_index_to_a1(idx: int) -> str`**
  - *Doc*: Convert 1-based column index to A1 letter(s).

##### Module: `metrics_config_reader.py`
*Path*: `app/sheets/metrics_config_reader.py`

*Doc*: Metrics_Config sheet reader for ProductOps sheet.

**Imports from**: __future__, app.sheets.client, app.sheets.models, app.utils.header_utils, typing

**Classes**:
- **Class `MetricsConfigReader`**
  - *Doc*: Reads Metrics_Config tab from ProductOps sheet.
  - `__init__(self, client: SheetsClient)`
  - `get_rows_for_sheet(self, spreadsheet_id: str, tab_name: str, header_row: int, start_data_row: int, max_rows: Optional[int])`
  - `_row_to_dict(self, header: List[Any], row_cells: List[Any])`
  - `_is_empty_row(self, row_cells: Iterable[Any])`

**Functions**:
- **Function `_blank_to_none(v: Any) -> Any`**
- **Function `_coerce_bool(v: Any) -> Optional[bool]`**
- **Function `_col_index_to_a1(idx: int) -> str`**

##### Module: `models.py`
*Path*: `app/sheets/models.py`

*Doc*: Pydantic models for sheet row representations.

**Imports from**: __future__, datetime, pydantic, typing

**Classes**:
- **Class `MetricsConfigRow`** (inherits: BaseModel)
  - *Doc*: Represents a single row from ProductOps Metrics_Config tab.
  - *No methods*
- **Class `KPIContributionRow`** (inherits: BaseModel)
  - *Doc*: Represents a single row from ProductOps KPI_Contributions tab.
  - *No methods*
- **Class `MathModelRow`** (inherits: BaseModel)
  - *Doc*: Represents a single row from MathModels tab in ProductOps sheet.
  - *No methods*
- **Class `ParamRow`** (inherits: BaseModel)
  - *Doc*: Represents a single row from Params tab in ProductOps sheet.
  - `_sync_display_aliases(self)`
- **Class `OptCandidateRow`** (inherits: BaseModel)
  - *Doc*: Optimization Center Candidates tab row.
  - *No methods*
- **Class `OptScenarioConfigRow`** (inherits: BaseModel)
  - *Doc*: Optimization Center Scenario_Config tab row.
  - *No methods*
- **Class `OptConstraintRow`** (inherits: BaseModel)
  - *Doc*: Optimization Center Constraints tab row.
  - *No methods*
- **Class `OptTargetRow`** (inherits: BaseModel)
  - *Doc*: Optimization Center Targets tab row.
  - *No methods*
- **Class `OptRunRow`** (inherits: BaseModel)
  - *Doc*: Optimization Center Runs tab row.
  - *No methods*
- **Class `OptResultRow`** (inherits: BaseModel)
  - *Doc*: Optimization Center Results tab row.
  - *No methods*
- **Class `OptGapAlertRow`** (inherits: BaseModel)
  - *Doc*: Optimization Center Gaps_and_alerts tab row.
  - *No methods*

##### Module: `optimization_candidates_writer.py`
*Path*: `app/sheets/optimization_candidates_writer.py`

*Doc*: Writer for Optimization Candidates tab - populates from DB.

**Imports from**: __future__, app.db.models.initiative, app.db.models.optimization, app.sheets.client, app.sheets.optimization_center_readers

**Functions**:
- **Function `populate_candidates_from_db(db: Session, client: SheetsClient, spreadsheet_id: str, tab_name: str, scenario_name: str, constraint_set_name: str, initiative_keys: Optional[List[str]]) -> Dict[(str, Any)]`**
  - *Doc*: Populate Optimization Candidates tab from DB.
- **Function `_col_idx_to_letter(idx: int) -> str`**
  - *Doc*: Convert 0-based column index to A1 notation letter.

##### Module: `optimization_center_readers.py`
*Path*: `app/sheets/optimization_center_readers.py`

*Doc*: Readers for Optimization Center tabs (Candidates, Scenario_Config, Constraints, Targets, Runs, Results, Gaps_and_alerts).

**Imports from**: __future__, app.sheets.client, app.sheets.models, app.utils.header_utils, datetime

**Classes**:
- **Class `_BaseOptReader`**
  - `__init__(self, client: SheetsClient)`
  - `_read_raw(self, spreadsheet_id: str, tab_name: str, header_row: int)`
- **Class `CandidatesReader`** (inherits: _BaseOptReader)
  - `get_rows(self, spreadsheet_id: str, tab_name: str)`
- **Class `ScenarioConfigReader`** (inherits: _BaseOptReader)
  - `get_rows(self, spreadsheet_id: str, tab_name: str)`
- **Class `ConstraintsReader`** (inherits: _BaseOptReader)
  - `get_rows(self, spreadsheet_id: str, tab_name: str)`
- **Class `TargetsReader`** (inherits: _BaseOptReader)
  - `get_rows(self, spreadsheet_id: str, tab_name: str)`
- **Class `RunsReader`** (inherits: _BaseOptReader)
  - `get_rows(self, spreadsheet_id: str, tab_name: str)`
- **Class `ResultsReader`** (inherits: _BaseOptReader)
  - `get_rows(self, spreadsheet_id: str, tab_name: str)`
- **Class `GapsAlertsReader`** (inherits: _BaseOptReader)
  - `get_rows(self, spreadsheet_id: str, tab_name: str)`

**Functions**:
- **Function `_col_index_to_a1(idx: int) -> str`**
- **Function `_blank_to_none(val: Any) -> Any`**
- **Function `_to_bool(val: Any) -> Optional[bool]`**
- **Function `_to_float(val: Any) -> Optional[float]`**
- **Function `_to_int(val: Any) -> Optional[int]`**
- **Function `_split_keys(val: Any) -> Optional[List[str]]`**
  - *Doc*: Split a cell value into a list of strings, using commas or semicolons as delimiters.
- **Function `_to_date_iso(val: Any) -> Optional[str]`**
- **Function `_parse_json(val: Any) -> Optional[Any]`**
- **Function `_build_alias_lookup(header_map: Dict[(str, List[str])]) -> Dict[(str, str)]`**
- **Function `_row_to_dict(header: List[Any], row_cells: List[Any], lookup: Dict[(str, str)]) -> Dict[(str, Any)]`**

##### Module: `optimization_center_writers.py`
*Path*: `app/sheets/optimization_center_writers.py`

*Doc*: Writers for Optimization Center tabs (DB -> Sheets).

**Imports from**: __future__, app.sheets.client, app.sheets.models, app.utils.header_utils, app.utils.provenance

**Classes**:
- **Class `OptimizationCenterWriter`**
  - *Doc*: Writer for Optimization Center tabs (DB -> Sheets).
  - `__init__(self, client: SheetsClient)`
  - `_write_tab(self, spreadsheet_id: str, tab_name: str, header_map: Dict[(str, List[str])], key_fields: List[str], key_builder, write_fields: List[str], rows: Iterable[Any])`
  - `write_candidates(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any])`
  - `write_scenario_config(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any])`
  - `write_constraints(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any])`
  - `write_targets(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any])`
  - `append_runs_row(self, spreadsheet_id: str, tab_name: str, row: Dict[(str, Any)])`
  - `append_results_rows(self, spreadsheet_id: str, tab_name: str, rows: List[Dict[(str, Any)]])`
  - `append_gaps_rows(self, spreadsheet_id: str, tab_name: str, rows: List[Dict[(str, Any)]])`
  - `write_runs(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any])`
  - `write_results(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any])`
  - `write_gaps_alerts(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any])`

**Functions**:
- **Function `_now_iso() -> str`**
  - *Doc*: Get the current UTC time in ISO 8601 format.
- **Function `_col_index_to_a1(idx: int) -> str`**
  - *Doc*: Convert a 1-based column index to A1 notation (e.g., 1 -> 'A', 27 -> 'AA').
- **Function `_to_sheet_value(value: Any) -> Any`**
  - *Doc*: Convert a Python value to a Sheets-compatible value.
- **Function `_row_to_dict(row: Any) -> Dict[(str, Any)]`**
  - *Doc*: Convert a row object to a dictionary.
- **Function `_build_alias_lookup(header_map: Dict[(str, List[str])]) -> Dict[(str, str)]`**
  - *Doc*: Build a lookup of normalized header aliases to field names.
- **Function `_build_column_map(header: Sequence[Any], header_map: Dict[(str, List[str])]) -> Dict[(int, str)]`**
  - *Doc*: Build a mapping of column indices to field names based on header aliases.
- **Function `_read_header(client: SheetsClient, spreadsheet_id: str, tab_name: str) -> List[Any]`**
  - *Doc*: Read the header row (first row) of a given tab.
- **Function `_read_key_rows_composite(client: SheetsClient, spreadsheet_id: str, tab_name: str, key_fields: List[str], col_map: Dict[(int, str)], key_builder) -> Dict[(str, int)]`**
  - *Doc*: Read key columns and map composite keys to row numbers.
- **Function `_chunked_updates(client: SheetsClient, spreadsheet_id: str, updates: List[Dict[(str, Any)]]) -> None`**
  - *Doc*: Send batch_update_values in chunks to avoid size limits.
- **Function `_build_updates_for_rows(rows: Iterable[Any], col_map: Dict[(int, str)], key_fields: List[str], key_builder, write_fields: List[str], tab_name: str, key_to_row: Dict[(str, int)]) -> Tuple[(List[Dict[(str, Any)]], List[int], Set[Tuple[(int, str)]])]`**

##### Module: `params_reader.py`
*Path*: `app/sheets/params_reader.py`

*Doc*: Params sheet reader for ProductOps sheet.

**Imports from**: __future__, app.sheets.client, app.sheets.models, app.utils.header_utils, typing

**Classes**:
- **Class `ParamsReader`**
  - *Doc*: Reads Params tab from ProductOps sheet.
  - `__init__(self, client: SheetsClient)`
  - `get_rows_for_sheet(self, spreadsheet_id: str, tab_name: str, header_row: int, start_data_row: int, max_rows: Optional[int])`
  - `_row_to_dict(self, header: List[Any], row_cells: List[Any])`
  - `_is_empty_row(self, row_cells: Iterable[Any])`

**Functions**:
- **Function `_blank_to_none(v: Any) -> Any`**
- **Function `_coerce_bool(v: Any) -> Optional[bool]`**
- **Function `_coerce_float(v: Any) -> Optional[float]`**
- **Function `_col_index_to_a1(idx: int) -> str`**
  - *Doc*: Convert 1-based column index to A1 letter(s).

##### Module: `params_writer.py`
*Path*: `app/sheets/params_writer.py`

*Doc*: Params sheet writer for ProductOps sheet.

**Imports from**: __future__, app.sheets.client, app.sheets.models, app.utils.header_utils, app.utils.provenance

**Classes**:
- **Class `ParamsWriter`**
  - *Doc*: Writer for Params tab with append-only strategy.
  - `__init__(self, client: SheetsClient)`
  - `_get_last_data_row(self, spreadsheet_id: str, tab_name: str)`
  - `append_parameters(self, spreadsheet_id: str, tab_name: str, parameters: List[Dict[(str, Any)]])`
  - `append_new_params(self, spreadsheet_id: str, tab_name: str, params: List[Dict[(str, Any)]])`
  - `update_parameter_value(self, spreadsheet_id: str, tab_name: str, row_number: int, value: str, is_auto_seeded: bool)`
  - `update_parameters_batch(self, spreadsheet_id: str, tab_name: str, updates: List[Dict[(str, Any)]])`
  - `backfill_seeded_provenance(self, spreadsheet_id: str, tab_name: str)`
  - `_build_column_indices(self, header: List[str])`
  - `_build_row(self, param: Dict[(str, Any)], column_indices: Dict[(str, int)], total_cols: int)`
  - `_find_column_index(self, spreadsheet_id: str, tab_name: str, column_name: str)`

**Functions**:
- **Function `_now_iso() -> str`**
- **Function `_col_index_to_a1(idx: int) -> str`**
  - *Doc*: Convert 1-based column index to A1 letter(s).

##### Module: `productops_writer.py`
*Path*: `app/sheets/productops_writer.py`

*Doc*: Writer module for Product Ops Scoring_Inputs sheet output (score write-back).

**Imports from**: __future__, app.db.models.initiative, app.sheets.client, app.sheets.models, app.utils.header_utils

**Functions**:
- **Function `_now_iso() -> str`**
- **Function `_to_sheet_value(value: Any) -> Any`**
  - *Doc*: Normalize values before sending to Sheets to avoid JSON serialization errors.
- **Function `write_scores_to_productops_sheet(db: Session, client: SheetsClient, spreadsheet_id: str, tab_name: str) -> int`**
  - *Doc*: Write per-framework scores from DB to Product Ops sheet using targeted cell updates.
- **Function `write_status_to_productops_sheet(client: SheetsClient, spreadsheet_id: str, tab_name: str, status_by_key: Dict[(str, str)]) -> int`**
  - *Doc*: Write per-row Status messages for selected initiatives.
- **Function `write_status_to_sheet(client: SheetsClient, spreadsheet_id: str, tab_name: str, status_by_key: Dict[(str, str)]) -> int`**
  - *Doc*: Generic alias for per-row status writes.
- **Function `_cell_range_for_update(tab_name: str, col_idx: int, row_idx: int) -> str`**
  - *Doc*: Build A1 notation cell range for a single cell update.
- **Function `_col_index_to_a1(idx: int) -> str`**
  - *Doc*: Convert column index (1-based) to A1 letter notation.

##### Module: `scoring_inputs_reader.py`
*Path*: `app/sheets/scoring_inputs_reader.py`

**Imports from**: __future__, app.sheets.client, dataclasses, typing

**Classes**:
- **Class `ScoringInputsRow`**
  - *No methods*
- **Class `ScoringInputsReader`**
  - *Doc*: Reads a namespaced, wide Scoring_Inputs sheet.
  - `__init__(self, client: SheetsClient, spreadsheet_id: str, tab_name: str)`
  - `_parse_header(self, headers: List[str])`
  - `_to_bool(val: Any)`
  - `_to_float(val: Any)`
  - `read(self)`

##### Module: `sheet_protection.py`
*Path*: `app/sheets/sheet_protection.py`

*Doc*: Warning-only protected ranges for ProductOps tabs (MathModels, Params, Scoring_Inputs).

**Imports from**: __future__, app.sheets.client, app.sheets.models, app.utils.header_utils, typing

**Functions**:
- **Function `apply_warning_protections(client: SheetsClient, spreadsheet_id: str, tab_name: str, system_columns: List[str], header_map: Optional[Dict[(str, List[str])]]) -> None`**
  - *Doc*: Apply warningOnly=True protections to system columns in a ProductOps tab.
- **Function `apply_all_productops_protections(client: SheetsClient, spreadsheet_id: str, math_models_tab: str, params_tab: str, scoring_inputs_tab: str) -> None`**
  - *Doc*: Apply warning-only protections to all ProductOps tabs.
- **Function `_extract_sheet_id(props: dict, tab_name: str) -> Optional[int]`**
  - *Doc*: Extract sheet ID from various response shapes.
- **Function `_extract_protected_ranges(props: dict) -> List[dict]`**
  - *Doc*: Extract existing protected ranges from various response shapes.
- **Function `_find_column_index(header: List[str], canonical_name: str, header_map: Optional[Dict[(str, List[str])]]) -> Optional[int]`**
  - *Doc*: Find column index by canonical name with alias support.

#### Directory: `app/utils/`

##### Module: `__init__.py`
*Path*: `app/utils/__init__.py`

*No classes or functions defined*

##### Module: `header_utils.py`
*Path*: `app/utils/header_utils.py`

**Imports from**: __future__, typing

**Functions**:
- **Function `normalize_header(name: str) -> str`**
  - *Doc*: Normalize sheet header to lowercase field name format.
- **Function `resolve_indices(headers: List[str], header_map: Dict[(str, List[str])]) -> Dict[(str, int)]`**
  - *Doc*: Resolve column indices for a tab, using alias maps.
- **Function `get_value_by_header_alias(row: Dict[(str, Any)], primary_name: str, aliases: Iterable[str] | None) -> Optional[Any]`**
  - *Doc*: Return the value from row matching primary header name or any alias.

##### Module: `periods.py`
*Path*: `app/utils/periods.py`

*Doc*: Period parsing utilities for optimization scenarios.

**Imports from**: __future__, dataclasses, datetime

**Classes**:
- **Class `PeriodWindow`**
  - *Doc*: Represents a time period with start and end dates (end is inclusive).
  - `contains(self, dt: date)`

**Functions**:
- **Function `parse_period_key(period_key: str) -> PeriodWindow`**
  - *Doc*: Parse a period key string into a PeriodWindow.
- **Function `_parse_quarterly(year: int, quarter: int) -> PeriodWindow`**
  - *Doc*: Parse quarterly period (Q1-Q4).
- **Function `_parse_monthly(year: int, month: int) -> PeriodWindow`**
  - *Doc*: Parse monthly period (1-12).
- **Function `_parse_weekly(year: int, week: int) -> PeriodWindow`**
  - *Doc*: Parse weekly period (ISO week numbering).
- **Function `get_period_end_date(period_key: str) -> date`**
  - *Doc*: Convenience function to extract just the end date from a period key.

##### Module: `provenance.py`
*Path*: `app/utils/provenance.py`

**Imports from**: __future__, enum, typing

**Classes**:
- **Class `Provenance`** (inherits: str, Enum)
  - *Doc*: Canonical provenance tokens for DB and sheet writes.
  - *No methods*

**Functions**:
- **Function `token(prov: Provenance, run_id: Optional[str]) -> str`**
  - *Doc*: Render a provenance token, optionally appending a run identifier later if needed.

##### Module: `safe_eval.py`
*Path*: `app/utils/safe_eval.py`

**Imports from**: __future__, typing

**Classes**:
- **Class `SafeEvalError`** (inherits: Exception)
  - *Doc*: Raised when a formula is invalid, unsafe, or fails during evaluation.
  - *No methods*
- **Class `_SafeExprValidator`** (inherits: ast.NodeVisitor)
  - *Doc*: Validate that an expression contains only safe nodes.
  - `visit_Call(self, node: ast.Call)`
  - `visit_BinOp(self, node: ast.BinOp)`
  - `visit_UnaryOp(self, node: ast.UnaryOp)`
  - `visit_Name(self, node: ast.Name)`
  - `visit_Constant(self, node: ast.Constant)`
  - `generic_visit(self, node: ast.AST)`

**Functions**:
- **Function `extract_identifiers(formula_text: str) -> List[str]`**
  - *Doc*: Return input variable names (identifiers used on RHS) from a script.
- **Function `_validate_and_compile_expr(expr_src: str) -> ast.Expression`**
- **Function `evaluate_script(script: str, initial_env: Dict[(str, float)], timeout_secs: float) -> Dict[(str, float)]`**
  - *Doc*: Safely evaluate a multi-line math model script.
- **Function `validate_formula(script: str, max_lines: int) -> List[str]`**
  - *Doc*: Validate script for length, syntax, and required `value` assignment.

#### Directory: `app/workers/`

##### Module: `__init__.py`
*Path*: `app/workers/__init__.py`

*No classes or functions defined*

##### Module: `action_worker.py`
*Path*: `app/workers/action_worker.py`

**Imports from**: __future__, app.config, app.db.session, app.services.action_runner, typing

**Functions**:
- **Function `run_worker_loop(poll_interval_seconds: float, idle_sleep_seconds: float, max_runs: Optional[int]) -> int`**
  - *Doc*: Continuously execute queued ActionRuns.

