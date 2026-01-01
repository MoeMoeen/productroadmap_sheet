## Step 4.7 — Editable allowlists (paste-ready contracts)

I’m going to give you **tab-by-tab allowlists**, plus:

* **DB target** (which model/fields)
* **who can edit**
* **sync direction**
* **type coercion**
* **hard-fail validations**

These are designed to map cleanly to your existing patterns:

* `*_HEADER_MAP` in `app/sheets/models.py`
* `*_EDITABLE_FIELDS` allowlists used by sync services
* `pm.save_selected` tab-aware routing

---

# 4.7.1 ProductOps → `Metrics_Config` (NEW)

### Purpose

Authoritative UI for:

* single North Star KPI
* strategic KPI set
* KPI definitions (name/unit/description)

### Sync

* **ProductOps/Metrics_Config → DB** (authoritative save)
* Optional: **DB → ProductOps/Metrics_Config** (refresh view later)

### DB target

New DB model (recommended): `OrganizationMetricsConfig` and/or `KPIDefinition` table.
For v1 you can store everything into one table as JSON; but allowlist stays the same.

### Allowlist (columns PM can edit)

```python
METRICS_CONFIG_EDITABLE_FIELDS = {
    "kpi_key",
    "kpi_name",
    "kpi_level",       # north_star | strategic
    "unit",
    "description",
    "is_active",
    "notes",
}
```

### Read-only / backend-owned (must be ignored)

* `run_status`
* `updated_source`

### Type coercion

* `is_active`: bool
* `kpi_level`: enum (`north_star`, `strategic`)
* all others: strings

### Hard validations (save time)

1. Exactly **one** row where `kpi_level == "north_star"` and `is_active == True`
2. `kpi_key` non-empty, unique among rows
3. Active strategic KPIs must be `kpi_level == "strategic"`

---

# 4.7.2 ProductOps → `MathModels` (UPDATED: includes metric chain)

### Purpose

Persist:

* InitiativeMathModel fields
* and Initiative.metric_chain_json (via metric_chain_text)

### Sync

* **ProductOps/MathModels → DB**
* Optional display-only DB → ProductOps/MathModels later

### DB targets

* `InitiativeMathModel` (most columns)
* `Initiative.metric_chain_json` (derived from chain text)

### Allowlist

```python
MATHMODELS_EDITABLE_FIELDS = {
    # existing math model fields PM owns
    "model_name",
    "model_description_free_text",
    "model_prompt_to_llm",
    "assumptions_text",
    "llm_notes",
    "formula_text_final",
    "formula_text_approved",     # approval gate

    # NEW: metric chain authoring surface
    "metric_chain_text",         # PM authored
}
```

### LLM-only / backend-written (ignore on save)

* `llm_suggested_formula_text`
* `llm_suggested_metric_chain_text` (NEW)
* `initiative_key`, `framework`, `version`
* `run_status`, `updated_source`

### Type coercion

* `formula_text_approved`: bool
* `metric_chain_text`: string → parsed into JSON graph

### Hard validations

* If `formula_text_approved == True`:

  * `formula_text_final` must be non-empty and pass `validate_formula`
* For `metric_chain_text`:

  * if present, parse must succeed; if parse fails → **warning in v1**, hard-fail later when we require it.

**Note (important implementation detail)**
Even though this allowlist allows saving `metric_chain_text`, the DB field is `Initiative.metric_chain_json`. The service will:

* parse chain_text → metric_chain_json
* write `metric_chain_json` to Initiative row

---

# 4.7.3 Optimization Center → `Scenario_Config`

### Purpose

Persist `OptimizationScenario` (period + objective mode + capacity + weights)

### Sync

* **OptimizationCenter/Scenario_Config → DB**
* Optional DB → sheet refresh later

### DB target

* `OptimizationScenario`

### Allowlist

```python
OPTIM_SCENARIO_EDITABLE_FIELDS = {
    "scenario_name",
    "period_key",
    "capacity_total_tokens",
    "objective_mode",            # north_star | weighted_kpis | lexicographic
    "objective_weights_json",    # stringified JSON
    "notes",
}
```

### Ignore (read-only)

* `run_status`, `updated_source`

### Type coercion

