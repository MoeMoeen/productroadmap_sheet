Below is a **clean, accurate, comprehensive Step 4.5 document**, written exactly to **capture what we have agreed so far**, no more and no less.

---

# Step 4.5 — Sheet-Native Execution Layer & PM Jobs (V1)

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

We explicitly limit V1 to **four PM jobs**.
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

### Implementation Conclusions (V1)

- **Server-side orchestration:** A single PM job action `pm.score_selected` runs sync → compute → write on the backend (no Apps Script client-side chaining).
- **Selection scope:** Operates only on selected `initiative_keys`. Blank keys are skipped and counted as `skipped_no_key` in ActionRun summary.
- **Auto-sync before compute:** Latest sheet inputs are synced to DB first, then `flow3.compute_all_frameworks` runs, followed by `flow3.write_scores` to Scoring Inputs.
- **Per-row status:** Write short, row-scoped messages to a dedicated `Status` column (e.g., `OK`, `FAILED: <reason>`, `SKIPPED: missing key`). Do not use `Updated Source` for status.
- **Sheet context defaults:** If Apps Script omits `sheet_context`, backend uses settings-based defaults (preferred that Apps Script still sends it in production).

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

### Implementation Conclusions (V1)

- **Local-only switch:** Changing the Active Scoring Framework updates only the current sheet (Scoring Inputs or Central Backlog). No cross-sheet propagation.
- **Activated scores in Backlog:** Central Backlog shows only the activated framework’s scores as native columns. Other framework scores appear via formulas referencing Scoring Inputs.
- **No recompute:** Switching framework fetches already-computed and approved scores; it does not trigger recomputation.
- **ActionRun orchestration:** Even though lightweight, this PM job enqueues an ActionRun for consistency and audit. Per-row `Status` may be written on failures only.

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

### Implementation Conclusions (V1)

- **Direct DB writes:** Saves from Central Backlog write directly to the Initiative table.
- **Audit:** Use `ActionRun.requested_by` (best-effort `reported_by_email` via Apps Script in V1). Later versions can adopt OAuth for stronger identity.
- **Per-row status:** Write short results to the tab’s `Status` column; keep `Updated Source` strictly for provenance.
- **Provenance model:** ActionRun uses PM job tokens (e.g., `pm.save_selected`). DB row-level provenance remains flow-based (e.g., `flow3.compute_all_frameworks`). Sheet `Updated Source` may include PM job tokens when the PM job writes rows.

---

## 5.1 Global Implementation Conclusions (V1)

- **ActionRun/Worker for all PM jobs:** Every PM job enqueues an ActionRun and executes via the worker for consistent UX, audit, and to avoid Apps Script timeouts.
- **Selection payload:** Apps Script passes `initiative_keys` from sheet selection. Backend skips blanks, annotates per-row `Status`, and records `skipped_no_key` in summary.
- **Status column:** Use a dedicated `Status` (or `Last Run Status`) column per tab for outcome messages. Do not overload `Updated Source`.
- **Sheet context defaults:** Backend provides sensible defaults when `sheet_context` is missing; Apps Script should still send it in production.
- **Provenance tokens:** Add PM job tokens (`pm.backlog_sync`, `pm.score_selected`, `pm.switch_framework`, `pm.save_selected`) for ActionRun and (optionally) sheet-level `Updated Source`. Keep DB row provenance tied to underlying flow tokens.

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

