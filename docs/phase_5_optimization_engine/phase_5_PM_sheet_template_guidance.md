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

**Contribution display (derived, read-only):**

* `north_star_contribution`
  *(single number, derived from `kpi_contribution_json[north_star]`)*
* `strategic_kpi_contributions`
  *(summary string, derived from `kpi_contribution_json` for strategic KPIs)*

**KPI alignment (derived, read-only):**

* `immediate_kpi_key`

* `metric_chain_json`

* `status`

> ❌ `primary_kpi_key` is **removed** and must not appear.

### PM-only helper columns (sheet-only)

* `is_selected_for_run` (checkbox — **the only interactive control here**)
* `notes`
* `why_in_candidate_pool` (formula: completeness / graduation logic)
* `confidence`, `data_quality`, etc. (optional)

### UX tips

* Default filter:

  * `is_selected_for_run = TRUE`
  * `run_status != OK`
* Conditional formatting:

  * missing `engineering_tokens`
  * mandatory initiatives missing `mandate_reason`
  * malformed `prerequisite_keys` (e.g., no `INIT-`)

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

* `constraint_type`
  (`floor` | `cap` | `mandatory` | `dependency` | `bundle` | `exclusion` | `target`)
* `dimension`
  (`market` | `department` | `category` | `global` | `kpi`)
* `key`
* `min_tokens`
* `max_tokens`
* `bundle_member_keys`
* `notes`

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

* constraints
* normalization (weighted objective)

### Recommended columns (backend-recognized)

* `market` (`GLOBAL` allowed)
* `kpi_key`
* `target_value`
* `floor_or_goal` (`floor` | `goal`)
* `notes`

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

