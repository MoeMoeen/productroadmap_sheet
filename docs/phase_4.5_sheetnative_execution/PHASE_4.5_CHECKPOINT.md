# Phase 4.5 Checkpoint — Sheet-Native Execution & Control Plane (V1)

**Status: ✅ COMPLETE**

**Date: 28 December 2025**

---

## Overview

Phase 4.5 introduces a **PM-centric execution layer** that makes Google Sheets the primary UI for all workflows. PMs can now run the core product operations without terminal access, using custom menu items connected to a backend Action API powered by an async worker process.

This completes the hard prerequisite for Phase 5 (Portfolio Optimization).

---

## What's Implemented (End-to-End)

### ✅ Backend Execution & Control Plane

**Action API (HTTP Layer)**
- `POST /actions/run` — Enqueue action + return `run_id` immediately
- `GET /actions/run/{run_id}` — Poll for status, result, error

**ActionRun Ledger (DB Layer)**
- Execution audit trail with:
  - `run_id` (unique identifier per execution)
  - `action` (e.g., `pm.score_selected`)
  - `status` (queued → running → success/failed)
  - `payload_json` (full request context)
  - `result_json` (summary + per-row outcomes)
  - `error_text` (if failed)
  - `started_at`, `finished_at`, `requested_by`
  - `spreadsheet_id` (for multi-sheet contexts)

**Worker Process**
- Continuously claims queued ActionRun rows
- Executes orchestrated backend flows
- Single ActionRun per PM job (no nested enqueues)
- Best-effort per-row Status writes
- Atomic result capture

**Action Registry (15 total)**
- Flow 0–4 actions (legacy, for future use)
- PM Jobs #1–4 (pm.backlog_sync, pm.score_selected, pm.switch_framework, pm.save_selected)

---

### ✅ PM Jobs (V1)

All 4 PM jobs implemented in both backend and UI.

#### PM Job #1: `pm.backlog_sync`
**Intent**: "See latest intake initiatives in Central Backlog"

- **Scope**: All initiatives (no selection)
- **Backend orchestration**: 
  - Flow 1 full sync: intake sync → backlog update → backlog regeneration
- **UI**: Central Backlog sheet menu item
- **Summary fields**: `updated_count`, `cells_updated`
- **Status writes**: Per-row Status column in Central Backlog

#### PM Job #2: `pm.score_selected`
**Intent**: "Deep-dive and score selected initiatives"

- **Scope**: Selected `initiative_keys` only; blank keys skipped
- **Backend orchestration**:
  1. Sync inputs from sheet → DB
  2. Compute all frameworks (RICE, WSJF, Math Model)
  3. Write scores back to Scoring_Inputs sheet
  4. Update per-row Status
- **UI**: ProductOps Scoring_Inputs menu item
- **Summary fields**: `selected_count`, `saved_count`, `failed_count`, `skipped_no_key`
- **Status writes**: Per-row Status column

#### PM Job #3: `pm.switch_framework`
**Intent**: "Change active scoring framework (local only)"

- **Scope**: Selected `initiative_keys`; skips blank keys
- **Behavior**: Updates only the current sheet (no cross-sheet propagation)
- **Backend orchestration**:
  - **Scoring_Inputs branch**: Sync → activate → write active scores → Status
  - **Central Backlog branch**: Backlog update → activate → full backlog sync → Status
- **UI**: ProductOps Scoring_Inputs menu item (Backlog branch supported when called from backlog)
- **Summary fields**: `selected_count`, `saved_count`, `failed_count`
- **Key detail**: No recompute; copies already-computed framework-specific scores to active fields

#### PM Job #4: `pm.save_selected`
**Intent**: "Save selected edits (tab-aware)"

- **Scope**: Selected `initiative_keys`; skips blank keys
- **Tab-aware branching** (detects via exact config match + substring fallback):
  - **Scoring_Inputs**: Syncs scoring inputs via Flow3
  - **MathModels**: Syncs math models via MathModelSyncService
  - **Params**: Syncs parameters via ParamsSyncService
  - **Central Backlog**: Updates initiatives via Flow1
