Below is a **clean, accurate, comprehensive Step 4.5 document**, written exactly to **capture what we have agreed so far**, no more and no less.

---

# Step 4.5 — Sheet-Native Execution Layer & PM Jobs (V2)

## 1. Purpose of Step 4.5

Step 4.5 introduces a **PM-centric execution layer** that sits between:

* the **PM’s mental model** (Sheets as UI + source of truth), and
* the **backend system model** (DB, flows, workers, jobs).

The goal is to:

* Make **Google Sheets the primary and only UI for PMs**
* Let PMs perform **intuitive, outcome-oriented jobs**
* Hide backend flows, databases, and orchestration details
* Ensure correctness, safety, and determinism in the backend
* Prepare the system for **optimization (Step 5)** without forcing PMs to learn technical workflows

This step is explicitly about **UX, interaction design, and system boundaries**, not about new business logic.

---

## 2. Core UX & Mental Model Principles (Agreed)

### 2.1 Sheets are the PM’s source of truth

From the PM’s perspective:

* **Sheets are the system**
* The database is an implementation detail
* PMs do not “sync with DB” — they **save**
* PMs do not “run flows” — they **apply changes** or **see results**

All PM jobs must be framed and designed from this perspective.

---

### 2.2 Backend flows ≠ PM jobs

* Backend flows (Flow 0–4) are **engineering primitives**
* PM jobs are **super-actions** that:

  * orchestrate multiple flows
  * enforce ordering
  * scope execution (selection vs all)
  * return a single coherent outcome

PMs should never need to understand or sequence backend flows.

---

### 2.3 Explicit over implicit

We deliberately avoid:

* auto-sync on every edit
* invisible background writes
* implicit cross-sheet propagation

Instead, we prefer:

* explicit **Save**
* explicit **Compute**
* explicit **Update Backlog**

This makes behavior predictable, debuggable, and trustable.

---

## 3. Execution Model Context (Non-PM-Facing)

Step 4.5 relies on the following execution model (already implemented):

* **Action API** (HTTP)
* **ActionRun** (DB-backed execution ledger)
* **Worker process** (executes queued actions)
* **Apps Script UI** (menus, buttons, selection handling)

PM jobs are mapped onto this execution model, but PMs never see it.

---

## 4. Agreed PM Jobs (V1)

We explicitly defined V1 as **four PM jobs**. V2 adds two math-model jobs to support LLM-assisted formulas and explicit parameter seeding.
Each job is described in:

* PM intent
* Sheet surface(s)
* Expected behavior
* Scope & constraints
* Important nuances

---

## PM Job #1 — See latest intake initiatives in Central Backlog

### PM intent

> “I want to see the latest initiatives added by teams so I can work on them.”

### Sheet surfaces involved

* **Intake sheets** (owned by teams)
* **Central Backlog** (owned by PMs)

### Expected behavior

* New initiatives added in intake appear in Central Backlog
* Each initiative appears **once**, with a stable identifier
* Existing backlog rows are preserved
* Safe to run repeatedly (idempotent)

### PM perspective

* This is about **visibility**, not decision-making
* PM expects to *see what’s new*, not to score or prioritize yet
* PM does not care how many intake sheets/tabs exist

### Constraints & nuances

* Append-oriented from PM perspective
* No destructive updates
* No scoring, activation, or prioritization implied

### Implementation Status (V1) ✅

- **Action**: `pm.backlog_sync`
- **Orchestration**: Single ActionRun enqueued via worker
- **Backend flow**: Executes `run_all_backlog_sync()` (Flow 1)
- **Scope**: Always operates on all initiatives (no selection)
- **Status writes**: Per-row Status column updates in Central Backlog
- **Summary fields**: `updated_count`, `cells_updated` returned in ActionRun result
- **Provenance**: ActionRun uses `pm.backlog_sync` token; sheet Updated Source reflects flow token

---

## PM Job #2 — Deep-dive and score selected initiatives (Product Ops)

### PM intent

> “I want to score selected initiatives and compare them.”

### Primary sheet surface

* **Product Ops → Scoring Inputs** (main dashboard)

### Supporting sheet surfaces

* **Math Models**
* **Params**

### PM mental flow

#### Selection

* PM selects initiatives (copied from Central Backlog via formulas)
* Selection is always explicit (row-based)

#### Simple framework scoring

* PM fills RICE / WSJF inputs
* PM clicks **Compute**
* Scores appear immediately in Scoring Inputs

#### Math model scoring (manual)

* PM marks initiative as using math model
* Initiative appears in Math Models tab
* PM writes/edits formula
* PM triggers parameter seeding
* PM fills parameter values
* PM clicks **Compute**
* Scores appear in Scoring Inputs

#### Math model scoring (LLM-assisted)

* PM requests LLM suggestion
* PM reviews/edits formula
* PM confirms
* Parameter seeding happens
* PM fills parameter values
* PM clicks **Compute**
* Scores appear in Scoring Inputs

