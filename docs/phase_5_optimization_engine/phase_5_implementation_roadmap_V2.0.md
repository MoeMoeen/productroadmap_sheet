Below is the **next cohesive, comprehensive, internally consistent Phase 5 implementation roadmap**, rewritten to reflect **every lock and correction to date**, including:

* DB drop list + sheet drop list
* corrected entry surfaces (Intake vs ProductOps vs Backlog vs Optimization Center)
* **Metrics_Config** in ProductOps
* **KPI_Contributions** tab in ProductOps (entry surface for `kpi_contribution_json`)
* dropping `primary_kpi_key` everywhere
* `metric_chain_text` entered in ProductOps/MathModels → persisted as `Initiative.metric_chain_json`
* `llm_suggested_metric_chain_text` sheet-only suggestion
* **two contribution display columns** in OptimCenter/Candidates:

  * north star contribution (single)
  * strategic KPI contributions summary (multi)
* normalization policy:

  * North Star and Lexicographic: native units
  * Weighted KPIs: normalized by Targets as KPI scales
* constraints tab → `OptimizationConstraintSet` compilation
* Backlog writer must stop relying on column order
* initiative_key never PM-authored; formula-copied across sheets

This is the “implementation canonical doc” going forward.

---

# Phase 5 — Portfolio Optimization Engine (Implementation Roadmap, Canonical)

## 0) What Phase 5 is

Phase 5 turns your scored backlog into **portfolio decisions**.

**Input:** a validated candidate set of initiatives (from DB), scenario config + constraints + targets (from Optimization Center).
**Output:** a persisted Portfolio + PortfolioItems + run history + sheet outputs (Results, Gaps, Runs).

Phase 5 is **not** a prototype or a ranking sort: it is a **durable decision engine** with reproducibility, governance, and PM-native UX.

---

## 1) Hard locks and cleanup prerequisites

### 1.1 DB drops (must do before new fields)

Remove from `Initiative` DB model:

* `current_pain`, `desired_outcome`, `target_metrics`
* `strategic_theme`, `linked_objectives`
* `expected_impact_description`, `impact_metric`, `impact_unit`, `impact_low`, `impact_expected`, `impact_high`
* `total_cost_estimate`
* `time_sensitivity` (string)
* `missing_fields`
* `llm_notes`
* `math_warnings`

(These are replaced by: `problem_statement`, `hypothesis`, `llm_summary`, MathModels+Params, KPI contributions, and time_sensitivity_score/dates.) 

### 1.2 Sheet drops (already applied in latest headers)

* Central Backlog: drop `LLM Notes`, `Strategic Theme` (and keep Backlog mostly as a view + override surface)
* ProductOps/Scoring_inputs: drop `strategic_priority_coefficient`, `risk_level`, `time_sensitivity` (can be formula-copied later if desired) 

### 1.3 Backlog writer refactor

Backlog writer must **not** rely on column order; it must behave like other writers:

* find columns by header aliases
* update only mapped columns
* no rigid “write whole block by hardcoded order” behavior 

---

## 2) Updated metric/KPI architecture (locked)

### 2.1 KPI universe and units

**ProductOps → Metrics_Config** is the authoritative UI for:

* KPI keys
* KPI names
* KPI levels (north_star vs strategic)
* KPI units

This is persisted in DB (new model). Units live here for validation and display.

### 2.2 KPI contributions entry surface

**ProductOps → KPI_Contributions** is the only entry surface for `kpi_contribution_json`.

* PM/Analytics enter JSON
* backend validates keys + units using Metrics_Config
* backend never invents values
* everything else only displays derived summaries

### 2.3 Metric chain entry surface

**ProductOps → MathModels** contains:

* `metric_chain_text` (PM entry, optional LLM help)
* backend parses and persists to `Initiative.metric_chain_json`

`llm_suggested_metric_chain_text` stays sheet-only.

### 2.4 No primary_kpi_key

`primary_kpi_key` is dropped everywhere. Initiative is aligned via:

* `immediate_kpi_key`
* `kpi_contribution_json` keys (restricted to north_star + strategic KPIs)

---

## 3) Optimization math policy (locked)

### 3.1 Objective modes

1. **north_star**

* objective uses native units of north star contribution (no normalization)

2. **weighted_kpis**

* objective uses **normalized contributions**
* default scale = Targets (fraction-of-target)
* weights allowed only for KPIs in `{north_star} ∪ {strategic}`

3. **lexicographic**

* constraints/targets operate in native units (no normalization)
* solve in stages: meet target floors, then maximize objective

### 3.2 Redundancy policy

* Do not mix redundant KPIs in weighted objective (e.g., GMV + conversion)
* Use constraints/lexicographic instead for guardrails.

---

## 4) Sheet architecture (locked with latest headers)

### 4.1 Central Backlog (existing)

* mostly view of DB-backed initiative truth (intake → DB → backlog)
* PM can override selected fields (explicit save)
* shows read-only:

  * `Immediate KPI Key`
  * `Metric Chain JSON`

### 4.2 ProductOps (existing + new tabs)

