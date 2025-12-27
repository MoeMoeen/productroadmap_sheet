
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

  * One row per initiative using mathematical modeling
  * Stores PM free-text descriptions, LLM-suggested formulas, final approved formulas
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
  * Parameter auto-seeding
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
  * Suggest Math Models (selected rows)
  * Seed Params (approved models)
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

7. **Backend computes optimized portfolio** based on constraints (capacity, dependencies, strategic themes)
8. **Roadmap entries** are generated, versioned, and published.

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

## **9. Phase 5 Preview (After Phase 4.5)**

Once Phase 4.5 is stable:

* **Optimization Engine**: Linear/nonlinear solver for portfolio selection
* **Roadmap Generation**: Produce quarterly roadmap from optimization results
* **Scenario Simulation**: "What-if" weightings (revenue-heavy, risk-avoidance, etc.)
* **Monte Carlo**: Uncertainty modeling for robust portfolio selection

All triggered via Phase 4.5 control plane menu → `flow5.run_optimization`.

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
  
- **Phase 3.D (Config Tab)** ⏳ **Deferred**
  * Config-driven system behaviors planned for future

### **✅ COMPLETED:**

**Phase 4.5 – Sheet-Native Execution & Control Plane (Backend)** *(PRE-OPTIMIZATION PREREQUISITE)*
   * **Action API** – Single entry point (`POST /actions/enqueue`, `GET /actions/status/{run_id}`)
   * **ActionRun Ledger** – DB-backed execution tracking with job state, payloads, results
   * **PM Jobs Implemented**:
     - `pm.backlog_sync` – See latest intake initiatives in Central Backlog
     - `pm.score_selected` – Deep-dive and score selected initiatives
     - `pm.switch_framework` – Change active scoring framework (local only)
     - `pm.save_selected` – Save changes from tab (selection-based, tab-aware)
   * **Consistent Patterns**:
     - Server-side orchestration with single ActionRun per job
     - Selection-scoped operations via initiative_keys
     - Per-row Status column writes (separate from Updated Source provenance)
     - Accurate summary fields: selected_count, saved_count, failed_count, skipped_no_key
   * **Status Writer Abstraction** – Generic `write_status_to_sheet` alias for cross-tab compatibility
   * **Tab Detection** – Exact config matches with substring fallback for robustness
   * **Action Registry** – 15 total actions (Flow 0-4 + 4 PM Jobs)

### **📋 PLANNED (Future):**

**Phase 4.5.B – Apps Script UI Layer**
   * **Custom Menu** – "Roadmap AI" menu in ProductOps and Intake sheets
   * **Control Tab** – Live status surface showing run history, results, errors
   * **Polling Logic** – Apps Script polls backend for job completion
   * **PM-Driven Workflows** – Zero terminal access required for all flows
   * **Flow Actions** – Implement remaining flow actions:
     - `flow3.compute_all_frameworks`, `flow3.write_scores`
     - `flow2.activate`, `flow1.backlog_sync`
     - `flow4.suggest_mathmodels`, `flow4.seed_params`
     - `flow0.intake_sync`

**Phase 4 – MathModel Framework & LLM-Assisted Scoring** *(Post-4.5)*
   * **MathModels Sheet** – Dedicated sheet for custom quantitative formulas per initiative
   * **InitiativeMathModel** – DB model persistence and versioning
   * **LLM Integration for MathModels**:
     - Formula generation from PM free-text descriptions
     - Parameter suggestion with units, ranges, and metadata
     - Assumptions extraction and documentation
     - Plain-language formula explanations
   * **MathModelFramework** – Scoring framework using custom formulas
   * **Bidirectional Sheet-DB Sync** – MathModels sheet ↔ DB with batch updates
   * **Safe Formula Evaluation** – Parser and evaluator for approved formulas
   * **Parameter Seeding** – Auto-create Params rows from parsed formula variables
   * **Formula Approval Workflow** – LLM suggestions → PM review → approved formula

**Phase 5 – Portfolio Optimization & Roadmap Generation** *(ENABLED BY 4.5)*
   * Linear / mixed-integer optimization solver (pulp, ortools)
   * Multi-objective weighted-sum scenarios
   * Capacity-constrained roadmap generation
   * Roadmap sheet generation with selected initiatives

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

### **Three-Flow Architecture**

The current system operates with three independent, coordinated data flows:

1. **Flow 1 – Intake Consolidation (Source of Truth)**
   - **What**: Department intake sheets → DB → Central Backlog sheet
   - **When**: Triggered manually or on schedule via `sync_intake_job.py`
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
   - **When**: On schedule or manual trigger
   - **Responsibility**: Computes RICE + WSJF scores from Product Ops parameters
   - **Key Operations**:
     - `flow3_cli --sync`: Read Product Ops sheet into DB
     - `flow3_cli --compute-all`: Compute all RICE + WSJF scores
     - `flow3_cli --write-scores`: Write per-framework scores back to Central Backlog
   - **Important**: Flow 3 does NOT activate scores to active fields; Flow 2 must run afterward

### **Framework Switching Workflow**

To change the active scoring framework (e.g., WSJF → RICE):

1. **Edit Central Backlog** – Change `active_scoring_framework` cell
2. **Run Flow 1** – `backlog_update_cli --sync` (pulls framework change into DB)
3. **Run Flow 2** – `flow2_scoring_cli --all` (activates RICE scores to active fields)
4. **Sync Back** – `backlog_sync_cli --log-level INFO` (pushes updated active scores to sheet)

Result: Central Backlog now shows RICE scores in `value_score` / `overall_score` columns.

### **Key Architectural Concepts**

- **Per-Framework Fields**: Each initiative has isolated scoring fields (e.g., `rice_value_score`, `wsjf_value_score`) that preserve framework-specific computation
- **Active Fields**: `value_score` and `overall_score` are "view" fields that get populated by Flow 2 based on `active_scoring_framework`
- **Batch Updates**: All sheet writes use Google Sheets API `values().batchUpdate()` (1 API call for N cells) for efficiency
- **Header Normalization**: Sheet columns support underscore variants (e.g., `active_scoring_framework` or `ACTIVE_SCORING_FRAMEWORK`)
- **Atomicity**: DB transactions ensure data consistency; sheet updates batched to avoid partial writes

### **Data Propagation Example**

Product Ops enters RICE parameters → Flow 3 `--sync` → DB updated → Flow 3 `--compute-all` → RICE per-framework scores computed → Flow 3 `--write-scores` → Scores written to Central Backlog sheet → Flow 2 activation skipped (scores already for current framework) → Flow 1 backlog_sync reads updated Central Backlog back into DB for next iteration.

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

