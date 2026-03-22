This is a **core conceptual hinge** for Phase 5, so let’s lock it down cleanly and unambiguously.

---

## 1️⃣ First: correcting the ambiguity (important)


### Corrected statement (this is the one we should lock):

> **`kpi_contribution_json` does NOT store objective weights.**
> It stores **initiative-level impact estimates** (coefficients in the *constraint/objective summation*),
> while **`scenario.objective_weights_json` stores the weights of KPIs in the objective function**.

So:

* **Contributions ≠ Weights**
* They live at **different layers**
* They multiply each other **inside the objective**

Let’s formalize this.

---

## 2️⃣ What `kpi_contribution_json` actually is (initiative-level)

### Definition (locked)

> **`kpi_contribution_json` is a per-initiative dictionary of estimated marginal contributions to KPIs, expressed in the KPI’s native unit, for the given planning period.**

Key properties:

* It is **initiative-specific**
* It is **period-scoped implicitly** (e.g. “expected impact over Q1”)
* It contains **no priorities or preferences**
* It contains **only estimates of impact**, not desirability

### Shape (example)

```json
{
  "north_star_gmv": 120000,
  "gmv": 120000,
  "conversion_rate": 0.002,
  "retention_30d": 0.01
}
```

This answers the question:

> *“If we do THIS initiative, how much does it move KPI X?”*

---

### Who sets it (and how)

This is important.

**Primary owner**

* PM (with Analytics / Finance input)

**How it’s built**

* From:

  * the initiative’s **math model** (Phase 4)
  * or a simpler estimation model if math model not present
* Often:

  * Math model outputs multiple KPI deltas
  * PM chooses which ones to persist into `kpi_contribution_json`

**LLM’s role**

* Can help:

  * suggest structure
  * sanity-check numbers
  * derive implied KPI deltas from narrative
* **Never authoritative**

**Backend’s role**

* Validation only:

  * numeric
  * non-null where required
  * keys exist in allowed KPI universe

---

## 3️⃣ What `scenario.objective_weights_json` actually is (portfolio-level)

### Definition (locked)

> **`scenario.objective_weights_json` is a portfolio-level preference vector that expresses how important each KPI is relative to others for THIS optimization run.**

Key properties:

* It is **scenario-specific**
* It expresses **strategy**, not impact
* It is the **w** in the weighted objective
* It is *not* initiative-specific

### Shape (example)

```json
{
  "gmv": 1.0,
  "retention_30d": 0.3,
  "conversion_rate": 0.2
}
```

This answers the question:

> *“For THIS planning cycle, how do we trade off different KPIs?”*

---

## 4️⃣ How they work together in the optimizer (this is the key)

Let’s now tie it all together **mathematically and conceptually**.

---

## 5️⃣ Concrete e-commerce example (fully worked)

### Context

* Company: e-commerce marketplace
* Period: **2026-Q1**
* Capacity: 1,000 engineering tokens
* Candidate initiatives: A, B, C

### KPIs

* `gmv` (GBP)
* `retention_30d` (absolute fraction, e.g. +0.01 = +1%)
* `conversion_rate` (absolute fraction)

---

### Initiative A — “Improve checkout UX”

**kpi_contribution_json**

```json
{
  "gmv": 120000,
  "conversion_rate": 0.002
}
```

Interpretation:

* If selected, this initiative is expected to:

  * increase GMV by £120k in Q1
  * increase conversion by +0.2pp

---

### Initiative B — “Loyalty program v1”

```json
{
  "gmv": 80000,
  "retention_30d": 0.015
}
```

---

### Initiative C — “Infra cost optimization”

```json
{
  "gmv": 40000
}
```

---

## 6️⃣ Scenario 1 — Pure North Star maximization

### Objective mode

```
objective_mode = "north_star"
north_star_kpi = "gmv"
```

### Objective function

Mathematically:

[
\max \sum_i \text{GMV}_i \cdot x_i
]

Expanded:

[
\max (120000 \cdot x_A + 80000 \cdot x_B + 40000 \cdot x_C)
]

Notes:

* `kpi_contribution_json["gmv"]` is used
* **No weights**
* Other KPIs ignored for objective (but may appear in reporting)

---

## 7️⃣ Scenario 2 — Weighted multi-objective optimization

### Scenario weights

**scenario.objective_weights_json**

```json
{
  "gmv": 1.0,
  "retention_30d": 0.4,
  "conversion_rate": 0.2
}
```

This encodes:

* GMV is most important
* Retention matters, but less
* Conversion matters even less

---

### Objective function (this is the key formula)

For each initiative ( i ):

[
\text{score}*i = \sum*{k \in KPIs} w_k \cdot c_{i,k}
]

Where:

* ( c_{i,k} ) comes from `kpi_contribution_json`
* ( w_k ) comes from `scenario.objective_weights_json`

---

### Initiative A score

[
1.0 \cdot 120000 ;+; 0.2 \cdot 0.002
]

(you may normalize units later, but conceptually:)

→ dominated by GMV

---

### Initiative B score

[
1.0 \cdot 80000 ;+; 0.4 \cdot 0.015
]

Retention meaningfully boosts B relative to A

---

### Full objective

[
\max \sum_i \left( \sum_k w_k \cdot c_{i,k} \right) x_i
]

This is exactly why:

* **Contributions live on initiatives**
* **Weights live on scenarios**

They are multiplied together **inside the objective**, but they are conceptually different.

---

