Below is **non-binding Optimization Center sheet template guidance**: recommended tabs, recommended columns, and lightweight UX notes. **Nothing here is enforced by code** — PMs can reorder columns, insert new columns anywhere, add formulas, and experiment freely. The backend will only care about columns it recognizes via the header maps.

---

# Optimization Center — Recommended Sheet Template (Non-binding, Updated & Locked)

This is **UX guidance only**.
Nothing here is enforced by code — PMs can reorder columns, add new columns, insert formulas, and experiment freely.
The backend only relies on **recognized headers**, not column order.

---

## Global principles (unchanged, reaffirmed)

* **PMs can move/add columns anytime**; backend uses header names (aliases), not positions.
* Every tab should include **3 system columns** (recommended):

  * `run_status` — backend writes per-row job outcome
  * `updated_source` — backend writes provenance
  * `updated_at` — backend writes UTC timestamp
* Use **filters + conditional formatting** to make workflows obvious (especially Candidates + Results).
* Keep solver-driving inputs **simple and human-enterable**; use JSON only where structure is genuinely needed.

---

## Tab 1 — `Candidates`

**Purpose:**
A **read-only working shortlist** of initiatives eligible for optimization, with a **selection checkbox**.
This is a *view + selection surface*, **not** a data entry surface.

All initiative data here is expected to be **formula-copied** from Central Backlog.

**CRITICAL: Constraint Entry Separation**
- **Constraints are entered ONLY on the Constraints tab**
- Candidates tab may display constraint indicators (is_mandatory, bundle_key, etc.) but these are **read-only/computed**
- Backend derives constraint indicators from `OptimizationConstraintSet` compiled JSON and writes them to Candidates for display
- PMs must never edit constraint columns on Candidates tab - use Constraints tab as the sole entry surface

### Recommended columns (backend-recognized)

**Identity & Descriptive (formula-copied from Backlog):**
* `initiative_key`
* `title`
* `market`
* `department`
* `category`

**Editable Fields (PM can modify):**
* `engineering_tokens`
* `deadline_date`
* `notes` (sheet-only)
* `is_selected_for_run` (sheet-only checkbox)

**Display-Only Constraint Indicators (derived from Constraints tab):**
* `is_mandatory` (computed: initiative in compiled mandatory_initiatives_json)
* `mandate_reason` (computed: notes from corresponding mandatory constraint row)
* `bundle_key` (computed: bundle_key where initiative appears in bundles_json members)
* `prerequisite_keys` (computed: prerequisite list from prerequisites_json)
* `exclusion_keys` (computed: exclusion keys from exclusions_initiatives_json or exclusions_pairs_json)
* `synergy_group_keys` (computed: synergy keys from synergy_bonuses_json)

**Contribution display (derived, read-only):**

* `north_star_contribution`
  *(single number, derived from `kpi_contribution_json[north_star]`)*
* `strategic_kpi_contributions`
  *(summary string, derived from `kpi_contribution_json` for strategic KPIs)*

**KPI alignment (derived, read-only):**

* `immediate_kpi_key`
* `metric_chain_json`
* `active_scoring_framework`
* `active_overall_score`
* `lifecycle_status`

> ❌ `primary_kpi_key` is **removed** and must not appear.

**System columns:**
* `run_status`, `updated_source`, `updated_at`

### PM-only helper columns (sheet-only)

* `confidence`, `data_quality`, `why_in_candidate_pool` (optional formulas)

### UX tips

* Default filter:
  * `is_selected_for_run = TRUE`
  * `run_status != OK`
* Conditional formatting:
  * missing `engineering_tokens`
  * mandatory initiatives missing `mandate_reason`
* **To add/edit constraints**: Go to Constraints tab, not Candidates tab

---

## Tab 2 — `Scenario_Config`

**Purpose:**
Define **how** the optimizer should run.

### Recommended columns (backend-recognized)

* `scenario_name`
* `period_key`
* `capacity_total_tokens`
* `objective_mode`
  (`north_star` | `weighted_kpis` | `lexicographic`)
* `objective_weights_json`
* `notes`

### PM-only helper columns

* `active_north_star_kpi_key` (lookup from ProductOps → Metrics_Config)
* `active_strategic_kpis` (lookup/list)
* `weights_validated` (formula)
* `last_used_run_id` (vlookup from Runs)

### UX tips

* Use a dropdown for `objective_mode`.
* For `objective_weights_json`:

  * JSON is acceptable in v1
  * PMs may maintain weights in helper columns and build JSON via formula

**Normalization reminder (for PMs):**

* `weighted_kpis` mode uses **normalized contributions**
* Default normalization scale = **Targets**

