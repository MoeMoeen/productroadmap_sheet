
-
1. scoring batch --> rename to activating_batch
2. we have to add a brief description field in the initiative table/orm/model/class. string. 



--------------------------------------------------------------------------------------------

Brief but complete feedback:

You’re right to keep PM Job #1 as sync-all visibility only, now and later.

You’re also right that selective syncing from intake is the wrong abstraction in the long run.


What you just described is a much cleaner conceptual model:

Key shift (important)

Central Backlog = universe of ideas / candidates
(can be messy, incomplete, exploratory)

Roadmap(s) = approved, curated, decision-ready subsets
(clean, intentional, comparable, optimizable)


So instead of:

> “Should this initiative even enter the backlog?”



You move to:

> “Has this initiative passed the bar to enter a roadmap?”



That’s the correct place for approval, filtering, gating, and portfolio logic.

Why this is better

No silent exclusion of ideas

Full traceability of submissions

Backlog can be filtered instead of pruned

Roadmaps become first-class decision artifacts

Optimization naturally operates on roadmaps, not raw backlog


Implication (just to lock it)

Intake → Backlog stays unconditional and idempotent

Approval / quality gates happen when creating roadmaps

Multiple roadmaps can coexist, each with different logic

Backlog pollution is solved by status + filters, not selective sync


So yes — this is the right direction, and it aligns perfectly with:

your future optimization engine

multi-roadmap scenarios

governance without friction




Immediate next steps (per Phase 5 roadmap, given current code state):

1) ProductOps config tabs to DB:
   - Implement Metrics_Config reader/writer + sync service to OrganizationMetricsConfig; add ActionRun for save.
   - Implement KPI_Contributions reader/writer + sync service to Initiative.kpi_contribution_json (validated against Metrics_Config); add ActionRun for save.

2) MathModels parse path:
   - Finalize metric_chain_text parsing to Initiative.metric_chain_json (and raw on InitiativeMathModel) in the save flow; ensure status/writebacks OK.

3) Optimization Center plumbing:
   - Create workbook tabs (Candidates, Scenario_Config, Constraints, Targets, Runs, Results, Gaps_And_Alerts) with header maps.
   - Implement readers/writers + sync services for Scenario/Constraints/Targets, and status stamping.

4) Optimization service:
   - Build MILP solver (north_star, weighted_kpis with target-based normalization, lexicographic), with constraints (capacity, floors/caps, mandatory, bundles, prereqs, exclusions, optional synergies).
   - Persist OptimizationRun + Portfolio + PortfolioItems with inputs_snapshot_json/result_json.

5) PM actions (ActionRun):
   - Add pm.optimize_* actions: save_scenario, save_constraints, save_targets, run_selected_candidates, run_all_candidates, write_results.

6) Tests:
   - Unit: normalization, constraint builders, objective selection.
   - Integration: sheet→DB→opt→sheet round-trip; deterministic rerun check.