Existing tabs:

* `Scoring_inputs` (framework inputs + comparison surface)
* `MathModels` (formula + chain + approval)
* `Params` (inputs/assumptions)

New tabs:

* `Metrics_Config`
* `KPI_Contributions`

### 4.3 Optimization Center (new spreadsheet)

Tabs:

* `Candidates` (formula-copied view + selection checkbox)

  * includes both:

    * `north_star_contribution`
    * `strategic_kpi_contributions`
* `Scenario_Config`
* `Constraints`
* `Targets`
* `Runs` (backend-written)
* `Results` (backend-written)
* `Gaps_And_Alerts` (backend-written)

Important: `is_optimization_candidate` is **not** needed in Candidates tab. Graduation happens in Backlog and the Candidates tab is a filtered view.

---

## 5) DB models for Phase 5

### 5.1 Add new Initiative fields (Phase 5)

* candidate flag + period
* tokens + scope mode
* market/department/category
* mandate/bundle/dependencies/exclusions/synergy keys
* date constraints + time_sensitivity_score
* KPI alignment fields:

  * `immediate_kpi_key`
  * `metric_chain_json`
  * `kpi_contribution_json`

### 5.2 Add new DB models

* `OrganizationMetricsConfig` (for Metrics_Config)
* `OptimizationScenario`
* `OptimizationConstraintSet`
* `OptimizationRun` (domain run artifact; ActionRun remains execution ledger)
* `Portfolio`
* `PortfolioItem`

---

## 6) Sync and entry surface rules (implementation-critical)

### 6.1 initiative_key rule

* backend generates
* never PM-entered
* other sheets copy it via formulas

### 6.2 Source-of-truth by field family

* Intake-owned identity fields: intake → DB → backlog; backlog can override
* Scoring framework controls: ProductOps/Scoring_inputs → DB → backlog
* Math model structure: ProductOps/MathModels → DB
* Params (inputs): ProductOps/Params → DB
* KPI universe: ProductOps/Metrics_Config → DB
* KPI contributions: ProductOps/KPI_Contributions → DB
* Optimization config/constraints/targets: Optimization Center tabs → DB

---

## 7) Optimization engine implementation (backend)

### 7.1 New sheet modules

* readers/writers for Optimization Center tabs:

  * candidates reader (mostly reads selection + validates)
  * scenario reader
  * constraints reader
  * targets reader
  * runs writer
  * results writer
  * gaps writer

All follow existing patterns:

* header normalization
* alias maps
* status writes (`run_status`)
* updated_source + updated_at stamping

### 7.2 Optimization service

`app/services/optimization_service.py` responsibilities:

* load candidate set from DB (filtered by is_optimization_candidate + period) OR by explicit selection scope
* load scenario + constraints + targets from DB (saved from sheets)
* validate:

  * tokens present
  * KPI contribution keys valid
  * prerequisite keys resolvable
  * mandatory initiatives feasible
* build MILP:

  * x_i binary selection
  * capacity constraints
  * floors/caps
  * dependencies
  * bundles
  * exclusions
  * optional synergy bonuses
* compute:

  * achieved KPI totals
  * gaps vs targets
  * normalized contributions for weighted mode
* persist:

  * OptimizationRun (inputs_snapshot_json, result_json)
  * Portfolio + PortfolioItems

---

## 8) Execution plane (PM jobs via ActionRun)

### Phase 5 PM jobs (new actions)

* `pm.optimize_save_scenario` (Scenario_Config → DB)
* `pm.optimize_save_constraints` (Constraints → DB/ConstraintSet)
* `pm.optimize_save_targets` (Targets → DB/ConstraintSet.targets_json)
* `pm.optimize_run_selected_candidates` (Candidates selection → optimization run)
* `pm.optimize_run_all_candidates` (DB candidate pool → optimization run)
* `pm.optimize_write_results` (DB → write Runs/Results/Gaps tabs)

These run in worker with ActionRun ledger, consistent summary semantics, and per-row statuses.

---

## 9) Testing + observability

### 9.1 Unit tests

* contribution normalization (target-based scaling)
* constraint compilation (Constraints tab → ConstraintSet JSON)
* MILP constraints:

  * capacity
  * floors/caps
  * prerequisites
  * bundles
  * exclusions
* KPI gap calculation

### 9.2 Integration tests

* save scenario/constraints/targets from sheets → DB
* run optimization → produces deterministic selection
* write results to sheets
* rerun identical inputs → identical outputs

### 9.3 Observability

* OptimizationRun.inputs_snapshot_json persists exact inputs
* solver metadata stored
* ActionRun result_json includes run_id linkage
* sheet updated_source + updated_at surfaces are consistent

---

## 10) Step-by-step build plan (ordered)

### Phase 5.0 — Cleanup + schema alignment

1. Apply DB drops + migrations (Initiative cleanup)
2. Apply sheet drops (already done in your latest headers)
3. Refactor backlog writer to header-based updates
4. Add new InitiativeMathModel fields:

   * `model_name`
   * `model_description_free_text`
   * (confirm `model_prompt_to_llm` persists)