* `capacity_total_tokens`: float
* `objective_weights_json`: parse JSON (dict[str, float]) OR empty dict when blank
* `objective_mode`: enum

### Hard validations

* `capacity_total_tokens > 0`
* objective_mode in allowed enum
* If `objective_mode == "weighted_kpis"`:

  * weights not empty
  * keys ∈ active strategic KPIs (from Metrics_Config DB)
  * values numeric

---

# 4.7.4 Optimization Center → `Constraints`

### Purpose

Persist reusable constraint rows into `OptimizationConstraintSet`

### Sync

* **OptimizationCenter/Constraints → DB**
* Optional DB → sheet refresh later

### DB target

Option A (v1 pragmatic): store raw rows into `OptimizationConstraintSet` JSON blobs:

* floors_json
* caps_json
* targets_json
* bundles_json (optional)
* exclusions_json (optional)

### Allowlist

```python
OPTIM_CONSTRAINTS_EDITABLE_FIELDS = {
    "constraint_type",   # floor/cap/mandatory/dependency/bundle/target/exclusion
    "dimension",         # market/department/category/global/kpi
    "key",
    "min_tokens",
    "max_tokens",
    "target_kpi_key",
    "target_value",
    "notes",
}
```

### Type coercion

* `min_tokens`, `max_tokens`, `target_value`: float (nullable allowed)
* enums for `constraint_type`, `dimension`

### Hard validations

* constraint_type and dimension must be valid enums
* If constraint_type in {floor, cap}:

  * require dimension in {market, department, category, global}
  * require key (except global)
* If constraint_type == target:

  * require target_kpi_key and target_value
  * target_kpi_key must be in {north star + strategic KPIs}
* If min and max both present: min_tokens ≤ max_tokens

---

# 4.7.5 Optimization Center → `Targets`

### Purpose

Persist KPI targets cleanly (often easier than encoding in Constraints)

### Sync

* **OptimizationCenter/Targets → DB**
* Optional DB → sheet refresh later

### DB target

* Either:

  * separate `OptimizationTargets` table later, OR
  * store inside `OptimizationConstraintSet.targets_json` now

### Allowlist

```python
OPTIM_TARGETS_EDITABLE_FIELDS = {
    "market",           # "GLOBAL" allowed
    "kpi_key",
    "target_value",
    "floor_or_goal",    # floor | goal
    "notes",
}
```

### Type coercion

* `target_value`: float
* `floor_or_goal`: enum

### Hard validations

* kpi_key ∈ {north star + strategic KPIs}
* target_value numeric
* market non-empty (allow "GLOBAL")

---

# 4.7.6 Optimization Center → `Candidates` (OPTIONAL WRITE-BACK)

This is optional because you can keep Candidates as “mostly DB-derived + sheet-only selection”.

If we allow saving from Candidates, it must be **very strict**.

### Sync

* **OptimizationCenter/Candidates → DB** (only a few allowed fields)
* DB → OptimizationCenter/Candidates (refresh)

### Allowlist (strict)

```python
OPTIM_CANDIDATES_EDITABLE_FIELDS = {
    # Only fields that are truly initiative attributes and safe to edit here
    "is_optimization_candidate",
    "candidate_period_key",
    "engineering_tokens",
    "scope_mode",
    "market",
    "department",
    "category",
    "is_mandatory",
    "mandate_reason",
    "bundle_key",
    "prerequisite_keys",
    "exclusion_keys",
    "synergy_group_keys",
}
```

### Explicitly NOT persisted (sheet-only)

* `is_selected_for_run`
* `notes`
* `run_status`
* `updated_source`

### Hard validations (same as Backlog saves)

* mandatory → mandate_reason required
* prerequisite/exclusion keys resolvable
* engineering_tokens >= 0

---

# 4.7.7 Where these constants live

**Put these in:**

* `app/sheets/models.py`

Near your existing:

* `PARAMS_HEADER_MAP`
* `MATHMODELS_HEADER_MAP`
* etc.

And you will add:

* `METRICS_CONFIG_HEADER_MAP` (new)
* `OPTIM_*_HEADER_MAP` (new)
* plus these `*_EDITABLE_FIELDS` sets.

---

