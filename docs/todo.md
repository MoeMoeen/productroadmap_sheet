

--------------------------------------------------------------------------------------------


Immediate next steps (per Phase 5 roadmap, given current code state):

1) ProductOps config tabs to DB: DONE
   - Implement Metrics_Config reader/writer + sync service to OrganizationMetricsConfig; add ActionRun for save.
   - Implement KPI_Contributions reader/writer + sync service to Initiative.kpi_contribution_json (validated against Metrics_Config); add ActionRun for save.

2) MathModels parse path: DONE
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


   ----------------------------------------------------------------------------------------------------------------------

   Plan for Optimization Center scaffolding

1) Define models/header maps (app/sheets/models.py)
   - Add header → field maps + alias normalization for each tab: Candidates, Scenario_Config, Constraints, Targets, Runs, Results, Gaps_and_alerts.
   - Define editable fields per tab (lists, deterministic).
   - Define sheet row pydantic models for each tab (typed fields; Optional for blanks; lists for *_keys via comma-split).
   - Add provenance tokens for opt sheets (updated_source).

2) Readers (sheet → row models)
   - Implement per-tab readers: candidates_reader.py, scenario_config_reader.py, constraints_reader.py, targets_reader.py, runs_reader.py, results_reader.py, gaps_alerts_reader.py.
   - Each reader: header alias resolution, row parsing with type casting (dates, ints/floats, bools, json for objective_weights_json), list splitting for *_keys, blank-row skip rules, and return (row, row_num) pairs.
   - Add validation: e.g., scenario_name required; initiative_key required in candidates/results; constraint_type/dimension required; objective_mode must be in allowed set; target_kpi_key optional by type.

3) Writers (DB → sheet)
   - Minimal read + targeted write pattern (like backlog/productops writer):
     * Read header row
     * Read key column only to map key → row
     * Build updates only for owned columns
     * Batch/chunk writes (200 ranges) with blank-run cutoff
   - Per tab:
     * Candidates/Results keyed by initiative_key
     * Scenario_Config keyed by scenario_name
     * Constraints keyed by (constraint_type, dimension, key) string key
     * Targets keyed by (market, kpi_key)
     * Runs keyed by run_id
     * Gaps_and_alerts keyed by (market, kpi_key)

4) Sync services (sheet → DB)
   - candidates_sync_service: upsert OptimizationCandidate (or similar) fields; validate initiative exists; apply provenance, updated_at; respect is_selected_for_run.
   - scenario_config_sync_service: upsert ScenarioConfig (period_key, capacity_total_tokens, objective_mode, objective_weights_json).
   - constraints_sync_service: upsert Constraint rows keyed by (constraint_type, dimension, key); validate min/max/target numeric.
   - targets_sync_service: upsert Target rows keyed by (market, kpi_key); validate floor_or_goal enum.
   - runs_sync_service: upsert run metadata (run_id, scenario_name, status timestamps).
   - results_sync_service: upsert OptimizationResult rows (selected, allocated_tokens, gains, notes).
   - gaps_alerts_sync_service: upsert gaps/alerts keyed by (market, kpi_key); severity optional enum.

   Common patterns:
   - Use blank-run cutoff when scanning keys.
   - Normalize keys (strip/lower) for matching; preserve original casing in writes.
   - Commit in batches (commit_every).
   - Return counts (row_count, upserts, failures).

5) Status writebacks
   - For each tab, support a Status column if present (or run_status column you already have). Writer should only touch the status column; minimal read (header + key + status col), blank-run cutoff, chunked updates.
   - Hook into ActionRunner substeps to write per-row status on errors/success where applicable.

6) ActionRunner wiring
   - Add pm.save_selected branches for each new tab to call the respective sync service; allow scope.type=all to process all rows; allow selection lists for keys.
   - Add pm.optimize_* actions later (run scenarios, write results) after engine is ready.

7) Config
   - Extend PRODUCT_OPS (or OPT) settings with tab names/IDs for the new sheet; add defaults.
   - Add provenance tokens for optimization-center writes.

8) Tests
   - Unit: readers parsing, validators for enums/json/number bounds, key normalization.
   - Integration: sheet→DB→sheet round-trip for each tab (minimal fixtures).
   - Smoke: chunking and blank-run cutoff behavior on sparse sheets.