## 8️⃣ Scenario 3 — Lexicographic (targets first)

Here’s where it gets even clearer.

### Targets

```json
{
  "retention_30d": 0.02
}
```

### Constraint

[
\sum_i c_{i,\text{retention}} \cdot x_i \ge 0.02
]

This uses:

* **ONLY `kpi_contribution_json`**
* **NO weights**

Then, once feasible portfolios are found:

* secondary objective kicks in (e.g. GMV maximization)

---

## 9️⃣ Final locked understanding (this is the TL;DR)

### 🔒 Locked definitions

* **`kpi_contribution_json`**

  * Initiative-level
  * “If we do THIS initiative, how much does it move KPI X?”
  * Used in:

    * objective summations
    * target constraints
    * reporting & gaps
  * **Never contains weights or priorities**

* **`scenario.objective_weights_json`**

  * Scenario-level
  * “For THIS planning cycle, how much do we care about KPI X vs Y?”
  * Used **only** to weight contributions in the objective

### 🔑 Mental model

```
initiative impact (c_i,k)  ×  scenario preference (w_k)
           ↓                         ↓
     kpi_contribution_json   objective_weights_json
           ↓                         ↓
           →  optimizer objective function
```

---

## 🔟 Baseline Normalization & Gap-Based Objectives (Phase 5.1)

### The Problem: Absolute vs Incremental Targets

KPI contributions in `kpi_contribution_json` are **incremental** (delta impact).

But business targets in the Targets tab are often **absolute** (final state to reach):

* "Reach GMV = £10M" vs "Add £500K GMV"
* "Retention = 85%" vs "Improve retention by +2pp"

Without baseline context, the optimizer can't distinguish these cases.

---

### Solution: Baseline Values on Targets

The **Targets** tab now supports an optional `Baseline Value` column.

```
| Dimension | Dimension Key | KPI Key | Target Type | Value | Baseline Value |
|-----------|---------------|---------|-------------|-------|----------------|
| all       | all           | gmv     | >=          | 10000000 | 9500000     |
| all       | all           | retention_30d | >= | 0.85 | 0.82 |
```

**Gap calculation:**
```
effective_gap = target_value - baseline_value
```

For GMV: £10M - £9.5M = £500K gap to close

---

### Objective Mode Policies (Production)

#### NORTH_STAR Mode

* **Policy:** Maximize raw contribution to single KPI
* **Formula:** `max(sum(contrib_i * x_i))`
* **Normalization:** None (raw values)
* **Baseline effect on objective:** None (contributions are incremental deltas)
* **Baseline effect on feasibility:** Baselines can still affect feasibility
  indirectly through target-floor constraints (Step 7) on the same KPI

#### WEIGHTED_KPIS Mode

* **Policy:** Maximize weighted sum of **normalized** contributions
* **Formula:** `max(sum_k(w_k * sum_i(contrib_i,k / scale_k) * x_i))`
* **Normalization:** `scale_k` derived from targets with gap-based policy

**Normalization scale resolution (in order):**

1. **Gap-based** (when baseline provided): `scale_k = target - baseline`
2. **Incremental** (no baseline): `scale_k = target_value`
3. **Fallback**: `scale_k = 1.0` (warning logged)

**Already-satisfied handling:**

If `baseline >= target` for a KPI:
* The KPI is **excluded from the weighted objective**
* Rationale: No gap to close, contributions don't help

---

### Target Floors (Step 7 constraints)

Target floors enforce minimum KPI thresholds as hard constraints.

**Gap-based floor (when baseline provided):**
```
effective_floor = max(target - baseline, 0)
```

**Policy decisions:**
* If `baseline >= target`: Floor constraint skipped (already satisfied)
* If baseline is malformed: `model_invalid` returned (no silent fallback)

---

### Diagnostics

The solver logs detailed normalization mode breakdown:

```json
{
  "normalization_modes": {
    "incremental": 2,
    "gap_based": 3,
    "already_satisfied": 1,
    "fallback": 0
  },
  "already_satisfied_kpis": ["kpi_x"],
  "effective_kpis": ["kpi_a", "kpi_b", "kpi_c", "kpi_d", "kpi_e"],
  "objective_degenerate_to_feasibility_only": false
}
```

This provides visibility into how each KPI is treated in the objective function.

**Degenerate objective warning:** If all weighted KPIs are already satisfied,
`objective_degenerate_to_feasibility_only: true` is logged and the optimization
effectively becomes a feasibility check (any valid portfolio is equally good).

---

### Best Practices

1. **Use baselines when targets are absolute business goals**
   - "Reach £10M GMV" → set baseline to current GMV

2. **Omit baselines when targets are incremental**
   - "Add £500K GMV" → no baseline needed

3. **Negative baselines are allowed for signed KPIs**
   - Profit/loss margins, NPS, net cash flow can have negative baselines
   - Example: `baseline = -50000` (loss), `target = 100000` (profit goal)

4. **Negative targets are also allowed**
   - For signed KPIs with negative goals (e.g., "reduce loss to -10K")
   - Gap = target - baseline works correctly regardless of sign

5. **baseline > target is allowed (already satisfied)**
   - Schema accepts this; solver treats as "already satisfied"
   - Target floors are skipped (no constraint needed)
   - KPI excluded from weighted objective (no gap to close)

6. **Watch for degenerate objectives**
   - If `objective_degenerate_to_feasibility_only: true`, all KPIs are satisfied
   - Consider whether targets are set appropriately (too easy?)

---

