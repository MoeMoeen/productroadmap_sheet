Below is a **complete Phase 5 end-to-end implementation roadmap** for the **Optimization Engine**—not a prototype. It’s a full system plan with:
* backend architecture
* new DB models + **specific Initiative fields to add**
* a new **Optimization spreadsheet** (tabs + columns)
* new flows / PM jobs (like Phase 4.5, but for optimization)
* solver strategy (MILP first, extensible to non-linear later)
* scenario planning + trade-offs (“horse trading”)
* governance (mandatory initiatives, enablers, bundles, prerequisites)
* testing + observability

---
# Phase 5 — Optimization Engine (End-to-End Roadmap)
## 0) Core framing decisions (lock now in design)
### 0.1 The unit of optimization
**Optimize a portfolio of initiatives for a specific period and scenario.**
* Period: e.g., Q1 2026, Monthly cycle, etc.
* Portfolio output: selected initiatives + allocations + rationale + gaps.
### 0.2 Objective functions (support multiple)
The engine must support **multiple objective modes**, selectable per run:
1. **North Star maximize** (single objective)
2. **Weighted KPI maximize** (multi-objective, scalarized)
3. **Lexicographic objective** (meet targets first, then maximize surplus)
### 0.3 Constraints families (your narrative)
We will implement constraints as first-class objects:
* Capacity (global + per market/team)
* Floors & caps (market, department, category)
* Target floors (market KPI targets, global targets)
* Dependencies (prerequisites)
* Bundles (all-or-nothing)
* Mandatory initiatives (always include)
* Deadline/time sensitivity constraints (must be scheduled before date)
---
# 1) Data model changes (DB)
## 1.1 Add fields to `Initiative` (required for optimization)
These are the **must-have** fields to run meaningful optimization.
### A) Portfolio / eligibility
* `is_optimization_candidate` (bool, default False)
“Graduated to optimization pool”
* `candidate_period_key` (str, nullable)
e.g. `"2026-Q1"` or `"2026-01"`; optional but useful
### B) Capacity / cost modeling
* `engineering_tokens` (float, nullable)
Primary capacity consumption unit for optimization
* `engineering_tokens_mvp` (float, nullable)
Optional: MVP version cost
* `engineering_tokens_full` (float, nullable)
Optional: full version cost
* `scope_mode` (str, nullable; enum-ish: `"mvp"|"full"|"custom"`)
Used if you allow PM to choose variant
(You already have `effort_engineering_days`; you can map days→tokens, but tokens should exist explicitly.)
### C) Ownership dimensions (constraints)
You already have `country`, `requesting_team`, etc. For optimization you should normalize:
* `market` (str, nullable) — (can reuse `country` but better to have a stable “market”)
* `department` (str, nullable) — e.g. “Growth”, “Operations”
* `category` (str, nullable) — from your taxonomy: UX, Infra, Hygiene, etc.
### D) Governance constraints
* `is_mandatory` (bool) — you already have it ✅
* `mandate_reason` (str/text, nullable)
* `program_key` (str, nullable) — “program/enabler grouping”
* `bundle_key` (str, nullable) — “must ship together” group
* `prerequisite_keys` (JSON list[str], nullable) — required initiatives
* `exclusion_keys` (JSON list[str], nullable) — mutually exclusive (optional)
### E) Time constraints
* `deadline_date` exists ✅
Add:
* `earliest_start_date` (date, nullable)
* `latest_finish_date` (date, nullable) (or reuse deadline)
* `time_sensitivity_score` (float, nullable) — for objective weighting
### F) Metric chain + target contribution
This is the heart of your narrative.
* `immediate_kpi_key` (str, nullable)
* `primary_kpi_key` (str, nullable)
* `north_star_kpi_key` (str, nullable) (or global setting)
* `metric_chain_json` (JSON, nullable)
e.g. nodes/edges: immediate → intermediary → primary → north star
* `kpi_contribution_json` (JSON, nullable)
normalized estimated contribution numbers per KPI
Example:
```json
{
"north_star": 1200,
"gmv": 100000,
"conversion_rate": 0.002,
"retention_30d": 0.01
}
```
### G) Synergy modelling inputs (optional now, but you described it)
* `synergy_group_keys` (JSON list[str], nullable)
Then synergy is modeled at portfolio level.
---
## 1.2 New DB models (required)
### A) `OptimizationScenario`
Represents the “planning context”.
Fields:
* `id`
* `name`
* `period_key` (e.g. `2026-Q1`)
* `description`
* `objective_mode` (`"north_star"|"weighted_kpis"|"lexicographic"`)
* `objective_weights_json` (KPI→weight)
* `capacity_total_tokens`
* `capacity_by_market_json` (optional)
* `capacity_by_department_json` (optional)
* `created_by_user_id`
* `created_at`, `updated_at`
### B) `OptimizationConstraintSet`
Reusable constraint definitions.
Fields:
* `id`
* `name`
* `floors_json` (market/department/category floors)
* `caps_json` (market/department/category caps)
* `targets_json` (market KPI targets, global targets)
* `mandatory_initiatives_json` (optional cache)
* `notes`
### C) `OptimizationRun`
A single execution of the optimizer.
Fields:
* `id`, `run_id` (string like ActionRun style)
* `scenario_id`
* `constraint_set_id`
* `status` (`queued/running/success/failed`)
* `requested_by_email`
* `inputs_snapshot_json` (the exact candidate set + parameters used)
* `result_json` (selected initiatives, allocations, gaps)
* `solver_name`, `solver_version`
* `started_at`, `finished_at`
* `error_text`
### D) `Portfolio` / `RoadmapVersion`
The persisted decision artifact.
Fields:
* `id`
* `scenario_id`
* `optimization_run_id` (optional)
* `name`
* `is_baseline` / `is_active`
* `selected_initiatives_json` or (better) a join table
### E) `PortfolioItem` (join table)
* `portfolio_id`
* `initiative_id`
* `selected` (bool)
* `allocated_tokens`
* `rank` (optional)
* `notes`
* `source` (`"optimizer"|"manual_override"`)
---
# 2) New “Optimization Spreadsheet” (Frontend / sheets architecture)
Create a new spreadsheet: **Optimization Center**.
This spreadsheet is your “graduation level” after backlog scoring.
## Tabs (recommended)
### Tab 1 — `Candidates`
Where initiatives eligible for optimization appear.
Columns (minimum):
* `initiative_key`
* `title`
* `market`
* `department`
* `category`
* `engineering_tokens`
* `deadline_date`
* `is_mandatory`
* `bundle_key`
* `prerequisite_keys`
* `active_scoring_framework`
* `active_overall_score`
* `north_star_contribution` (from `kpi_contribution_json`)
* `immediate_kpi_key`
* `primary_kpi_key`
* `status`
* `notes` (UI-only)
* `is_selected_for_run` (checkbox) — helps selection without manual key picking
* `run_status` (Status column)
> These rows are typically pulled from Central Backlog via formulas + filtering.
> But the backend must treat the Optimization sheet as a working surface too.
### Tab 2 — `Scenario_Config`
Defines the scenario parameters for a run.
* `scenario_name`
* `period_key`
* `capacity_total_tokens`
* `objective_mode`
* `objective_weights_json` (or columns per KPI)
* `notes`
### Tab 3 — `Constraints`
Define floors/caps and other constraints in a structured way.
Example columns:
* `constraint_type` (floor/cap/mandatory/dependency/bundle/target)
* `dimension` (market/department/category/global)
* `key` (e.g. “UK”, “Growth”, “Infra”)
* `min_tokens`
* `max_tokens`
* `target_kpi_key`
* `target_value`
* `notes`
### Tab 4 — `Targets`
Market + global targets as explicit data.
* `market`
* `kpi_key`
* `target_value`
* `floor_or_goal` (floor/goal)
* `notes`
### Tab 5 — `Runs`
Log of optimization runs.
* `run_id`
* `scenario_name`
* `status`
* `created_at`
* `finished_at`
* `selected_count`
* `total_value`
* `capacity_used`
* `gap_summary`
* `link_to_results` (UI convenience)
### Tab 6 — `Results_Portfolio`
The selected portfolio output written back by backend.
* `initiative_key`
* `selected` (TRUE/FALSE)
* `allocated_tokens`
* `market`
* `department`
* `category`
* `north_star_gain`
* `active_overall_score`
* `mandatory_reason`
* `bundle_key`
* `dependency_status`
* `notes`
* `run_status`
### Tab 7 — `Gaps_And_Alerts`
Shows unmet targets / infeasible constraints.
* `market`
* `kpi_key`
* `target`
* `achieved`
* `gap`
* `severity`
* `notes`
* `recommendation` (optional later, LLM)
---
# 3) Backend services and flows for Phase 5
## 3.1 Sheet readers/writers (new modules)
Create:
* `app/sheets/optimization_candidates_reader.py`
* `app/sheets/optimization_constraints_reader.py`
* `app/sheets/optimization_results_writer.py`
* `app/sheets/optimization_runs_writer.py`
Follow the same patterns you used for ProductOps and Backlog:
* header normalization
* safe mapping
* selection by initiative_key
* Status column writes
## 3.2 Optimization engine core (`app/services/optimization_service.py`)
Responsibilities:
* Build candidate set from DB (or from Optimization sheet)
* Build constraint matrices
* Build objective function
* Call solver (MILP first)
* Produce structured outputs:
* selected initiatives
* allocations
* KPI achievement
* gaps
* reasons (mandatory, bundle, dependency)
* Persist `OptimizationRun` + `Portfolio`
## 3.3 Solver choice (pragmatic and scalable)
Start with **MILP** using:
* **OR-Tools** (recommended for combinatorial selection + constraints)
or
* **PuLP** / **Pyomo**
Why MILP:
* binary selection variables
* floors/caps/mandatory constraints are natural
* dependencies/bundles are natural
Non-linear:
* only needed later if synergies are non-linear or objective is non-linear
## 3.4 Handling synergy (your narrative)
Phase 5 full system should include synergy modelling, but implement in a staged way:
### V1 synergy model (linearizable)
Introduce synergy “bonus variables” per synergy group:
* if all initiatives in group selected → add bonus to objective
This is MILP-friendly:
* bonus_var ≤ each initiative selection var
* bonus_var = 1 only if all selected
* objective += synergy_bonus * bonus_var
### Later: non-linear synergies
If synergy depends on continuous relationships, move to:
* piecewise linear approximation
* or nonlinear solver
---
# 4) Optimization execution plane (like Phase 4.5 but for Phase 5)
You already have ActionRun infrastructure—reuse it.
## New PM jobs (Phase 5 UI actions)
These are not Phase 4.5; they’re Phase 5 jobs.
* `pm.optimize_run_selected_candidates`
* `pm.optimize_run_all_candidates`
* `pm.optimize_save_constraints`
* `pm.optimize_write_results`
* `pm.optimize_publish_portfolio_to_roadmap_sheet` (later)
Each is a single ActionRun, and writes status back to Optimization sheet tabs.
---
# 5) Initiative graduation workflow (the “next level” you described)
You said:
> initiatives are “graduated to optimization” via formulas / rules.
Implementation:
### Sheet-level graduation (formulas)
* Central Backlog marks `is_optimization_candidate` based on:
* score thresholds
* completeness checks
* required KPI chain presence
* token estimate presence
* etc.
### Backend-level enforcement
Even if sheet shows candidates, backend validates:
* required fields exist (tokens, market, metric chain)
* else mark as invalid and surface in `Status/Gaps`
Then candidates are synced into DB:
* via `pm.save_selected` style action for candidates tab (later)
---
# 6) Roadmap sheets (your future direction)
You’re thinking correctly:
* Backlog can be messy
* Roadmaps are curated portfolios that passed criteria
* Optimization outputs become Roadmap versions
So Phase 5 should also include:
* `Roadmap` spreadsheet concept:
* Roadmap_Versions tab
* Roadmap_Items tab
* Publishing action from optimizer results into roadmap sheet
But if you want Phase 5 to finish end-to-end, include it.
---
# 7) Testing strategy (must-have)
### Unit tests
* constraint builder correctness
* objective calculation
* dependency/bundle constraints
* floor/cap constraints
* target gap calculation
### Integration tests
* candidate sheet → DB snapshot
* optimization run produces deterministic portfolio
* results written back to Results_Portfolio tab
* run logged in Runs tab
### Regression tests
* run same scenario twice → stable results (unless candidate set changes)
---
# 8) Observability / traceability (must-have)
* Persist full `inputs_snapshot_json` in OptimizationRun
* Persist solver name + status
* Store gaps as structured output
* Log substep results like you did with pm jobs
* Status columns on sheets reflect run outcomes per row
---
# 9) Step-by-step implementation plan (ordered)
## Phase 5.A — Modeling & schema
1. Add Initiative fields (tokens, category, KPI keys, metric chain, bundles, prerequisites, candidate flag)
2. Create OptimizationScenario, ConstraintSet, OptimizationRun, Portfolio, PortfolioItem models
3. Create migrations + seed minimal sample scenarios
## Phase 5.B — Optimization spreadsheet
4. Create Optimization Center spreadsheet with tabs listed above
5. Define canonical headers and help text (like Phase 4 sheet help)
6. Implement readers/writers for Candidates/Constraints/Runs/Results
## Phase 5.C — Optimization engine service
7. Implement `OptimizationService` (inputs → MILP → output)
8. Implement constraint builders:
* capacity
* floors/caps
* targets as floors
* mandatory
* prerequisites
* bundles
9. Implement objective modes (north star, weighted KPIs, lexicographic)
## Phase 5.D — Execution plane for optimization
10. Add Phase 5 PM jobs in action_runner:
* run optimization
* write results
* log run
11. Add Apps Script UI to Optimization spreadsheet (bound scripts v1)
## Phase 5.E — Portfolio persistence + roadmap outputs
12. Persist Portfolio + PortfolioItems per run
13. Create Roadmap spreadsheet + publishing flow
14. Add what-if scenario runner (clone scenario + rerun)
## Phase 5.F — Advanced features from narrative
15. Synergy group bonuses
16. Horse trading assistant: “if we force X, what drops?”
17. Multi-roadmap generation: run multiple frameworks / weights to produce multiple portfolios
18. Gap signals + collaboration prompts
---
# 10) What I need from you before I finalize the plan into a task-by-task build sequence
Not a question that blocks you—we can proceed—but the implementation will be cleaner if we pick defaults:
1. What’s the first optimization period format you want? (`2026-Q1` or monthly)
2. What’s the first capacity unit you want as “tokens”? (map from engineering days or separate number)
3. First objective: maximize `north_star_contribution` (from math model) or active score?
If you don’t answer, I’ll assume:
* period = quarterly
* tokens = `engineering_tokens` (float)
* objective = maximize `north_star_contribution` with active score as tie-breaker
---