### Key constraints & nuances

* Scoring Inputs is the **single comparison surface**
* Math model flow intentionally includes human pause
* LLM is an assistant, never authoritative
* All operations are **selection-based**
* This job is exploratory, not publishing

### Implementation Status (V1) ✅

- **Action**: `pm.score_selected`
- **Orchestration**: Single ActionRun with server-side flow coordination
- **Backend flows**: Executes sync → `flow3.compute_all_frameworks` → `flow3.write_scores`
- **Selection scope**: Operates only on selected `initiative_keys`; blank keys skipped and counted as `skipped_no_key`
- **Tab-aware**: Defaults to Scoring_Inputs; can target other Product Ops tabs
- **Per-row status**: Uses `write_status_to_sheet` for Status column writes (sync errors, compute errors, write errors, success)
- **Summary fields**: Returns `selected_count: 0`, `failed_count: 0` on early bail; accurate counts on success
- **Error handling**: Best-effort status writes; captures errors in ActionRun result
- **Sheet context**: Backend uses settings-based defaults if omitted

---

## PM Job #3 — Change active scoring framework (local only)

### PM intent

> “I changed the active framework — show me the new scores.”

### Sheet surface

* Either:

  * **Scoring Inputs**, or
  * **Central Backlog**

### Agreed behavior (critical decision)

* Changing Active Scoring Framework affects **only the current sheet**
* No implicit cross-sheet propagation

Examples:

* Change in Scoring Inputs → only Scoring Inputs updates
* Change in Central Backlog → only Central Backlog updates

### What this job does

* Switches which already-computed framework scores are *represented*
* Copies per-framework scores into representative fields

### What this job does NOT do

* Does not recompute scores
* Does not seed params
* Does not sync other sheets

### Nuances

* Must feel fast and safe
* Highly reversible
* Used frequently for exploration

Publishing to Central Backlog is a **separate explicit job**.

### Implementation Status (V1) ✅

- **Action**: `pm.switch_framework`
- **Orchestration**: Single ActionRun enqueued via worker
- **Backend flows**: Executes Flow3 sync → `activate_scoring_frameworks` → write scores
- **Selection scope**: Operates on selected `initiative_keys`; skips blank keys
- **Local-only behavior**: Updates only the current sheet (no cross-sheet propagation)
- **Per-row status**: Uses `write_status_to_sheet` for Status column writes (sync errors, activate errors, write errors, success)
- **Summary fields**: Returns `selected_count: 0` on early bail; accurate `selected_count`, `saved_count`, `failed_count` on success
- **No recompute**: Fetches already-computed scores; does not trigger new scoring computation
- **Tab-aware**: Works with both Scoring_Inputs and Central Backlog

---

## PM Job #4 — Save changes from this tab (selected rows)

### PM intent

> “I edited some values — save them.”

### Sheet surfaces

* Scoring Inputs
* Math Models
* Params
* Central Backlog

### Agreed behavior (V1)

* Save is **row-based and selection-based**
* PM selects the rows they want to save
* PM can select all rows to emulate whole-tab save

### Column handling rules (important)

* Columns with DB mapping:

  * Saved to system
* Columns without DB mapping:

  * Ignored silently
* Computed/output columns:

  * Treated as read-only
  * Never written back

### Tab-aware semantics

The same Save button exists everywhere, but meaning differs:

* Scoring Inputs → save scoring inputs
* Math Models → save math models
* Params → save parameters
* Central Backlog → save editable backlog fields only

### Concurrency stance (explicitly agreed)

* V1 uses **row-level snapshot saving**
* Non-conflicting row edits are preserved
* If two PMs edit the same row:

  * Last save wins for that row
* Patch-based (cell-level) saving deferred to later versions

### Implementation Status (V1) ✅

- **Action**: `pm.save_selected`
- **Orchestration**: Single ActionRun with tab-aware branching logic
- **Tab detection**: Exact config matches (`settings.PRODUCT_OPS.mathmodels_tab`, `params_tab`, `scoring_inputs_tab`) with substring fallback for backlog
- **Branch logic**:
  - **MathModels tab**: Syncs via `MathModelSyncService.sync_sheet_to_db()`
  - **Params tab**: Syncs via `ParamsSyncService.sync_sheet_to_db()`
  - **Central Backlog**: Updates via `backlog_update_with_keys()` (Flow 1)
  - **Scoring_Inputs**: Syncs via `run_flow3_sync_productops_to_db()`
- **Selection scope**: Operates only on selected `initiative_keys`; skips blank keys (counted as `skipped_no_key`)
- **Per-row status**: Uses `write_status_to_sheet` for Status column writes across all branches
- **Summary fields**: Returns `selected_count`, `saved_count`, `failed_count: max(0, selected - saved)`, `skipped_no_key`
- **Early bail**: Includes `selected_count: 0`, `failed_count: 0` when no valid keys selected
- **Direct DB writes**: Central Backlog saves write directly to Initiative table
- **Audit**: Uses `ActionRun.requested_by` for execution tracking

