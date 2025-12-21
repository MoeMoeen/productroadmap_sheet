Perfect — here is the **clean, corrected, internally consistent, implementation-ready version** of the plan, incorporating all agreed fixes and refinements.

I’m presenting it as a **final reference doc** you can treat as canonical going forward.

---

# Sheet-Native Execution & Control Plane

**(Pre-Optimization Phase – Final Refined Version)**

---

## 0) Context & Goal

PMs must be able to operate the entire roadmap lifecycle **from Google Sheets**, without terminals.

They need a **sheet-native execution/control plane** that supports:

* Buttons / menus
* Run-one-initiative actions
* Run-batch actions
* Optional automatic triggers (guarded)
* Guardrails (approved rows only, etc.)
* Near-real-time scenario recalculation loops
* Clear provenance & logs
* Safe, idempotent execution

This control plane is a **hard prerequisite** before introducing the optimization engine.

---

## What PMs must be able to do

From **ProductOps** sheets:

* Run **Flow 3**: compute scores & write scores back
* Run **Flow 2**: activate scoring framework
* Run **Flow 1**: sync Central Backlog (DB → Sheet)
* Run **Flow 4**: suggest / seed / sync math models & params

From **Intake** sheets:

* Run **Flow 0**: intake sync (Sheet → DB)

All with:

* ✅ one-click actions
* ✅ visible run status + results
* ✅ no terminal usage
* ✅ idempotent & safe execution
* ✅ canonical provenance + structured logs

---

## 1) Architecture Overview

### A) UI Layer — Google Apps Script (Sheets-native)

Embedded in **ProductOps** and **Intake** sheets.

Provides a custom menu:

**`Roadmap AI`**

Menu actions (examples):

* Compute scores (all frameworks)
* Write scores back to ProductOps
* Activate framework (AUTO / forced)
* Sync Central Backlog
* Suggest Math Models (selected rows)
* Seed Params (approved models)
* Sync MathModels → DB
* Sync Params → DB
* Sync Intake → DB

Each menu item:

* Collects scope from the sheet
* Sends a **single HTTP request** to backend
* Writes run status to a Control tab
* Polls for completion

---

### B) Backend Layer — Action API (single entry point)

One canonical endpoint:

```
POST /actions/run
```

This endpoint:

* Validates action + scope
* Enqueues an async job
* Returns a `run_id` immediately

Action → implementation mapping:

| Action                         | Backend mapping                           |
| ------------------------------ | ----------------------------------------- |
| `flow3.compute_all_frameworks` | `ScoringService.compute_all_frameworks()` |
| `flow3.write_scores`           | `run_flow3_write_scores_to_sheet()`       |
| `flow2.activate`               | `run_scoring_batch()`                     |
| `flow1.backlog_sync`           | `run_all_backlog_sync()`                  |
| `flow4.suggest_mathmodels`     | `run_math_model_generation_job()`         |
| `flow4.seed_params`            | `run_param_seeding_job()`                 |
| `flow4.sync_mathmodels`        | `MathModelSyncService.sync_sheet_to_db()` |
| `flow4.sync_params`            | `ParamsSyncService.sync_sheet_to_db()`    |
| `flow0.intake_sync`            | `run_sync_all_intake_sheets()`            |

---

### C) Status Surface — Control / RunLog Tab (Sheets)

A dedicated tab in **ProductOps** (and optionally Intake) that shows:

* timestamp
* run_id
* action
* scope summary
* status (`queued / running / success / failed`)
* started_at
* finished_at
* result summary (counts, updates)
* error snippet (if any)

This is critical for:

* PM confidence
* auditability
* “did it run?” clarity

---

## 2) Execution Model (Final Choice)

### ✅ V1.5 — Async Job Runner (from day 1)

**Chosen approach**

Flow:

1. Apps Script → `POST /actions/run`
2. Backend enqueues job → returns `run_id`
3. Apps Script writes run row in Control tab
4. Apps Script polls `GET /actions/run/{run_id}`
5. Status + results update live