# 4.7.8 Next implementation mapping (so you can see how it plugs in)

* `pm.save_selected` tab router in `action_runner.py` gains:

  * branch for `Metrics_Config` → `MetricsConfigSyncService.sync_sheet_to_db(...)`
* `MathModelSyncService` is extended to accept:

  * `metric_chain_text` parsing and writing to Initiative.metric_chain_json
* New services:

  * `OptimizationScenarioSyncService`
  * `OptimizationConstraintsSyncService`
  * `OptimizationTargetsSyncService`
  * (optional) `OptimizationCandidatesSyncService`

Each service:

* reads rows with a Reader
* filters selection if initiative_keys provided (where applicable)
* applies allowlist mapping
* upserts DB
* writes per-row status back

---











------------------------------------------------------------------------------------------------------------------------------------------------------------



Got it on all 3 notes ✅

* I’ll include **`updated_at`** as read-only on **all tabs** (with alias variants).
* I’m aligned that **MathModels uses `formula_text` and `approved_by_user`** (not `formula_text_final` / `formula_text_approved`). Good catch.
* For **`weighted_kpis`**, allowed KPI keys = **North Star + active Strategic KPIs** (not just strategic). ✅

Below are **paste-ready header maps** in the exact “`*_HEADER_MAP` dict of canonical_field -> [aliases...]” style.

---

## Common alias sets (optional helpers)

You can paste these at top of `app/sheets/models.py` to reuse in maps.

```python
UPDATED_SOURCE_ALIASES = [
    "updated_source", "Updated Source", "UPDATED SOURCE", "UpdatedSource",
    "last_updated_source", "Last Updated Source",
]

UPDATED_AT_ALIASES = [
    "updated_at", "Updated At", "UPDATED AT", "UpdatedAt",
    "last_updated_at", "Last Updated At",
]

RUN_STATUS_ALIASES = [
    "run_status", "Run Status", "RUN STATUS",
    "status", "Status", "STATUS",
    "last_run_status", "Last Run Status",
]
```

---

# 1) ProductOps → Metrics_Config

```python
METRICS_CONFIG_HEADER_MAP = {
    "kpi_key": ["kpi_key", "KPI Key", "kpi", "KPI", "metric_key", "Metric Key"],
    "kpi_name": ["kpi_name", "KPI Name", "kpi title", "KPI Title", "metric_name", "Metric Name"],
    "kpi_level": ["kpi_level", "KPI Level", "level", "Level", "metric_level", "Metric Level"],
    "unit": ["unit", "Unit", "units", "Units"],
    "description": ["description", "Description", "desc", "Desc"],
    "is_active": ["is_active", "Is Active", "active", "Active", "enabled", "Enabled"],
    "notes": ["notes", "Notes", "comment", "Comment", "comments", "Comments"],

    # system / read-only surfaces
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}
```

---

# 2) Optimization Center — all tabs header maps

## 2.1 Candidates tab