- **UI**: ProductOps menu (handles all tabs dynamically)
- **Summary fields**: `selected_count`, `saved_count`, `failed_count: max(0, selected - saved)`, `skipped_no_key`
- **Status writes**: Per-row Status column across all branches

---

### ✅ Provenance Model (V1)

**Three-tier provenance**:

1. **Flow-level (DB)**: Preserved in `Initiative.updated_source` and `Initiative.scoring_updated_source`
   - Example: `flow1.backlog_update`, `flow3.compute_all_frameworks`

2. **PM-job level (ActionRun)**: PM job tokens stored in ActionRun action field
   - Example: `pm.score_selected`, `pm.switch_framework`

3. **Sheet-level (Updated Source column)**: Last writer and token
   - May include PM job tokens when PM job writes rows
   - Maintains audit trail visible in Sheets

---

### ✅ Apps Script UI (V1)

**Architecture**: Bound Apps Script menus connected to FastAPI backend via shared-secret HTTP authentication.

**ProductOps Sheet Menus** (🧠 Roadmap AI)
- Score selected initiatives → `pm.score_selected`
- Switch framework → `pm.switch_framework`
- Save selected (tab-aware) → `pm.save_selected`

**Central Backlog Sheet Menu** (🧠 Roadmap AI)
- See latest intake → `pm.backlog_sync`

**UI Implementation Details**
- **config.gs**: Centralized API URL + secret management
- **api.gs**: Low-level HTTP helpers (POST /actions/run, GET /actions/run/{run_id})
- **selection.gs**: Extract `initiative_keys` from selected rows
- **menu.gs**: Register menu items on sheet open
- **ui_*.gs**: Individual PM job handlers (ui_scoring.gs, ui_framework.gs, ui_save.gs, ui_backlog_sync.gs)
- **Error handling**: Try/catch blocks surface API errors in-sheet via toast
- **Polling (optional)**: Apps Script can poll backend until completion for UX feedback

**Authentication**
- Shared secret header: `X-ROADMAP-AI-SECRET`
- Stored in Apps Script Script Properties (not hardcoded)
- Validated by FastAPI dependency

**Deployment (V1)**
- Bound to individual Google Sheets
- Uses ngrok for local development
- Later: Migrate to Google Workspace Add-on for SaaS distribution

---

## Technical Highlights

### Selection Handling
- Apps Script reads selected rows and extracts `initiative_key` column
- Backend receives `initiative_keys` list in scope payload
- Blank keys are filtered and counted as `skipped_no_key`
- Deduplicated before backend processing

### Tab-Aware Branching (pm.save_selected)
- **Exact matches**: `settings.PRODUCT_OPS.mathmodels_tab`, `params_tab`, `scoring_inputs_tab`
- **Substring fallback**: `"backlog"` in tab name (case-insensitive)
- Allows same PM job to intelligently route to correct sync service

### Status Writer Abstraction
- Generic `write_status_to_sheet` alias (delegates to `write_status_to_productops_sheet`)
- Used consistently across all PM jobs
- Supports any tab with a Status/Last Run Status column
- Safely no-ops if column missing

### Summary Semantics
- Early bail returns: `selected_count: 0`, `failed_count: 0`, `skipped_no_key: 0`
- Success paths: Accurate counts + `failed_count: max(0, selected_count - saved_count)`
- Consistent across all PM jobs for _extract_summary compatibility

### Active Score Mapping
- DB schema uses generic `value_score`, `effort_score`, `overall_score` (no "active_" prefix)
- Sheet schema expects `active: value score`, `active: effort score`, `active: overall score` columns
- **Fix applied**: SCORE_FIELD_TO_HEADERS maps DB fields to sheet column aliases
- pm.switch_framework now correctly writes active scores to sheet

---

## Validation & Testing