Why:

* Avoids Apps Script timeouts
* Supports long-running jobs (LLM, compute-all, backlog sync)
* Scales cleanly
* Minimal extra complexity

---

## 3) API Contract (Stable)

### POST `/actions/run`

```json
{
  "action": "flow3.write_scores",
  "scope": {
    "type": "initiative_keys",
    "initiative_keys": ["INIT-000017", "INIT-000021"]
  },
  "sheet_context": {
    "spreadsheet_id": "...",
    "tab": "Scoring_Inputs"
  },
  "options": {
    "only_missing": true,
    "commit_every": 100,
    "force": false,
    "limit": 20
  },
  "requested_by": {
    "ui": "apps_script",
    "user_email": "optional"
  }
}
```

Response:

```json
{
  "run_id": "run_20251221_123456_abcd",
  "status": "queued"
}
```

---

### GET `/actions/run/{run_id}`

```json
{
  "run_id": "...",
  "status": "success",
  "started_at": "...",
  "finished_at": "...",
  "result": {
    "updated": 11,
    "cells_updated": 79
  },
  "error": null
}
```

---

## 4) Scope Selection Patterns (v1)

Supported scope types:

### 1) Selected rows

* Apps Script reads selected range
* Extracts `initiative_key` column values

### 2) All rows

* Used for compute-all, backlog sync
* Explicitly labeled as “dangerous”

### 3) Filtered scope

* Well-known predicates only (v1):

  * `approved_by_user == TRUE`
  * `use_math_model == TRUE`
* No arbitrary expressions yet

Example:

```json
{
  "type": "filter",
  "predicate": {
    "column": "use_math_model",
    "op": "==",
    "value": true
  }
}
```

---

## 5) Security (v1 decision)

### ✅ Start with Option A — Shared Secret Header

Apps Script sends:

```
X-ROADMAP-AI-SECRET: <value from Script Properties>
```

Backend validates against env var.

* Fast
* Sufficient for v1
* Can upgrade later to IAP / OAuth

---

## 6) Codebase Integration

You already have:

* jobs (`app/jobs/*`)
* services (`app/services/*`)
* writers/readers
* provenance tokens

### New modules to add

#### A) API

* `app/api/actions.py`
* `app/schemas/actions.py`

#### B) Runner

* `app/services/action_runner.py`

  * validates action
  * maps to callable
  * enqueues job
  * executes safely
  * captures results/errors

#### C) Job Ledger (recommended)

DB table: `ActionRun`

Fields:

* run_id
* action
* status
* payload_json
* result_json
* error_text
* started_at
* finished_at
* requested_by
* spreadsheet_id

This becomes your **execution audit log**.

---

## 7) Provenance & Logging Rules (Final)

* **DB provenance**

  * `Initiative.updated_source = token(Provenance.X)`
  * scoring updates also stamp:

    * `scoring_updated_source`
    * `scoring_updated_at`

* **Sheet provenance**

  * Each tab’s `Updated Source` column = last writer of that tab

* **Action runs**

  * `run_id` lives in:

    * logs
    * `ActionRun` table
    * Control tab
  * **Do not** embed run_id in provenance tokens

---

## 8) Minimum Lovable Action Set (v1)

Implement these first:

1. `flow3.compute_all_frameworks`
2. `flow3.write_scores`
3. `flow2.activate`
4. `flow1.backlog_sync`
5. `flow4.suggest_mathmodels`
6. `flow4.seed_params`
7. `flow0.intake_sync`

Everything else is optional later.

---

## 9) What This Unlocks Immediately

* End-to-end scoring without engineers
* Rapid math-model iteration + recalculation
* Framework activation & backlog reflection
* Real “what-if” scenario loops
* PM-driven planning, not ops-driven

This makes the **optimization engine viable**.

---

## Next Execution Step

We proceed in this order:

**→ Implement Option 3: Job table + async runner first**

Then:

1. Backend Action API
2. Apps Script UI
3. Control tab rendering

