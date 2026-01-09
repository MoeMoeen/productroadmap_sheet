
## Step 1 — Draft the Phase 5 glossary entries (one-line definitions)

Below is a **first-pass glossary** for every Phase 5 field/column we discussed (DB + sheets + new entities). Each item is **one line** by design, so you can review quickly and we can refine wording together.

### A) Core entities (new concepts)

* **Optimization Scenario**: A named planning context for a specific period that defines objective mode, KPI weights, and capacity assumptions.
* **Constraint Set**: A reusable bundle of floors/caps/targets/governance rules that shape what portfolios are allowed.
* **Optimization Run**: One executed solver run with an input snapshot, solver metadata, and the resulting selected portfolio + gaps.
* **Portfolio**: The persisted decision artifact (a chosen set of initiatives) produced by an optimization run (or manually curated).
* **Portfolio Item**: One initiative inside a portfolio, including selection flag, allocated tokens, rank, and source (optimizer vs manual).
* **Roadmap Version**: A published, human-facing roadmap view derived from a portfolio (may include extra scheduling/notes and manual overrides).
* **Horse trading**: A what-if process that forces inclusion/exclusion and reruns optimization to show what drops/changes and why.

### B) Initiative fields (optimization eligibility + governance)

* **is_optimization_candidate**: Whether this initiative is eligible to be considered by the optimizer.
* **candidate_period_key**: The period this initiative is intended/eligible for (e.g., `2026-Q1`) to scope candidate pools.
* **is_mandatory**: Whether the initiative must be included regardless of optimization trade-offs.
* **mandate_reason**: Human explanation of why the initiative is mandatory (regulatory, contractual, leadership mandate).
* **program_key**: A label grouping initiatives under a shared program/enabler theme for reporting or constraint rules.
* **bundle_key**: A label meaning initiatives with the same bundle must be selected together (all-or-nothing).
* **prerequisite_keys**: A list of initiative_keys that must be selected if this initiative is selected.
* **exclusion_keys**: A list of initiative_keys that cannot be selected together with this initiative (mutual exclusion).
* **synergy_group_keys**: A list of groups where selecting all members yields an extra portfolio-level bonus (synergy).

### C) Effort/capacity fields

* **effort_engineering_days**: Human-friendly estimate of engineering effort expressed in days (existing, used for understanding).
* **engineering_tokens**: The optimizer’s primary consumption unit representing engineering capacity usage (float, comparable across initiatives).
* **engineering_tokens_mvp**: Tokens required for an MVP version of the initiative (optional variant).
* **engineering_tokens_full**: Tokens required for a full version of the initiative (optional variant).
* **scope_mode**: Which scope variant is being optimized for (`mvp`, `full`, or `custom`) to choose the token cost basis.

### D) Ownership/dimension fields (constraint axes)

* **market**: Normalized market identifier used for constraints and capacity slicing (e.g., UK, UAE, Global).
* **department**: Normalized department identifier used for constraints/caps (e.g., Growth, Ops, Core).
* **category**: Normalized initiative category used for floors/caps (e.g., Infra, UX, Hygiene, Experiment).

### E) Time fields

* **deadline_date**: The latest acceptable delivery date (existing; used as time feasibility constraint).
* **earliest_start_date**: The earliest date the initiative is allowed to start (due to dependency, timing, readiness).
* **latest_finish_date**: The latest acceptable finish date (explicit “must be done by” date; can mirror deadline).
* **time_sensitivity_score**: A numeric indicator of urgency/penalty for delay used in objective weighting.

### F) Metric chain + contributions (impact model)

* **immediate_kpi_key**: The direct metric this initiative most immediately moves (closest causal metric).
* **metric_chain_json**: A structured graph describing how the initiative's impact flows through intermediate KPIs to the north star.
* **kpi_contribution_json**: A dictionary of estimated numeric contributions of this initiative to KPIs (keys restricted to north_star + strategic KPIs only).

**Note:** `primary_kpi_key` has been removed from the system. KPI alignment is now expressed via `immediate_kpi_key` and the keys present in `kpi_contribution_json`.

### G) OptimizationScenario fields

* **scenario.name**: Human-friendly label for a scenario (e.g., “Q1 Growth Heavy”).
* **scenario.period_key**: The period being optimized (e.g., `2026-Q1`).
* **scenario.objective_mode**: Which objective logic to use (`north_star`, `weighted_kpis`, `lexicographic`).
* **scenario.objective_weights_json**: KPI→weight map used when objective_mode is weighted KPIs.
* **scenario.capacity_total_tokens**: Total available token capacity for the period.
* **scenario.capacity_by_market_json**: Market→capacity token map for per-market capacity constraints.
* **scenario.capacity_by_department_json**: Department→capacity token map for per-department capacity constraints.