---

## Tab 3 — `Constraints`

**Purpose:**
Define **governance and feasibility rules**.

### Recommended columns (backend-recognized)

* `scenario_name` (grouping key for compilation)
* `constraint_set_name` (e.g., "Baseline", "Aggressive", "Relaxed")
* `constraint_type` — Canonical values:
  * `capacity_floor`
  * `capacity_cap`
  * `mandatory`
  * `bundle_all_or_nothing`
  * `exclude_pair`
  * `exclude_initiative`
  * `require_prereq`
  * `synergy_bonus`
* `dimension` — Canonical values:
  * For capacity: `country` | `product` | `department` | `category` | `program` | `all`
  * For governance: `initiative` | `bundle`
* `dimension_key` (the specific value: UK, Growth, INIT-000123, BUNDLE-001, etc.)
* `min_tokens` (capacity_floor only)
* `max_tokens` (capacity_cap only)
* `bundle_member_keys` (bundle_all_or_nothing only: pipe-separated "INIT-001|INIT-002|INIT-003")
* `prereq_member_keys` (require_prereq only: pipe-separated prerequisites "INIT-001|INIT-019")
* `notes`

**Prerequisite Example:**
- `constraint_type` = `require_prereq`
- `dimension` = `initiative`
- `dimension_key` = `INIT-0003` (the dependent initiative)
- `prereq_member_keys` = `INIT-0001|INIT-0019` (required prerequisites)
- Result: If INIT-0003 is selected, both INIT-0001 and INIT-0019 must also be selected

**Note:** Targets moved to separate Targets tab. Each constraint row represents one rule; many rows share the same (scenario_name, constraint_set_name) and get compiled together.

### PM-only helper columns

* `is_active` (checkbox, optional)
* `priority` (future)
* `source` (Leadership / Finance / etc.)

### UX tips

* Treat each row as a **single rule**.
* Backend compiles this tab into an `OptimizationConstraintSet`.

---

## Tab 4 — `Targets`

**Purpose:**
Define **KPI targets**, used for:

* constraints (all optimization modes)
* normalization scale (weighted_kpis mode)
* achievement tracking (gaps)

### Recommended columns (backend-recognized)

* `scenario_name` (grouping key for compilation)
* `constraint_set_name` (must match Constraints tab)
* `dimension` (e.g., `country`, `product`, `all` for global)
* `dimension_key` (e.g., `UK`, `Payments`, empty for `all`)
* `kpi_key` (must exist in ProductOps → Metrics_Config)
* `floor_or_goal` (`floor` | `goal`)
* `target_value` (numeric, in native KPI units)
* `notes`

**Multi-dimensional targets supported:** You can set country-level targets, product-level targets, cross-sectional targets (country+product), or global targets (dimension="all"). Targets compile to nested JSON: `{dimension: {dimension_key: {kpi_key: {type, value, notes?}}}}`.

### PM-only helper columns

* `unit` (lookup from Metrics_Config)
* `owner`
* `confidence`

### UX tips

* KPI keys must be **North Star or Strategic KPIs only**.
* Target values are entered in **native KPI units**.

---

## Tab 5 — `Runs`

**Purpose:**
Execution history and audit trail.

### Backend-written columns

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

* `compare_to_run_id`
* `notes`

---

## Tab 6 — `Results` (Results_Portfolio)

**Purpose:**
The selected portfolio produced by a run.

### Backend-written columns

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

### PM-only helper columns (future)

* `manual_override_selected`
* `override_reason`

---

## Tab 7 — `Gaps_And_Alerts`

**Purpose:**
Explain **why the portfolio is imperfect**.

### Backend-written columns

* `market`
* `kpi_key`
* `target`
* `achieved`
* `gap`
* `severity`
* `notes`
* `recommendation` (optional, LLM later)

### PM-only helper columns

* `owner`
* `status`
* `next_action`

---

## (Related but separate) ProductOps → `KPI_Contributions`

> Not part of Optimization Center, but **feeds it directly**

**Purpose:**
Single entry surface for `kpi_contribution_json`.

### Recommended columns

* `initiative_key` *(formula-copied, read-only)*
* `kpi_contribution_json` *(PM / Analytics editable)*
* `notes`
* `run_status`
* `updated_source`
* `updated_at`

**Rules:**

* Keys must ⊆ `{north_star ∪ strategic_kpis}`
* Units validated against Metrics_Config
* Backend never invents values
* Optimization Center only **displays derived summaries**

---

## System columns (unchanged)

Every tab may include (anywhere):

* `run_status`
* `updated_source`
* `updated_at`

Backend writes these; PM edits are ignored.

---