```python
OPTIM_CANDIDATES_HEADER_MAP = {
    "initiative_key": ["initiative_key", "Initiative Key", "initiative id", "Initiative ID", "key", "Key"],
    "title": ["title", "Title", "initiative_title", "Initiative Title"],
    "market": ["market", "Market", "country", "Country"],
    "department": ["department", "Department", "team", "Team", "requesting_team", "Requesting Team"],
    "category": ["category", "Category", "type", "Type", "initiative_category", "Initiative Category"],

    "engineering_tokens": ["engineering_tokens", "Engineering Tokens", "tokens", "Tokens", "eng_tokens", "Eng Tokens"],
    "deadline_date": ["deadline_date", "Deadline Date", "deadline", "Deadline", "due_date", "Due Date"],

    "is_mandatory": ["is_mandatory", "Is Mandatory", "mandatory", "Mandatory", "must_do", "Must Do"],
    "mandate_reason": ["mandate_reason", "Mandate Reason", "mandatory_reason", "Mandatory Reason", "reason", "Reason"],

    "bundle_key": ["bundle_key", "Bundle Key", "bundle", "Bundle"],
    "prerequisite_keys": ["prerequisite_keys", "Prerequisite Keys", "prerequisites", "Prerequisites", "depends_on", "Depends On"],
    "exclusion_keys": ["exclusion_keys", "Exclusion Keys", "exclusions", "Exclusions", "mutual_exclusions", "Mutual Exclusions"],
    "program_key": ["program_key", "Program Key", "program", "Program"],
    "synergy_group_keys": ["synergy_group_keys", "Synergy Group Keys", "synergy_groups", "Synergy Groups"],

    "active_scoring_framework": [
        "active_scoring_framework", "Active Scoring Framework", "active framework", "Active Framework",
        "framework", "Framework",
    ],
    "active_overall_score": [
        "active_overall_score", "Active Overall Score", "overall_score", "Overall Score",
        "active: overall score", "Active: Overall Score",
    ],

    "north_star_contribution": [
        "north_star_contribution", "North Star Contribution", "north_star_gain", "North Star Gain",
        "ns_contribution", "NS Contribution",
    ],
    "immediate_kpi_key": ["immediate_kpi_key", "Immediate KPI Key", "immediate_kpi", "Immediate KPI"],
    "primary_kpi_key": ["primary_kpi_key", "Primary KPI Key", "primary_kpi", "Primary KPI"],

    "status": ["status", "Status", "initiative_status", "Initiative Status"],
    "notes": ["notes", "Notes"],

    # UI helper only (sheet-only)
    "is_selected_for_run": [
        "is_selected_for_run", "Is Selected For Run", "selected_for_run", "Selected For Run",
        "include_in_run", "Include In Run",
    ],

    # system / read-only
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}
```

---

## 2.2 Scenario_Config tab

```python
OPTIM_SCENARIO_HEADER_MAP = {
    "scenario_name": ["scenario_name", "Scenario Name", "name", "Name"],
    "period_key": ["period_key", "Period Key", "period", "Period", "timeframe", "Timeframe"],
    "capacity_total_tokens": [
        "capacity_total_tokens", "Capacity Total Tokens", "total_capacity_tokens", "Total Capacity Tokens",
        "capacity_tokens", "Capacity Tokens",
    ],
    "objective_mode": ["objective_mode", "Objective Mode", "mode", "Mode"],
    "objective_weights_json": [
        "objective_weights_json", "Objective Weights JSON", "objective_weights", "Objective Weights",
        "weights_json", "Weights JSON", "weights", "Weights",
    ],
    "notes": ["notes", "Notes"],

    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}
```

---

## 2.3 Constraints tab

```python
OPTIM_CONSTRAINTS_HEADER_MAP = {
    "constraint_type": ["constraint_type", "Constraint Type", "type", "Type"],
    "dimension": ["dimension", "Dimension"],
    "key": ["key", "Key", "dimension_key", "Dimension Key"],

    "min_tokens": ["min_tokens", "Min Tokens", "floor_tokens", "Floor Tokens", "min", "Min"],
    "max_tokens": ["max_tokens", "Max Tokens", "cap_tokens", "Cap Tokens", "max", "Max"],

    "target_kpi_key": ["target_kpi_key", "Target KPI Key", "kpi_key", "KPI Key"],
    "target_value": ["target_value", "Target Value", "value", "Value"],

    "notes": ["notes", "Notes"],

    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}
```

---

## 2.4 Targets tab

```python
OPTIM_TARGETS_HEADER_MAP = {
    "market": ["market", "Market", "country", "Country", "scope", "Scope"],
    "kpi_key": ["kpi_key", "KPI Key", "metric_key", "Metric Key"],
    "target_value": ["target_value", "Target Value", "value", "Value"],
    "floor_or_goal": ["floor_or_goal", "Floor Or Goal", "type", "Type", "target_type", "Target Type"],
    "notes": ["notes", "Notes"],

    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}
```

---

## 2.5 Runs tab