5. Remove Initiative llm_notes + math_warnings fields

### Phase 5.1 — ProductOps config tabs

6. Add ProductOps `Metrics_Config` tab + DB model + sync service
7. Add ProductOps `KPI_Contributions` tab + sync service (writes Initiative.kpi_contribution_json)
8. Add metric chain columns to MathModels:

   * metric_chain_text (persist)
   * llm_suggested_metric_chain_text (sheet-only)
   * update MathModelSyncService to parse + persist Initiative.metric_chain_json

### Phase 5.2 — Optimization Center spreadsheet plumbing ✅ COMPLETE

9. ✅ Create Optimization Center workbook with locked tabs + headers
10. ✅ Implement readers/writers + header maps (ConstraintsReader, TargetsReader, ConstraintsWriter, TargetsWriter)
11. ✅ Implement constraint/target compilation and sync services:
    * `app/services/optimization_compiler.py` - pure compilation logic (zero I/O)
    * `app/services/optimization_sync_service.py` - I/O orchestration (sheets → compiler → DB)
    * Schema validation via discriminated unions in `app/schemas/optimization_center.py`
    * Writers use composite keys to prevent collisions
12. ✅ Apply production-grade fixes:
    * Rename `key` → `dimension_key` across all layers
    * Multi-dimensional targets with nested JSON: `{dimension: {dimension_key: {kpi_key: {...}}}}`
    * Bundle member deduplication (schema-level)
    * Exclusion pair normalization (sorted pairs)
    * Split exclusions into `exclusions_initiatives_json` + `exclusions_pairs_json`
    * CapacityDimension literal type for type safety
    * Full composite key scoping in writers

### Phase 5.3 — Solver interface design (NEXT)

13. Design solver adapter interface:
    * Define `OptimizationProblem` schema (candidates + objective + constraints)
    * Define `OptimizationSolution` schema (selected + allocations + KPI achievements)
    * Define `SolverAdapter` protocol
14. Implement feasibility checker (pre-solver validation):
    * Detect hard contradictions (mandatory + excluded, prerequisite cycles)
    * Detect capacity impossibilities (sum(floors) > cap)
    * Return `FeasibilityReport` with errors/warnings
15. Implement solver adapter stub (mock solutions for testing)

### Phase 5.4 — THE ACTUAL SOLVER (THE HEART OF THE SYSTEM)

16. **Implement the optimization solver** (`app/services/optimization_solver.py`):
    * **Build MILP model** using OR-Tools CP-SAT or PuLP:
      * Binary decision variables: x_i for each candidate initiative
      * Objective function construction (north_star / weighted_kpis / lexicographic)
      * Capacity constraints (sum tokens by dimension <= caps, >= floors)
      * Governance constraints:
        * Mandatory: x_i = 1 for mandatory initiatives
        * Bundles: all-or-nothing (if any x_i in bundle = 1, all must = 1)
        * Exclusions pairs: x_i + x_j <= 1
        * Exclusions initiatives: x_i = 0 for excluded initiatives
        * Prerequisites: x_dependent <= x_required (or equivalently: x_dependent => x_required)
        * Synergy bonuses (optional): add bonus terms to objective when both x_i = 1 and x_j = 1
      * Target constraints (multi-dimensional):
        * KPI floor constraints: sum(contributions[dimension][dimension_key][kpi]) >= target_value
        * KPI goal constraints: soft penalties or second-stage optimization
    * **Solve the model**:
      * Call solver.Solve()
      * Check solver status (OPTIMAL, FEASIBLE, INFEASIBLE, UNBOUNDED)
      * Extract solution: selected initiative keys, allocated tokens per dimension, achieved KPI values
    * **Compute results**:
      * Total objective value
      * Capacity used (total and by dimension)
      * KPI achievements (by dimension)
      * Gaps vs targets
      * Solver diagnostics (solve time, iterations, etc.)
    * **Return `OptimizationSolution`** with all results

17. **Wire solver into optimization service**:
    * `optimization_service.py` calls feasibility checker first
    * If feasible, calls solver with `OptimizationProblem`
    * Persists `OptimizationRun` + `Portfolio` + `PortfolioItem` records
    * Returns run_id and summary

18. Run 2-3 smoke test scenarios end-to-end (simple, conflicting, multi-dimensional)

### Phase 5.5 — Execution jobs (ActionRun)

19. Add PM job actions to action_runner + worker orchestration
20. Add Apps Script UI menus in Optimization Center

### Phase 5.6 — Portfolio persistence + publish roadmap outputs

21. Persist Portfolio + PortfolioItems per run (already covered in 5.4)
22. Create Roadmap spreadsheet + publishing flow
23. Add what-if scenario runner (clone scenario + rerun)

## Phase 5.F — Advanced features from narrative

24. Enhanced synergy group bonuses (complex scoring models)
25. Horse trading assistant: "if we force X, what drops?"
26. Multi-roadmap generation: run multiple frameworks / weights to produce multiple portfolios
27. Gap signals + collaboration prompts

---
