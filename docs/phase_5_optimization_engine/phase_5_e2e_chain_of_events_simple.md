Now, the **end-to-end chain of events** for the optimization plumbing we’re building (from sheets → validators → DB → engine → outputs) looks like this:

## 0) Entry surfaces (PM-facing sheets)

PMs work in the **Optimization Center workbook**:

**PM input tabs (Sheet → DB)**

* **Scenario_Config**: scenario_name, period_key, capacity_total_tokens, objective_mode, objective_weights_json, notes
* **Constraints**: scenario_name, constraint_set_name, constraint_type, dimension, key, min/max tokens, target_kpi_key/target_value, notes
* **Targets**: scenario_name, constraint_set_name, country, kpi_key, target_value, floor_or_goal, notes
* **Candidates**: engineering_tokens, deadline_date, mandatory/bundles/prereqs/exclusions etc, selection flags, notes (plus formula-fed read-only columns)

**System output tabs (DB → Sheet)**

* **Runs**: run metadata + run_status
* **Results**: chosen initiatives + allocations + gains + run_status (+ updated_* stamps)
* **Gaps_Alerts**: achieved vs target + severity + recommendations/notes (system- and/or PM-editable depending on your final decision)

## 1) “Save” action from the sheet (ActionRunner)

User clicks something like:

* `pm.save_selected` with `sheet_context.tab = "Constraints"` (or "Targets", "Scenario_Config", etc.)
* scope could be selection-based or `scope.type=all`.

ActionRunner routes to the right **Sync Service** (we’re building next).

## 2) Readers (Sheet → parsed rows)

Each tab has a reader that:

* reads header row
* resolves aliases → canonical fields
* reads rows (with blank-run cutoff)
* does basic coercion (bool/float/int/date) and returns `(row_num, row_dict_or_model)`.

At this stage, readers should **not** enforce deep semantics—they just parse.

## 3) Pydantic validators / schemas (Parsed row → validated row)

This is exactly what `app/schemas/optimization_center.py` is for.

For each row:

* map sheet fields → schema fields (your `*_FIELD_MAP` dicts)
* validate with Pydantic:

  * **ScenarioConfigSchema** validates numeric + objective_weights_json shape
  * **ConstraintRow** (discriminated union) validates *by constraint_type* (capacity_floor, cap, mandatory, bundle, exclude_pair, require_prereq, synergy_bonus, etc.)
  * **TargetRowSchema** validates floor_or_goal + numeric + required fields
* also validate cross-table rules where needed (ex: KPI keys exist in Metrics_Config).

Output of validation step = structured `ValidationMessage(row_num, key, errors, warnings)` per row.

## 4) Compilation step (Constraints + Targets → “compiled constraint set JSON”)

This is the “semantic bridge” between:

* **row-level inputs** on Constraints/Targets tabs
  and
* **engine-ready constraint set structure** stored in DB.

Flow:

* group rows by `(scenario_name, constraint_set_name)`
* compile them into a single `ConstraintSetCompiled` object (or a dict with that exact shape)
* that compiled JSON is what gets persisted into your DB model (OptimizationConstraintSet.*_json fields / rows_json / compiled_json — whatever you chose).

So: **Constraints tab is not the engine format**. It’s a user-friendly row input format. Compilation turns it into engine format.

## 5) Sync Services (Validated inputs → DB)

For each PM input tab:

**Scenario_Config sync**

* upsert `OptimizationScenario` keyed by `scenario_name`
* store objective_mode + objective_weights_json, capacity_total_tokens, etc.

**Constraints + Targets sync**

* upsert `OptimizationConstraintSet` keyed by `(scenario_name, constraint_set_name)`
* store:

  * raw rows (optional, for audit/debug)
  * compiled JSON (the thing the solver will consume)

**Candidates sync**

* upsert candidate fields (or store in candidate table / JSON on scenario/run depending on your DB design)
* validate initiative exists, etc.

Each sync service:

* returns counts + per-row validation messages
* writes sheet status (“OK / FAILED: …”) as a **system run_status** message (sheet-only) and stamps updated_source/updated_at.

## 6) Run execution (DB → engine → DB)

Later, a run action like `pm.optimize.run_selected_candidates` will:

* choose a scenario + a constraint_set (explicitly)
* snapshot inputs into `OptimizationRun.inputs_snapshot_json`:

  * scenario config
  * compiled constraint set
  * candidate set at that time
  * KPI registry / contributions, etc.
* call the MILP solver
* produce outputs:

  * selected initiatives + allocations
  * achieved KPIs vs targets
  * diagnostics / infeasibilities

Persist:

* `OptimizationRun` status, timings, objective value, etc.
* `Portfolio` + `PortfolioItem` rows
* results_json / gaps_json

## 7) Writers (DB → Sheet outputs)

After run:

* **Runs writer** writes run row + run_status message + stamps
* **Results writer** writes result rows (and notes/recommendations *only if you decided they’re system-owned for that tab*, otherwise those stay PM-editable and you never overwrite)
* **Gaps_Alerts writer** writes computed target/achieved/gap + severity + optional recommendation text

Again, run_status and updated_* are always safe to include as system-written fields (and your “`OUTPUT_FIELDS + _SYSTEM_STATUS_FIELDS`” approach is totally fine).

---