---

## 4.1 Additional PM Jobs (V2 — Math Models)

### PM Job #5 — Suggest math model via LLM (new)

**PM intent**

> “Give me a draft formula and assumptions for this initiative.”

**Sheet surface**

* **MathModels tab** (selected initiatives)

**Behavior**

* Calls LLM to propose a draft formula and notes for rows without a formula.
* Writes only to LLM-owned columns on MathModels: `llm_suggested_formula_text`, `llm_notes`, and sets `suggested_by_llm`.
* Never overwrites user-owned columns: `formula_text`, `assumptions_text`, `approved_by_user`.
* Guard: If initiative context is thin (no problem statement, no impact description, no metric) and `model_prompt_to_llm` is empty, the job skips with "SKIPPED: Insufficient context".
* Status per row: OK suggested / SKIPPED (formula exists or no key or insufficient context) / FAILED (LLM or sheet error).

**Usage pattern**

1) Select rows on MathModels with empty `formula_text`.
2) Run `pm.suggest_math_model_llm`.
3) Review/edit: copy the suggestion into `formula_text` and add/edit `assumptions_text`; set `approved_by_user = TRUE` before seeding.

### PM Job #6 — Seed math params (renamed from pm.build_math_model)

**PM intent**

> “Take the approved formula and create parameter rows to fill.”

**Sheet surface**

* **MathModels tab** for selection, writes new rows to **Params tab**.

**Behavior**

* Validates `formula_text`, extracts identifiers, and seeds Params rows with LLM metadata (values empty).
* Skips rows without approval or without formula.
* Status per row: OK seeded / SKIPPED (not approved/no formula/no key) / FAILED (validation or write error).
* Sheet-first: DB persistence happens later via `pm.save_selected` on Params.

**Usage pattern**

1) Approved formula on MathModels (`approved_by_user = TRUE`).
2) Run `pm.seed_math_params` (seeds metadata + empty values).
3) Fill param values on Params tab.
4) Run `pm.save_selected` (Params) → `pm.score_selected`.

**Rationale for rename**

* Old name `pm.build_math_model` implied scoring; the job only seeds parameters. `pm.seed_math_params` is explicit and matches the PM mental model.

## 5.1 Global Implementation Status (V2)

**Implemented**

- ✅ V1 jobs (4): backlog_sync, score_selected, switch_framework, save_selected
- ✅ V2 math-model jobs added to backend + registry: suggest_math_model_llm, seed_math_params

**Pending polish**

- LLM prompt + sheet writer wiring for `pm.suggest_math_model_llm` suggestions.
- Apps Script menu items for both math-model jobs.
- End-to-end tests for both Path A (manual formula) and Path B (LLM → approve → seed → save → score).

---

## See Also

- Math Model Workflow (V2) — Column ownership, two-step flow, timeline, guards, and troubleshooting: [phase_4.5_sheetnative_execution/PHASE_4.5_CHECKPOINT.md](productroadmap_sheet_project/docs/phase_4.5_sheetnative_execution/PHASE_4.5_CHECKPOINT.md)
- PM Jobs Cheatsheet — Quick references for all jobs including math model steps: [phase_4.5_sheetnative_execution/phase_4.5_pm_cheatsheet.md](productroadmap_sheet_project/docs/phase_4.5_sheetnative_execution/phase_4.5_pm_cheatsheet.md)

### Backend (action_runner.py)
- Consistent ActionRun/worker pattern across all 6 PM jobs.
- Status abstraction + summary semantics unchanged; new jobs return the same fields (selected/ok/skipped/failed).
- `pm.seed_math_params` renamed and registered; `pm.suggest_math_model_llm` scaffolded with TODO prompt/writer hook.

### Frontend (Apps Script)
- Existing menus for 4 jobs remain.
- TODO: Add MathModels tab menu items for `pm.suggest_math_model_llm` and `pm.seed_math_params`.

**Validation**
- Backend static checks pass; registry updated.
- LLM prompt/write path for suggest job still to wire.

**Checkpoint document:** See [PHASE_4.5_CHECKPOINT.md](PHASE_4.5_CHECKPOINT.md); V2 updates are additive (math-model jobs).

---

## 5. Explicit Non-Goals for Step 4.5

Step 4.5 intentionally does NOT include:

* Optimization or portfolio selection
* Automatic cross-sheet propagation
* Auto-save on every edit
* Cell-level diff tracking
* User-level permissions
* Real-time collaboration conflict resolution

---

## 6. Why This Cut Is Correct

This design:

* Matches real PM workflows
* Keeps UX predictable and explicit
* Protects system integrity
* Avoids premature complexity
* Creates a clean foundation for Step 5 (Optimization)

---