✅ **Backend Validation**
- Static analysis: No Pylance errors in action_runner.py
- Imports verified: All dependencies resolve
- Action registry: 15 actions registered correctly
- Early bail fields: All PM jobs include required summary fields

✅ **Manual Testing (Swagger)**
- pm.score_selected: Successfully computes and writes scores
- pm.switch_framework: Correctly updates DB + writes active scores to sheet
- pm.save_selected: Tab-aware routing works; Status column updates accurate
- Error handling: API errors surface cleanly; ActionRun captures error_text

✅ **Apps Script Testing (Sheet UI)**
- Menu items appear on sheet open
- Selection extraction: Correctly identifies initiative_keys from selected rows
- API calls: Shared secret header sent correctly
- Response parsing: run_id extracted and displayed
- Error handling: API errors show in toast alerts

---

## Known Limitations & Future Work

### V1 Limitations
- Single selection mode (no multi-range selections in Apps Script)
- No cell-level diff tracking (row-level snapshot saves)
- No user-level permissions (all users see all initiatives)
- No real-time collaboration conflict resolution
- pm.backlog_sync uses full refresh (not incremental; will optimize in V2)

### V2 Roadmap
- Multi-range selection support
- Cell-level diff tracking for smarter saves
- User identity via OAuth (stronger than current best-effort email)
- Incremental backlog sync (delta-based vs full refresh)
- Control/RunLog tab (live dashboard of execution history)
- Workflow triggers & automation

### Phase 5 Prerequisites Met
✅ Sheet-native execution layer complete

✅ PM jobs vetted end-to-end

✅ Provenance model in place

✅ Audit trail via ActionRun

Ready to proceed with Portfolio Optimization Engine.

---

## Files Changed (Phase 4.5)

### Backend
- `app/services/action_runner.py`: Action registry + orchestration + 4 PM jobs
- `app/sheets/productops_writer.py`: Generic `write_status_to_sheet` alias
- `app/sheets/models.py`: Fixed SCORE_FIELD_TO_HEADERS mapping for active scores
- `app/api/routes/actions.py`: POST /actions/run, GET /actions/run/{run_id}
- `app/db/models/action_run.py`: ActionRun ledger schema

### Frontend (Apps Script)
- `ProductOps Sheet`:
  - config.gs
  - api.gs
  - selection.gs
  - menu.gs
  - ui_scoring.gs (pm.score_selected)
  - ui_framework.gs (pm.switch_framework)
  - ui_save.gs (pm.save_selected)

- `Central Backlog Sheet`:
  - config.gs
  - api.gs
  - selection.gs
  - menu.gs
  - ui_backlog_sync.gs (pm.backlog_sync)

### Documentation
- `docs/projectscope.md`: Marked Phase 4.5 as COMPLETED
- `docs/phase_4.5_sheetnative_execution/phase_4.5_pm_jobs.md`: Updated implementation status
- `docs/phase_4.5_sheetnative_execution/phase_4.5_sheenative_execution.md`: Updated status + next steps
- `docs/phase_4.5_sheetnative_execution/PHASE_4.5_CHECKPOINT.md`: This file

---

## Next Steps

**Phase 4.5 is feature-complete. No further work planned unless bugs surface.**

**To proceed to Phase 5 (Portfolio Optimization)**:

1. Review this checkpoint
2. Gather feedback from stakeholders (PMs, engineers)
3. Document any pain points or missing features for V2
4. Begin Phase 5: Portfolio Optimization Engine design + implementation

**Optional V1 polish** (if time permits):
- Add Control/RunLog tab to ProductOps sheet (nice-to-have for ops visibility)
- Implement optional polling in Apps Script for better UX feedback
- Add more granular status messages (e.g., "syncing", "computing", "writing")

---

## Summary

**Phase 4.5 is the foundation for PM-driven product operations.** PMs can now run all core workflows from Google Sheets without terminal access. The system is audited, versioned, and ready for the optimization layer in Phase 5.

