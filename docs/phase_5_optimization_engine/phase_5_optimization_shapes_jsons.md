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

```json
{
  "country": {
    "UK": {
      "kpi.delivery_time": {"type": "goal", "value": 2.3},
      "kpi.cost_per_order": {"type": "cap", "value": 5.0}
    }
  }
}
```

### `mandatory_initiatives_json`

```json
["INIT-000017", "INIT-000022"]
```

### `bundles_json`

```json
{
  "BUNDLE-1": ["INIT-000010", "INIT-000011"]
}
```

### `exclusions_json`

```json
[["INIT-000010", "INIT-000099"]]
```

This lets the solver layer read one consistent structure.

---

## 7) “How do inputs get delivered to the sheets in the first place?”

Two sources:

1. **Formula-fed / copied fields** (read-only feel)

   * from Central Backlog → Candidates: initiative_key/title/country/department/category/lifecycle_status
2. **PM entry fields live in Optimization Center**

   * engineering_tokens, deadline_date, mandatory flags, prereqs, etc.

Then sync services persist PM-entered values into DB (either:

* directly onto `Initiative` fields (best) or
* into constraint_set JSON (for optimization-only inputs)


---

## 1) KPI keys in Targets tab — where do they come from?

Yes: the `kpi_key` values in **Targets** should come from **ProductOps → Metrics_Config** (your authoritative KPI registry). In sync:

* validate each `kpi_key` exists in `OrganizationMetricConfig.kpi_key`
* optionally validate `kpi_level` if you want to restrict some rows (e.g., allow only `north_star` + `strategic`)

---

## 2) What “baseline vs aggressive” means (and why it’s in constraint set, not scenario)

Think of it like this:

* **Scenario** = “the optimization goal setup”

  * objective mode (north_star vs weighted KPIs vs lexicographic)
  * objective weights
  * capacity totals (and maybe by country/department)

* **Constraint Set** = “the guardrails + policy package”

  * floors/caps per dimension (country/department/category)
  * KPI targets / floors / goals (per country/KPI)
  * mandatory initiatives / bundles / exclusions

So “baseline” vs “aggressive” is totally valid at the **constraint set** layer:

* **Baseline**: realistic floors/caps, conservative targets, fewer mandatory items
* **Aggressive**: higher KPI floors/goals, maybe higher minimum allocations to growth markets, tighter caps on low-priority spend, more forced bundles, etc.

You can keep the **same scenario** (same objective mode/weights) and run it against multiple constraint sets to see sensitivity.

---

## 3) The compiled JSON shape (what the sync service should write to OptimizationConstraintSet)

This is the shape I recommend, matching your DB columns:

### `floors_json`

Minimum allocations / minimum counts by dimension.

```json
{
  "capacity_floors": [
    {
      "dimension": "country",
      "key": "UK",
      "min_tokens": 120
    },
    {
      "dimension": "department",
      "key": "Growth",
      "min_tokens": 80
    }
  ],
  "min_selected": [
    {
      "dimension": "country",
      "key": "UK",
      "min_count": 3
    }
  ]
}
```

### `caps_json`

Maximum allocations / maximum counts by dimension.

```json
{
  "capacity_caps": [
    {
      "dimension": "country",
      "key": "DE",
      "max_tokens": 150
    }
  ],
  "max_selected": [
    {
      "dimension": "category",
      "key": "TechDebt",
      "max_count": 4
    }
  ]
}
```

### `targets_json`

KPI floors/goals by dimension. This is separate from “floors/caps” because it’s **outcome constraints**, not resource constraints.

```json
{
  "kpi_targets": [
    {
      "kpi_key": "north_star_gmv",
      "dimension": "country",
      "key": "UK",
      "floor_or_goal": "goal",
      "target_value": 1.15,
      "unit": "ratio",
      "notes": "15% GMV growth target"
    },
    {
      "kpi_key": "conversion_rate",
      "dimension": "country",
      "key": "UK",
      "floor_or_goal": "floor",
      "target_value": 0.032,
      "unit": "ratio"
    }
  ]
}
```

### `mandatory_initiatives_json`

```json
{
  "mandatory": [
    {
      "initiative_key": "INIT-000123",
      "reason": "Regulatory deadline"
    }
  ]
}
```

### `bundles_json`

```json
{
  "bundles": [
    {
      "bundle_key": "BUNDLE-ONBOARDING",
      "initiative_keys": ["INIT-000201", "INIT-000202"],
      "mode": "all_or_nothing",
      "notes": "Requires both backend + frontend work"
    }
  ]
}
```

### `exclusions_json`

```json
{
  "exclude_initiatives": ["INIT-000999"],
  "exclude_bundles": ["BUNDLE-LEGACY"]
}
```

---

## 4) Example compiled JSON for Baseline vs Aggressive (illustrative)

### Baseline constraint set (example)

```json
{
  "floors_json": {
    "capacity_floors": [
      {"dimension": "country", "key": "UK", "min_tokens": 120},
      {"dimension": "country", "key": "DE", "min_tokens": 80},
      {"dimension": "department", "key": "Core", "min_tokens": 100}
    ],
    "min_selected": []
  },
  "caps_json": {
    "capacity_caps": [
      {"dimension": "category", "key": "TechDebt", "max_tokens": 140}
    ],
    "max_selected": []
  },
  "targets_json": {
    "kpi_targets": [
      {"kpi_key": "north_star_gmv", "dimension": "country", "key": "UK", "floor_or_goal": "goal", "target_value": 1.10, "unit": "ratio"},
      {"kpi_key": "conversion_rate", "dimension": "country", "key": "UK", "floor_or_goal": "floor", "target_value": 0.030, "unit": "ratio"}
    ]
  },
  "mandatory_initiatives_json": {
    "mandatory": [
      {"initiative_key": "INIT-000123", "reason": "Regulatory deadline"}
    ]
  },
  "bundles_json": {
    "bundles": [
      {"bundle_key": "BUNDLE-ONBOARDING", "initiative_keys": ["INIT-000201", "INIT-000202"], "mode": "all_or_nothing"}
    ]
  },
  "exclusions_json": {
    "exclude_initiatives": [],
    "exclude_bundles": []
  }
}
```

### Aggressive constraint set (example)

```json
{
  "floors_json": {
    "capacity_floors": [
      {"dimension": "country", "key": "UK", "min_tokens": 160},
      {"dimension": "department", "key": "Growth", "min_tokens": 140}
    ],
    "min_selected": [
      {"dimension": "country", "key": "UK", "min_count": 5}
    ]
  },
  "caps_json": {
    "capacity_caps": [
      {"dimension": "category", "key": "TechDebt", "max_tokens": 90}
    ],
    "max_selected": [
      {"dimension": "category", "key": "TechDebt", "max_count": 2}
    ]
  },
  "targets_json": {
    "kpi_targets": [
      {"kpi_key": "north_star_gmv", "dimension": "country", "key": "UK", "floor_or_goal": "goal", "target_value": 1.20, "unit": "ratio"},
      {"kpi_key": "conversion_rate", "dimension": "country", "key": "UK", "floor_or_goal": "floor", "target_value": 0.035, "unit": "ratio"}
    ]
  },
  "mandatory_initiatives_json": {
    "mandatory": [
      {"initiative_key": "INIT-000123", "reason": "Regulatory deadline"},
      {"initiative_key": "INIT-000305", "reason": "Growth bet required for aggressive plan"}
    ]
  },
  "bundles_json": {
    "bundles": [
      {"bundle_key": "BUNDLE-ONBOARDING", "initiative_keys": ["INIT-000201", "INIT-000202"], "mode": "all_or_nothing"},
      {"bundle_key": "BUNDLE-RETENTION", "initiative_keys": ["INIT-000401", "INIT-000402", "INIT-000403"], "mode": "all_or_nothing"}
    ]
  },
  "exclusions_json": {
    "exclude_initiatives": ["INIT-000999"],
    "exclude_bundles": []
  }
}
```

These are “exact” **format-wise** (matching your DB columns), but not “exact” **value-wise** until I can see your sample sheet rows.

---

Yep — **“editable fields” = PM-editable in the sheet**, not “backend-editable”. The backend *may still write* system fields (run_status / updated_source / updated_at), but the “editable_fields” lists are explicitly about **what humans are allowed/expected to type**.

Now, here’s a **concrete, PM-facing UX example** showing how the tabs look and how they map to DB.

---

## The mental model (PM UX)

* **Scenario_Config**: defines the *intent* (objective mode + weights + capacity headline).
* **Constraints**: defines *rules* you must obey (floors/caps/mandatory/bundles/exclusions/etc).
* **Targets**: defines *KPI goals/floors* (what you want to hit), grouped into the same constraint set.
* A **Constraint Set** is just a named bundle of constraints+targets for a scenario (e.g., “Baseline”, “Aggressive Growth”).
* A **Run** = “execute this Scenario + this Constraint Set on these Candidates”.

So **Constraints tab is not “one row = constraint set”**.
It’s **one row = one constraint**, and many rows share the same `(scenario_name, constraint_set_name)`.

---

## 1) Scenario_Config tab (PM inputs → OptimizationScenario)

Example (2 scenarios):

| scenario_name  | period_key | capacity_total_tokens | objective_mode  | objective_weights_json                  | notes                 |
| -------------- | ---------- | --------------------: | --------------- | --------------------------------------- | --------------------- |
| Q1-2026 Core   | 2026-Q1    |                  1200 | weighted_kpis   | {"north_star":0.6,"strategic_kpis":0.4} | Default Q1 portfolio  |
| Q1-2026 Growth | 2026-Q1    |                  1200 | north_star_only | {}                                      | Pure NSM maximization |

**Yes**: PM can paste JSON in the cell (string). Your reader already parses it into a dict. Sync stores it in `OptimizationScenario.objective_weights_json`.

---

## 2) Constraints tab (PM inputs → OptimizationConstraintSet JSON “compiled” fields)

**Add these columns (UX-critical):**

* `scenario_name`
* `constraint_set_name`

Then each row becomes “one rule”.

### What “min_tokens / max_tokens” mean

They only make sense for **capacity allocation constraints** (floors/caps).
For other constraint types, those columns are **blank** and you use `key/target_kpi_key/target_value` (or `notes`) depending on the type.

### Example Constraints (Scenario Q1-2026 Core, constraint sets Baseline vs Aggressive)

| scenario_name | constraint_set_name | constraint_type       | dimension  | key                      | min_tokens | max_tokens | target_kpi_key | target_value | notes                               |
| ------------- | ------------------- | --------------------- | ---------- | ------------------------ | ---------: | ---------: | -------------- | -----------: | ----------------------------------- |
| Q1-2026 Core  | Baseline            | capacity_floor        | country    | UK                       |        250 |            |                |              | Minimum UK capacity                 |
| Q1-2026 Core  | Baseline            | capacity_cap          | country    | DE                       |            |        180 |                |              | Cap Germany                         |
| Q1-2026 Core  | Baseline            | mandatory             | initiative | INIT-000017              |            |            |                |              | Must ship (regulatory)              |
| Q1-2026 Core  | Baseline            | bundle_all_or_nothing | bundle     | BNDL-PAYMENTS            |            |            |                |              | If pick one, pick all in bundle     |
| Q1-2026 Core  | Baseline            | exclude               | initiative | INIT-000044              |            |            |                |              | Blocked by legal                    |
| Q1-2026 Core  | Aggressive          | capacity_floor        | country    | UK                       |        350 |            |                |              | More UK investment                  |
| Q1-2026 Core  | Aggressive          | capacity_cap          | country    | DE                       |            |        120 |                |              | Lower DE cap                        |
| Q1-2026 Core  | Aggressive          | mandatory             | initiative | INIT-000017              |            |            |                |              | Same mandatory                      |
| Q1-2026 Core  | Aggressive          | require_prereq        | initiative | INIT-000081<-INIT-000012 |            |            |                |              | “INIT-81 requires INIT-12” encoding |

### How this compiles to DB (`OptimizationConstraintSet`)

Grouped by `(scenario_name, constraint_set_name)` you compile into:

* `floors_json`: e.g. `{"country":{"UK":250}}`
* `caps_json`: e.g. `{"country":{"DE":180}}`
* `mandatory_initiatives_json`: e.g. `["INIT-000017"]`
* `bundles_json`: e.g. `{"BNDL-PAYMENTS":{"mode":"all_or_nothing","items":[...]}}`
* `exclusions_json`: e.g. `["INIT-000044"]`
* `notes`: free text

So yes: **constraints are PM-entered row-wise**, then your sync service compiles them into the JSON fields on `OptimizationConstraintSet`.

---

## 3) Targets tab (PM inputs → OptimizationConstraintSet.targets_json)

Targets are *not a separate DB table in your schema*, so they should compile into the **same constraint_set** as constraints (same `(scenario_name, constraint_set_name)` columns).

Example:

| scenario_name | constraint_set_name | country | kpi_key        | floor_or_goal | target_value | notes               |
| ------------- | ------------------- | ------- | -------------- | ------------- | -----------: | ------------------- |
| Q1-2026 Core  | Baseline            | UK      | NSM_ORDERS     | floor         |       200000 | Must not drop below |
| Q1-2026 Core  | Baseline            | UK      | KPI_CONVERSION | goal          |        0.035 | Stretch goal        |
| Q1-2026 Core  | Aggressive          | UK      | NSM_ORDERS     | goal          |       240000 | Push growth         |
| Q1-2026 Core  | Aggressive          | DE      | NSM_ORDERS     | floor         |       120000 | Keep stable         |

Compile into `targets_json`, e.g.

```json
{
  "UK": {"NSM_ORDERS":{"type":"floor","value":200000},"KPI_CONVERSION":{"type":"goal","value":0.035}},
  "DE": {"NSM_ORDERS":{"type":"floor","value":120000}}
}
```

---

## 4) Candidates tab (mixed: formula-fed + PM inputs)

This is what you wanted (and we locked): **Candidates is the PM entry surface for capacity + dependency + mandatory + bundle fields**, while identity fields can be formula-fed from backlog.

Example:

| initiative_key | title (formula)     | country (formula) | department (formula) | engineering_tokens (PM) | deadline_date (PM) | is_mandatory (PM) | bundle_key (PM) | prerequisite_keys (PM) | exclusion_keys (PM) | is_selected_for_run (PM) | notes (PM)      |
| -------------- | ------------------- | ----------------- | -------------------- | ----------------------: | ------------------ | ----------------- | --------------- | ---------------------- | ------------------- | ------------------------ | --------------- |
| INIT-000017    | Payments compliance | UK                | Payments             |                     180 | 2026-02-15         | TRUE              |                 |                        |                     | TRUE                     | Regulatory      |
| INIT-000081    | New checkout        | UK                | Checkout             |                     220 |                    |                   | BNDL-PAYMENTS   | INIT-000012            |                     | TRUE                     | Depends on auth |
| INIT-000044    | Feature X           | DE                | Core                 |                     120 |                    |                   |                 |                        | INIT-000099         | FALSE                    | Blocked         |

---

## 5) Runs tab (system output + sanity fields)

You decided to keep:

* `run_status` (sheet-only messaging)
* `optimization_db_status` (DB status from OptimizationRun.status)

Example:

| run_id                        | scenario_name | constraint_set_name | optimization_db_status | run_status    | created_at        | finished_at       | selected_count | total_objective | capacity_used |
| ----------------------------- | ------------- | ------------------- | ---------------------- | ------------- | ----------------- | ----------------- | -------------: | --------------: | ------------: |
| run_20260105T120102Z_a1b2c3d4 | Q1-2026 Core  | Baseline            | success                | OK: completed | 2026-01-05T12:01Z | 2026-01-05T12:02Z |             12 |            0.82 |          1185 |

---

## 6) Results tab + Gaps tab (system outputs **plus** PM notes/recommendations if you want)

Your latest decision (good): keep system outputs separate, but allow PM notes on Results and PM notes+recommendation on Gaps.

So:

* System writes: the computed fields.
* PM can add: `notes` (Results), `notes` + `recommendation` (Gaps).

---

# Direct answer to your confusion about “min_tokens / max_tokens”

The UX works if you treat it like **a typed-row format**:

* For `capacity_floor / capacity_cap`: use `dimension`, `key`, `min_tokens/max_tokens`.
* For `mandatory / exclude`: use `dimension=initiative`, `key=INIT-...`, leave token columns blank.
* For bundle-like constraints: use `dimension=bundle`, `key=BNDL-...`, leave token columns blank (and encode mode in constraint_type).
* For prereqs: encode dependency in `key` (e.g., `A<-B`) **or** add a new column later (`related_keys`) if you want it cleaner.

---

# 1️⃣ Are these JSON shapes already agreed, or just suggestions?

**Not previously agreed. Just suggestions. We should agree now**

---

## 2️⃣ How will the backend know JSONs have the “right shape”?

Short answer: **it must be enforced via Pydantic models**.
Free-form JSON is **not acceptable** for this system long-term.

### ❌ What we should NOT do

* Store arbitrary JSON blobs without schema
* Trust PM-entered JSON strings blindly
* Infer structure dynamically at runtime

That would break:

* Validation
* Optimization correctness
* Debuggability
* Future migrations

---

## 3️⃣ The correct approach (this is the key decision)

### ✅ Step-by-step, correct architecture

### **A. Each logical JSON gets a Pydantic schema**

Examples (names illustrative):

```python
class CapacityConstraint(BaseModel):
    max_tokens: int
    min_tokens: int | None = None

class TargetConstraint(BaseModel):
    country: str
    kpi_key: str
    value: float
    mode: Literal["floor", "goal"]

class ConstraintSetSchema(BaseModel):
    capacity: CapacityConstraint | None
    targets: list[TargetConstraint]
```

These schemas become:

* **The source of truth**
* Used by:

  * Sheet → DB sync
  * DB → optimizer
  * Optimizer → results
  * Validation & errors back to sheet

---

### **B. Sheets stay UX-friendly, not JSON-centric**

PMs **do not write nested JSON by hand**.

Instead:

* Sheets are **row-based**
* Sync service **compiles rows → validated Pydantic models**
* Invalid rows → explicit row-level errors back to sheet


---

### **C. DB stores structured JSON, but validated**

In DB:

* JSON columns exist ✔️
* But they are **guaranteed to match Pydantic schemas**
* No “unknown keys”, no “magic strings”

---

## 4️⃣ KPI keys in Targets tab — where do they come from?

Yes, your assumption is **correct**:

> **KPI keys in Optimization Targets come from ProductOps → Metrics_Config**

Flow:

```
ProductOps Metrics_Config
        ↓ (authoritative registry)
Optimization Targets (dropdown / validation)
        ↓
ConstraintSet.targets[]
```

That gives you:

* Referential integrity
* KPI discoverability
* No typo-driven bugs

---

## 5️⃣ “Baseline” vs “Aggressive” constraint sets — what do they really mean?

You’re right again:
**“Aggressive” should not live in constraints semantically.**

Here’s the correct interpretation:

### ❌ What “aggressive” should NOT mean

* Not vague strategy
* Not “growth vs stability”
* Not business intent

That belongs to **Scenario**, not ConstraintSet.

---

### ✅ What constraint sets actually represent

A **constraint set is a *configuration envelope***, not a strategy.

Examples:

| Constraint Set | Meaning                                                              |
| -------------- | -------------------------------------------------------------------- |
| Baseline       | Default guardrails (current capacity, legal limits, standard floors) |
| Tight          | More restrictive feasibility (budget cut, staff shortage)            |
| Loose          | Relaxed guardrails (extra capacity approved, temporary flexibility)  |

So:

* **Scenario = intent**
* **Constraint Set = feasibility boundary**

That separation is **correct and powerful**.

---

## 6️⃣ Final, clean mental model (lock this in)

### Relationships

```
Scenario
 ├─ defines intent (objective_mode, weights)
 ├─ has many Runs
       └─ each Run uses exactly ONE ConstraintSet
```

### ConstraintSet

* Is **row-composed in sheets**
* Is **compiled into a validated Pydantic object**
* Is **immutable per run** (important!)

### Targets & constraints

* Are **inputs to ConstraintSet**
* Not standalone models
* Not ad-hoc JSON

---

## 7️⃣ What we should do next (before coding sync services)

**Do NOT write sync code yet.**

Next steps should be:

1. **Formally define Pydantic schemas for:**

   * Capacity constraints
   * KPI targets
   * Any other constraint type you want
2. **Map each sheet column → schema field**
3. **Define validation errors → sheet feedback**
4. **Only then implement Sheet → DB sync**