roadmap_platform/
├── pyproject.toml / requirements.txt
├── README.md
├── .env
└── app/
    ├── __init__.py
    ├── config.py                        # Settings, API keys, sheet IDs, env vars
    │
    ├── db/
    │   ├── __init__.py
    │   ├── base.py                      # SQLAlchemy Base
    │   ├── session.py                   # DB engine + SessionLocal
    │   └── models/
    │       ├── __init__.py
    │       ├── initiative.py            # Initiative ORM model
    │       ├── roadmap.py               # Roadmap ORM
    │       ├── roadmap_entry.py         # RoadmapEntry ORM
    │       └── scoring.py               # InitiativeMathModel, InitiativeScore
    │
    ├── schemas/
    │   ├── __init__.py
    │   ├── initiative.py                # Pydantic schemas for Initiative
    │   ├── roadmap.py                   # Pydantic schemas for Roadmap
    │   ├── roadmap_entry.py             # Pydantic schemas for RoadmapEntry
    │   └── scoring.py                   # Schemas for math models, scoring history
    │
    ├── sheets/                          # Google Sheets API integration layer
    │   ├── __init__.py
    │   ├── client.py                    # Google Sheets API wrapper
    │   ├── intake_reader.py             # Reads intake sheets from departments
    │   ├── backlog_writer.py            # Writes to central backlog sheet
    │   │
    │   ├── math_models_reader.py        # Reads MathModels sheet rows
    │   ├── math_models_writer.py        # Writes LLM suggestions + approvals
    │   │
    │   ├── params_reader.py             # Reads Params rows (all frameworks)
    │   └── params_writer.py             # Writes auto-seeded params + updates
    │
    ├── services/                        # Core business logic and orchestration
    │   ├── __init__.py
    │   │
    │   ├── intake_mapper.py             # Row → InitiativeCreate mapping
    │   ├── initiative_key.py            # Initiative key generator
    │   ├── intake_service.py            # Syncs sheet rows → DB (upsert)
    │   │
    │   ├── validation_service.py        # Missing fields, completeness checks
    │   │
    │   ├── scoring/                     # Scoring engine (modular frameworks)
    │   │   ├── __init__.py
    │   │   ├── base_framework.py        # Framework interface + ScoreResult
    │   │   ├── rice_framework.py        # RICE implementation
    │   │   ├── wsjf_framework.py        # WSJF implementation (optional)
    │   │   ├── moscow_framework.py      # MoSCoW implementation (optional)
    │   │   ├── simple_weighted.py       # Generic weighted scoring
    │   │   └── math_model_framework.py  # Formula-based scoring using math models
    │   │
    │   ├── scoring_service.py           # Orchestrates scoring across frameworks
    │   ├── param_seeding_service.py     # *NEW*: Auto-seeds params from formula/framework
    │   │
    │   ├── optimization_service.py      # Linear, nonlinear, multi-objective optimization
    │   └── roadmap_service.py           # Roadmap generation, scenario creation
    │
    ├── llm/                             # LLM integration
    │   ├── __init__.py
    │   ├── client.py                    # Wrapper for OpenAI/Anthropic/etc.
    │   ├── enrichment.py                # Summaries, classification, hypothesis
    │   ├── scoring_assistant.py         # Formula generation, parameter suggestions
    │   └── prompts.py                   # Prompt templates for all LLM tasks
    │
    ├── jobs/                            # Scheduled / batch jobs
    │   ├── __init__.py
    │   ├── sync_intake_job.py           # Intake sheets → DB sync
    │   ├── validation_job.py            # Populates missing_fields, nudges requesters
    │   ├── math_model_generation_job.py # Reads MathModels, calls LLM, writes suggestions
    │   ├── param_seeding_job.py         # Seeds Params from formulas or framework
    │   │── optimisation_job.py
    │   └── scoring_job.py               # Batch run scoring, writes results to backlog
    │
    ├── api/ (optional for future REST endpoints)
    │   ├── __init__.py
    │   ├── deps.py
    │   ├── routes_initiatives.py
    │   └── routes_roadmaps.py
    │
    └── utils/                           # Helpers (optional)
        ├── safe_eval.py                 # Safe expression evaluation for math models
        └── formula_parser.py            # Parse formula_text_final into an AST or DSL


# **Core end-to-end flows**


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

**Scenario:** PM decides a particular initiative needs a full mathematical model.

### 3.1. PM flags initiative to use math model

* In central backlog sheet:

  * `use_math_model = TRUE`
  * `active_scoring_framework = "MATH_MODEL"`

### 3.2. PM describes the model in MathModels sheet

* PM opens **MathModels** sheet:

  * Adds/edits row with:

    * `initiative_key = "INIT-000456"`
    * `framework = "MATH_MODEL"`
    * `model_description_free_text` (or leaves blank + maybe `llm_prompt`).

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

    1. Access `initiative.math_model` (via relationship to `InitiativeMathModel`).

    2. Build a parameter dict:

       ```python
       params = get_params_for_initiative(initiative.initiative_key, framework="MATH_MODEL")
       ```

    3. Evaluate formula:

       * **Module:** `app/utils/safe_eval.py`
       * **Function:** `evaluate_formula(formula_text: str, params: dict) -> float`

    4. Compute:

       ```python
       value_score = evaluated_value
       effort_score = initiative.effort_engineering_days or derived_from_tshirt
       overall_score = value_score / effort_score if effort_score > 0 else None
       ```

* `ScoringService` then updates `initiative.value_score`, `initiative.overall_score`, persists `InitiativeScore`, and `backlog_writer` pushes numbers back to central sheet.

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
Canonical object representing a proposed product change. Aggregates identity (initiative_key, source_*), requester info, problem/context, strategic classification, impact (low/expected/high), effort (t‑shirt, days), risk/dependencies, workflow status, scoring summary (value_score, effort_score, overall_score), math‑model linkage (use_math_model, math_model_id).

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
Per‑initiative modeling workspace for those using custom quantitative formulas. Columns for free‑text description, llm_suggested_formula_text, assumptions_text, formula_text_final, approval flags. PM approves final formula → backend stores in InitiativeMathModel.

8. InitiativeMathModel (DB)  
Single math model attached (optionally) to an Initiative. Fields: formula_text (approved), parameters_json (structure & metadata), assumptions_text, suggested_by_llm flag. Drives evaluation in MathModelFramework.

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