```python
OPTIM_RUNS_HEADER_MAP = {
    "run_id": ["run_id", "Run ID", "id", "ID"],
    "scenario_name": ["scenario_name", "Scenario Name", "scenario", "Scenario"],
    "period_key": ["period_key", "Period Key", "period", "Period"],
    "status": ["status", "Status"],

    "created_at": ["created_at", "Created At", "created", "Created"],
    "finished_at": ["finished_at", "Finished At", "finished", "Finished", "completed_at", "Completed At"],

    "selected_count": ["selected_count", "Selected Count", "count_selected", "Count Selected"],
    "total_objective": ["total_objective", "Total Objective", "objective_value", "Objective Value"],
    "capacity_used": ["capacity_used", "Capacity Used", "tokens_used", "Tokens Used"],

    "gap_summary": ["gap_summary", "Gap Summary", "gaps_summary", "Gaps Summary"],
    "results_tab_ref": ["results_tab_ref", "Results Tab Ref", "link_to_results", "Link To Results"],

    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}
```

---

## 2.6 Results_Portfolio tab

```python
OPTIM_RESULTS_HEADER_MAP = {
    "initiative_key": ["initiative_key", "Initiative Key", "key", "Key"],
    "selected": ["selected", "Selected", "is_selected", "Is Selected"],
    "allocated_tokens": ["allocated_tokens", "Allocated Tokens", "tokens", "Tokens", "allocation", "Allocation"],

    "market": ["market", "Market"],
    "department": ["department", "Department"],
    "category": ["category", "Category"],

    "north_star_gain": [
        "north_star_gain", "North Star Gain", "north_star_contribution", "North Star Contribution",
        "ns_gain", "NS Gain",
    ],
    "active_overall_score": [
        "active_overall_score", "Active Overall Score", "overall_score", "Overall Score",
        "active: overall score", "Active: Overall Score",
    ],

    "mandate_reason": ["mandate_reason", "Mandate Reason", "mandatory_reason", "Mandatory Reason"],
    "bundle_key": ["bundle_key", "Bundle Key", "bundle", "Bundle"],
    "dependency_status": ["dependency_status", "Dependency Status", "deps_status", "Deps Status"],

    "notes": ["notes", "Notes"],

    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}
```

---

## 2.7 Gaps_And_Alerts tab

```python
OPTIM_GAPS_HEADER_MAP = {
    "market": ["market", "Market", "scope", "Scope"],
    "kpi_key": ["kpi_key", "KPI Key", "metric_key", "Metric Key"],
    "target": ["target", "Target", "target_value", "Target Value"],
    "achieved": ["achieved", "Achieved"],
    "gap": ["gap", "Gap", "shortfall", "Shortfall"],
    "severity": ["severity", "Severity", "level", "Level"],
    "notes": ["notes", "Notes"],
    "recommendation": ["recommendation", "Recommendation", "suggestion", "Suggestion"],

    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}
```

---

## Quick confirmations aligned to your note #3 (weighted_kpis)

When `objective_mode == "weighted_kpis"`, validation should allow KPI keys that are:

* **North Star KPI key**
* **Active Strategic KPI keys**

So the allowed KPI universe for weights is:
`{north_star} ∪ {strategic_kpis_active}`

(We’ll enforce this in `OptimizationScenarioSyncService` save validation.)

---


A fixed order of headers/columns on sheets:

* makes PM-driven column rearranging brittle
* breaks sheet-local experimentation
* encourages “rigid spreadsheet as database table” behavior
* creates unnecessary refactor friction (exactly what you’re trying to avoid)

So: — column order should not matter, and we should avoid any design that requires it.

---

## The better approach (aligned to your current architecture)

We already have the right pattern in most places:

* **Readers/Writers rely on header normalization + alias maps**
* Writers update **only specific columns by name**, regardless of where they are
* Unknown columns are ignored
* PMs can move/add columns freely

That’s the correct “sheet-native” philosophy.

### What we should do instead (for any “regen” behavior)

If we ever need “full regeneration” for a results view (like a Portfolio view), do it in a way that’s still flexible:

**Option A : write only into a protected “system block”**

* Put a clearly labeled section, e.g.:

  * columns starting at `A:...` reserved for system output
  * everything to the right is PM playground
  * Even then, don’t rely on ordering; rely on headers inside the system block.

**Option B: avoid full regen altogether**

* Always do targeted writes based on header maps:

  * find column indices by header
  * update only those columns
  * append new rows if needed
    This is consistent with your current `ParamsWriter` / `MathModelsWriter` approach.

Given our preference, we’d default to **Option B** for Phase 5.

---
