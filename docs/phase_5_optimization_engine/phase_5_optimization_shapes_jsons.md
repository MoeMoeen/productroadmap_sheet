Yep — before sync services, you’re **100% right** to force clarity on **what lives where** and **how sheet rows map into your current DB schema**.

I’ll answer your questions in the same order and then give you a **clean mapping design** that fits your **existing tables** with minimal schema churn.

---

## 1) Scenario_Config: is PM literally typing JSON in the sheet?

**Yes — with the current design, that’s exactly the idea.**

* `Scenario_Config.objective_weights_json` is a **JSON object**.
* In the sheet, PM enters either:

  * a JSON string in the cell, like:

    ```json
    {"north_star": 1.0, "kpi.delivery_time": 0.4, "kpi.cost_per_order": 0.2}
    ```
  * OR (better UX later) you can support a “simple syntax” and convert it to JSON, but that’s optional.

Your reader already parses JSON, so the sync service can just persist the parsed dict into `OptimizationScenario.objective_weights_json`.

---

## 2) Relationships: Scenario ↔ Runs ↔ Constraint Sets

### Scenario ↔ Runs

This is **one-to-many**:

* **One scenario** can have **many runs**
* **One run** belongs to **one scenario**

**Why multiple runs for one scenario?** Example:

* Scenario = “2026-Q1 baseline” (same objective mode/weights/capacity)
* Run #1 = use only candidates with `is_selected_for_run = TRUE`
* Run #2 = include *all* candidates
* Run #3 = same candidates but different constraint set (e.g., “Strict country floors” vs “Relaxed”)
* Run #4 = same everything but different solver config or updated backlog scores

So the scenario is the “config definition”; the run is the “execution instance”.

### Scenario ↔ Constraint Sets

**Right now, your DB schema implies one-to-many:**

* `OptimizationScenario.constraint_sets` relationship exists
* `OptimizationConstraintSet.scenario_id` exists
  ➡️ meaning “a scenario can have many constraint sets.”

But you also want reuse (“same constraint set used by multiple scenarios”) — that would be **many-to-many**, which you do *not* currently model.

**So what do we do? Two realistic options:**

#### Option A (recommended, minimal change): constraint sets are *owned by scenario* (1-to-many)

* Each scenario can have multiple constraint sets.
* A run chooses which constraint set to use (`run.constraint_set_id`).

This gives you:

* one scenario → many constraint sets → many runs (each run picks a set)

✅ Works perfectly with current schema
✅ No new tables
✅ Matches “try multiple constraint versions for same scenario”

---

## 3) Constraints tab: what is “constraint_type / dimension / key / min/max tokens”?

Think of each row as a “constraint instruction” that eventually gets compiled into the JSON buckets on `OptimizationConstraintSet`.

### Suggested semantics

* `constraint_type`: what kind of rule this is

  * examples:

    * `capacity_floor` / `capacity_cap`
    * `mandatory`
    * `bundle`
    * `exclusion`
    * `prerequisite`
    * `target`
* `dimension`: what axis the constraint applies to

  * e.g. `country`, `department`, `category`, `program`, `initiative`
* `key`: which member inside that dimension

  * e.g. `UK`, `Growth`, `Payments`, `PROGRAM-12`, `INIT-000123`
* `min_tokens` / `max_tokens`: resource bounds for that dimension/key

  * “At least 200 tokens in UK” (`min_tokens=200`)
  * “At most 400 tokens in Growth” (`max_tokens=400`)

**Per scenario or per run?**

* These are *defined on the constraint set*.
* A run uses a constraint set.
  So: **constraints are defined per constraint set, applied per run**.

---

## 4) Targets tab: why no targets DB model?

Because your DB already has:

* `OptimizationConstraintSet.targets_json`

So the Targets tab rows should be **compiled into `targets_json`**.

That’s consistent with your current DB schema.

---

## 5) The missing piece: how do sheets map to DB rows cleanly?

Right now your **sheet tabs don’t include any linkage** like scenario_name or constraint_set_name on Constraints/Targets.

To make Sheet → DB sync deterministic, you need a grouping key.

### Minimal, clean sheet design (no DB change)

Add these columns to **Constraints** and **Targets** tabs:

* `scenario_name`
* `constraint_set_name`

Then sync groups rows like:

* (scenario_name="2026-Q1", constraint_set_name="Baseline") → one `OptimizationConstraintSet`
* and compiles the rows into its JSON buckets.

You do **not** need scenario_id on sheet; scenario_name is enough.

---

## 6) Concrete JSON shapes (so you stop guessing)

Here’s a sane shape that matches your model fields:

### `OptimizationConstraintSet.floors_json`

```json
{
  "country": { "UK": 200, "DE": 120 },
  "department": { "Growth": 300 }
}
```

### `caps_json`

```json
{
  "department": { "Platform": 250 }
}
```

### `targets_json`

KPI targets with **nested multi-dimensional structure**: `{dimension: {dimension_key: {kpi_key: {type, value, notes?}}}}`.

This structure supports:
- Global targets: `dimension="all", dimension_key="all"`
- Country-level targets: `dimension="country", dimension_key="UK"`  
- Product-level targets: `dimension="product", dimension_key="Payments"`
- Cross-sectional targets: `dimension="country_product", dimension_key="UK_Payments"`

**Why "all": {"all": {...}} nesting?**

The structure is `{dimension: {dimension_key: {kpi_key: {}}}}` for consistency. When dimension="all" (meaning global/company-wide targets), we still need a dimension_key level in the nested structure. We use "all" again because:
- Structural consistency: every dimension has dimension_keys
- Semantic clarity: "all"."all" clearly means "global across everything"
- Parser simplicity: no special cases needed

Alternatives like `{"all": {kpi_key: {}}}` would break the consistent 3-level nesting and require special-case parsing.

```json
{
  "country": {
    "UK": {
      "north_star_gmv": {"type": "floor", "value": 5000000},
      "conversion_rate": {"type": "goal", "value": 0.035, "notes": "Aspirational"}
    },
    "DE": {
      "north_star_gmv": {"type": "floor", "value": 3000000}
    }
  },
  "all": {
    "all": {
      "north_star_gmv": {"type": "floor", "value": 10000000}
    }
  }
}
```

**Important:** Targets are NOT auto-aggregated. Global targets are explicit constraints, not computed sums of dimensional targets.

### `mandatory_initiatives_json`

Simple list of initiative keys that must be selected.

```json
["INIT-000123", "INIT-000456", "INIT-000789"]
```

### `bundles_json`

All-or-nothing initiative groups. Schema enforces member deduplication.

```json
[
  {"bundle_key": "BUNDLE-ONBOARDING", "members": ["INIT-000201", "INIT-000202", "INIT-000203"]},
  {"bundle_key": "BUNDLE-RETENTION", "members": ["INIT-000401", "INIT-000402"]}
]
```

### `exclusions_initiatives_json`

Initiative keys that cannot be selected (single-initiative exclusions).

```json
["INIT-000999", "INIT-001234"]
```

### `exclusions_pairs_json`

Pairs of initiatives where both cannot be selected together. Schema normalizes pairs to sorted order `[min, max]` to prevent duplicates like `[A,B]` and `[B,A]`.

```json
[
  ["INIT-000100", "INIT-000200"],
  ["INIT-000300", "INIT-000400"]
]
```

### `prerequisites_json`

Prerequisite dependencies as a dict mapping each dependent initiative to its list of required prerequisites. Format: `{dependent_key: [prereq1, prereq2, ...], ...}`. If the dependent initiative is selected, ALL of its prerequisites must also be selected.

```json
{
  "INIT-000081": ["INIT-000012"],
  "INIT-000095": ["INIT-000033", "INIT-000034"],
  "INIT-000150": ["INIT-000100", "INIT-000101", "INIT-000102"]
}
```

In the example above:
- If INIT-000081 is selected, INIT-000012 must be selected
- If INIT-000095 is selected, both INIT-000033 AND INIT-000034 must be selected
- If INIT-000150 is selected, all three prerequisites (INIT-000100, INIT-000101, INIT-000102) must be selected

This dict structure provides:
- **Semantic clarity**: direct mapping from dependent to prerequisites
- **O(1) lookup**: efficient prerequisite checking
- **Self-documenting**: keys are initiatives, values are their prerequisites

### `synergy_bonuses_json`

Initiative pairs that yield bonus score when both selected. Schema deduplicates by normalized pair ordering.

```json
[
  ["INIT-000500", "INIT-000501"],
  ["INIT-000600", "INIT-000601"]
]
```

---

