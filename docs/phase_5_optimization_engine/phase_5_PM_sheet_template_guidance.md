Below is **non-binding Optimization Center sheet template guidance**: recommended tabs, recommended columns, and lightweight UX notes. **Nothing here is enforced by code** — PMs can reorder columns, insert new columns anywhere, add formulas, and experiment freely. The backend will only care about columns it recognizes via the header maps.

---

# Optimization Center — Recommended Sheet Template (Non-binding)

## Global principles

* **PMs can move/add columns anytime**; backend uses header names (aliases), not positions.
* Every tab should include **3 system columns** (recommended):

  * `run_status` (backend writes per-row job outcome)
  * `updated_source` (backend writes provenance token)
  * `updated_at` (backend writes UTC timestamp)
* Use **filters + conditional formatting** to make workflows obvious (especially Candidates + Results).
* Keep the solver-driving fields **simple and human-enterable**; keep complex structure in JSON cells only when necessary.

---

## Tab 1 — `Candidates`

**Purpose:** The working shortlist of initiatives eligible for optimization (a “graduation” surface).

### Recommended columns (backend-recognized)

* `initiative_key`
* `title`
* `market`
* `department`
* `category`
* `engineering_tokens`
* `deadline_date`
* `is_mandatory`
* `mandate_reason`
* `bundle_key`
* `prerequisite_keys`
* `exclusion_keys`
* `program_key`
* `synergy_group_keys`
* `active_scoring_framework`
* `active_overall_score`
* `north_star_contribution`
* `immediate_kpi_key`
* `primary_kpi_key`
* `status`

### Recommended PM-only helper columns (sheet-only)

* `is_selected_for_run` (checkbox)
* `notes`
* `owner` (if you want)
* `confidence` / `data_quality` (if you want)
* `why_in_candidate_pool` (formula that checks completeness)

### UX tips

* Filter default view: `is_selected_for_run = TRUE` and `run_status != OK`
* Conditional formatting:

  * highlight missing `engineering_tokens`
  * highlight mandatory with missing `mandate_reason`
  * highlight prerequisite_keys that look malformed (e.g., no “INIT-”)

---

## Tab 2 — `Scenario_Config`

**Purpose:** Define the scenario (period + objective mode + capacity + weights).

### Recommended columns (backend-recognized)

* `scenario_name`
* `period_key`
* `capacity_total_tokens`
* `objective_mode` (`north_star` | `weighted_kpis` | `lexicographic`)
* `objective_weights_json`
* `notes`

### PM-only helper columns

* `active_north_star_kpi_key` (lookup from ProductOps → Metrics_Config)
* `active_strategic_kpis` (lookup/list)
* `weights_validated` (formula)
* `last_used_run_id` (formula/vlookup from Runs)

### UX tips

* Use a data validation dropdown for `objective_mode`.
* For `objective_weights_json`:

  * keep it readable; one JSON cell is fine in v1
  * PMs can maintain weights in helper columns and build JSON with a formula if desired

---

## Tab 3 — `Constraints`

**Purpose:** Structured constraint rows (floors/caps/targets/bundles/exclusions/etc.).

### Recommended columns (backend-recognized)

* `constraint_type` (floor/cap/mandatory/dependency/bundle/target/exclusion)
* `dimension` (market/department/category/global/kpi)
* `key`
* `min_tokens`
* `max_tokens`
* `target_kpi_key`
* `target_value`
* `notes`

### PM-only helper columns

* `is_active` (checkbox) — if you want soft toggling without deleting rows
* `priority` (if you want future ordering)
* `source` (Leadership/Finance/etc.)

### UX tips

* Treat Constraints as “rule rows” — keep them small, clear, and readable.
* If you add `is_active`, backend can ignore it now; PM can use it for experimentation.

---

## Tab 4 — `Targets`

**Purpose:** Explicit KPI targets by market or global (cleaner than embedding in Constraints rows).

### Recommended columns (backend-recognized)

* `market` (use `GLOBAL` for global targets)
* `kpi_key`
* `target_value`
* `floor_or_goal` (`floor` | `goal`)
* `notes`

### PM-only helper columns

* `unit` (lookup from Metrics_Config)
* `owner` (Finance/Analytics)
* `confidence` (high/med/low)

### UX tips

* Strongly recommend Targets be only **North Star or Strategic KPIs** (your locked rule).
* Keep target_value in KPI-native units.

---

## Tab 5 — `Runs`

**Purpose:** Audit + history of optimization runs.

### Recommended columns (backend-recognized / backend-written)

* `run_id`
* `scenario_name`
* `period_key`
* `status`
* `created_at`
* `finished_at`
* `selected_count`
* `total_objective`
* `capacity_used`
* `gap_summary`
* `results_tab_ref`

### PM-only helper columns

* `compare_to_run_id` (for future diffing)
* `notes`

### UX tips

* Keep this tab append-only from PM perspective.
* PMs should use it as “what happened and when.”

---

## Tab 6 — `Results_Portfolio`

**Purpose:** The selected portfolio results (one row per initiative in result set).

### Recommended columns (backend-recognized / backend-written)

* `initiative_key`
* `selected`
* `allocated_tokens`
* `market`
* `department`
* `category`
* `north_star_gain`
* `active_overall_score`
* `mandate_reason`
* `bundle_key`
* `dependency_status`
* `notes`

### PM-only helper columns

* `manual_override_selected` (future)
* `override_reason` (future)
* `comments`

### UX tips

* Sort view by:

  * selected first
  * then `north_star_gain` desc
* If you want “portfolio rank”, add a column; backend can fill it later.

---

## Tab 7 — `Gaps_And_Alerts`

**Purpose:** Shows infeasibilities, unmet targets, and constraint tensions.

### Recommended columns (backend-recognized / backend-written)

* `market`
* `kpi_key`
* `target`
* `achieved`
* `gap`
* `severity`
* `notes`
* `recommendation` (optional now; LLM later)

### PM-only helper columns

* `owner` (who should act)
* `status` (open/triaged/done)
* `next_action`

### UX tips

* Treat this as the “portfolio debugging” tab.
* Severity can be computed by backend or a formula.

---

# Optional: minimal “system columns” guidance

For each tab, it’s useful to have these columns somewhere (PM can place them anywhere):

* `run_status`
* `updated_source`
* `updated_at`

The backend will:

* write these when it touches a row
* ignore them when PM saves (read-only)

---

