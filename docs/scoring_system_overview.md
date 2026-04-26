# Scoring System Overview

*As of April 2026.*

---

## What scoring does

Every initiative in the backlog gets a set of numeric scores:
- **`value_score`** – benefit / desirability
- **`effort_score`** – cost / size
- **`overall_score`** – primary sortable prioritization metric

These three "active" fields are what the optimization engine sees. How they are produced is determined by the **scoring framework** chosen for each initiative.

---

## Supported frameworks

Three frameworks are available today (defined in `app/services/product_ops/scoring/interfaces.py`):

| Framework | Enum value | Formula |
|---|---|---|
| **RICE** | `"RICE"` | `(Reach × Impact × Confidence) / Effort` |
| **WSJF** | `"WSJF"` | `Cost of Delay / Job Size` where `CoD = Business Value + Time Criticality + Risk Reduction` |
| **Math Model** | `"MATH_MODEL"` | Custom formula per initiative (Python-safe expression evaluated via `safe_eval`) |

Each framework is implemented as a standalone engine class in `app/services/product_ops/scoring/engines/`:
- `rice.py` → `RiceScoringEngine`
- `wsjf.py` → `WsjfScoringEngine`
- `math_model.py` → `MathModelScoringEngine`

All engines share the same interface: they accept a `ScoreInputs` object and return a `ScoreResult`.

---

## Input data

Inputs come from two sources:

1. **`Scoring_Inputs` Google Sheet tab** – a wide, namespaced sheet where columns follow the pattern `FRAMEWORK: Param` (e.g., `RICE: Reach`, `WSJF: Job Size`). The `ScoringInputsReader` parses this tab and maps columns into `ScoreInputs` for each initiative.

2. **`InitiativeParam` DB table** – normalized one-row-per-parameter storage. RICE, WSJF, and Math Model params can all live here. Math Model params are sourced from this table when evaluating formulas.

---

## Math Model specifics

An initiative can have **one or more math models** (`InitiativeMathModel` DB table, 1:N per initiative). Each model:
- has a `formula_text` (a Python-style expression that must assign `value`, and optionally `effort` and `overall`)
- targets a specific `target_kpi_key`
- can be marked `is_primary` to be used as the representative score for display
- must have `approved_by_user = True` to be executed; unapproved models are skipped with a warning
- may be flagged `suggested_by_llm = True` when the LLM generated the formula or parameters

The `MathModelScoringEngine` uses `safe_eval` to evaluate the formula in a sandboxed environment. Missing parameters cause a scored-but-warned result, not a hard error.

When Math Model is the active framework, individual per-model `computed_score` values are also written back to each `InitiativeMathModel` row, which in turn feeds the **KPI contribution** calculation.

---

## LLM's role

The LLM (`app/llm/scoring_assistant.py`) is a **suggestion assistant only**:
- Suggests math model formulas, assumptions, and parameter values
- Results land in the DB as `suggested_by_llm = True` / `approved_by_user = False`
- A PM must explicitly approve before the formula is executed
- The LLM never directly sets the final active scores

---

## Two-phase scoring flow

Scoring is split across two flows:

### Flow 3 – Compute all frameworks (Phase 1)
`ScoringService.compute_all_frameworks()` iterates over every initiative and runs **all three engines**. Results are stored in per-framework columns:
- `rice_value_score`, `rice_effort_score`, `rice_overall_score`
- `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`
- `math_value_score`, `math_effort_score`, `math_overall_score`

The active `value_score` / `effort_score` / `overall_score` fields are **not changed** in this phase. This lets Product Ops see all three framework scores side-by-side for comparison before committing to one.

### Flow 2 – Activate a framework
`ScoringService.activate_all()` (or `activate_initiative_framework()` per initiative) copies the chosen framework's per-framework scores into the active fields and sets `active_scoring_framework`. The PM selects the preferred framework in the ProductOps sheet; Flow 2 makes it the live score.

If per-framework scores are missing at activation time, they are computed on-the-fly before copying.

---

## History / audit

When `SCORING_ENABLE_HISTORY = True` (settings), every scoring run appends an `InitiativeScore` row containing:
- which framework was used
- the raw inputs and intermediate components
- the resulting scores
- LLM and approval flags

This table is append-only and is used for audit trails and score comparisons over time.

---

## Key files

| Path | Role |
|---|---|
| `app/services/product_ops/scoring/interfaces.py` | `ScoringFramework` enum, `ScoreInputs`, `ScoreResult`, `ScoringEngine` protocol |
| `app/services/product_ops/scoring/engines/` | Individual engine implementations (RICE, WSJF, Math Model) |
| `app/services/product_ops/scoring_service.py` | Orchestrator – maps Initiative → ScoreInputs, calls engines, writes back results |
| `app/db/models/scoring.py` | `InitiativeMathModel`, `InitiativeScore`, `InitiativeParam` ORM models |
| `app/sheets/scoring_inputs_reader.py` | Reads the `Scoring_Inputs` Google Sheet tab |
| `app/llm/scoring_assistant.py` | LLM helpers for formula/parameter suggestions |
| `app/jobs/flow2_scoring_activation_job.py` | Job that triggers the Flow 2 activation batch |