### H) OptimizationConstraintSet fields

* **floors_json**: Minimum token allocations by dimension: `{dimension: {dimension_key: min_tokens}}`.
* **caps_json**: Maximum token allocations by dimension: `{dimension: {dimension_key: max_tokens}}`.
* **targets_json**: KPI target requirements with nested multi-dimensional structure: `{dimension: {dimension_key: {kpi_key: {type, value, notes?}}}}`.
* **mandatory_initiatives_json**: List of initiative keys that must be included: `[initiative_key, ...]`.
* **bundles_json**: All-or-nothing initiative groups: `[{bundle_key, members: [...]}, ...]`.
* **exclusions_initiatives_json**: Initiative keys that cannot be selected: `[initiative_key, ...]`.
* **exclusions_pairs_json**: Pairs of initiatives where both cannot be selected: `[[key1, key2], ...]` (pairs normalized/sorted).
* **prerequisites_json**: Prerequisite dependencies as a dict: `{dependent_key: [prereq1, prereq2, ...], ...}` where if dependent is selected, all its prerequisites must be selected.
* **synergy_bonuses_json**: Initiative pairs that yield bonus when both selected: `[[key1, key2], ...]`.
* **notes**: Human explanation for why constraints exist and how to interpret them.

**Note:** All JSON fields use `dimension_key` (not `key`) for dimensional constraints. Exclusions split into separate initiatives vs pairs columns.

### I) OptimizationRun fields

* **run_id**: Unique identifier for this optimization execution (linked to ActionRun for execution traceability).
* **status**: Execution status of the solver run (`queued`, `running`, `success`, `failed`).
* **inputs_snapshot_json**: The exact candidate set + parameters + constraints used for reproducibility.
* **result_json**: Structured output including selected set, allocations, KPI achievements, and gaps.
* **solver_name**: Which solver engine was used (e.g., OR-Tools).
* **solver_version**: Solver version for reproducibility.
* **error_text**: Failure detail if the run did not succeed.

---

## Step 1.5 — Sheet-side columns (Optimization Center tabs)

### Candidates tab columns

* **is_selected_for_run**: Checkbox that marks which candidate initiatives should be included in the next optimization run scope.
* **north_star_contribution**: The initiative’s estimated direct contribution to the north star KPI (usually derived from kpi_contribution_json).
* **run_status**: Per-row status written by backend for user feedback (OK/FAILED/SKIPPED + message).
* **notes**: UI-only free text for PMs (not used by solver unless we explicitly decide later).

### Scenario_Config tab columns

* **objective_weights_json**: A JSON string holding KPI weights for weighted objective mode (or empty if not used).
* **run_status**: Status of last save/validation of scenario configuration.

### Constraints tab columns

* **scenario_name**: The scenario this constraint belongs to (grouping key for compilation).
* **constraint_set_name**: The named constraint set this rule belongs to (e.g., "Baseline", "Aggressive").
* **constraint_type**: The type of constraint rule (capacity_floor/capacity_cap/mandatory/bundle/exclude_pair/exclude_initiative/prerequisite/synergy_bonus).
* **dimension**: The dimension the constraint applies to (country/product/department/category/program/initiative/all for capacity; initiative for governance constraints).
* **dimension_key**: The value within the dimension (e.g., UK, Growth, Infra, INIT-000123).
* **min_tokens**: Minimum tokens required for that dimension+dimension_key (capacity_floor constraint only).
* **max_tokens**: Maximum tokens allowed for that dimension+dimension_key (capacity_cap constraint only).
* **bundle_member_keys**: Pipe-separated list of initiative keys for bundle constraints (e.g., "INIT-001|INIT-002|INIT-003").
* **notes**: Human-readable explanation of this constraint row.

### Results_Portfolio tab columns

* **selected**: Whether the initiative ended up selected by the optimizer.
* **allocated_tokens**: Tokens assigned to the initiative in the final portfolio (often equals engineering_tokens in V1).
* **dependency_status**: A computed indicator showing whether prerequisites were satisfied in the selected portfolio.

### Gaps_And_Alerts tab columns

* **achieved**: KPI value achieved by the selected portfolio (sum of contributions).
* **gap**: Remaining shortfall vs target (0 if target met).
* **severity**: Qualitative severity based on gap size (e.g., high/medium/low).

---

# Next step (Step 2)

Next, we’ll take this glossary list and add a second label per item:

* **DB-persisted** (must live in DB)
* **Sheet-only** (can live only in sheet, not persisted)
* **Derived** (computed from other fields; may be persisted as snapshot or not)

