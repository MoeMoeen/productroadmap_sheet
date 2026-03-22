---

# 🔴 First — Critical Concept 

## Absolute vs Incremental Contribution

### ✅ Correct approach (for optimization):

👉 We MUST use **incremental contribution (uplift / delta)**

### Why:


* Optimization = maximize objective function
* Objective = **sum of contributions of selected initiatives**

So mathematically:

[
\text{Total Value} = \sum (\Delta KPI_i)
]

NOT:

[
\sum (\text{absolute KPI values})
]

---

## 🔥 Important principle going forward:

> Every initiative must produce:

### 👉 **Δ (change) in KPI, NOT absolute value**

---

# ✅ NOW — FULL VERSION 

Keeping your structure, fixing only what’s needed.

---

# Step 3B — Initiative 1 End-to-End (Corrected)

---

## Initiative

`INIT-RA-001 — Self-Serve Restaurant Onboarding Flow`

---

# 1️⃣ Backlog Enrichment (Central Backlog)

### Problem Statement

Restaurants onboarding is currently manual and sales-driven, limiting scalability.

---

### Hypothesis

Self-serve onboarding will increase onboarding conversion rate and accelerate growth of active restaurants.

---

### Strategic Priority Coefficient

👉 `1.2`

---

### Candidate Period Key

👉 `Q2_2026`

---

### Is Optimization Candidate

👉 `TRUE`

---

### Active Scoring Framework

👉 `MATH_MODEL`

---

### Use Math Model

👉 `TRUE`

---

# 2️⃣ KPI Mapping (CORRECTED)

## Immediate KPI

👉 `onboarding_conversion_rate` ✅

---

## Target KPI

👉 `active_restaurants` ✅

---

# 3️⃣ Math Model (MathModels Tab)

---

## Core fields

### initiative_key

`INIT-RA-001`

---

### model_name

`self_serve_onboarding_uplift_model`

---

### target_kpi_key

`active_restaurants`

---

### immediate_kpi_key

`onboarding_conversion_rate`

---

### is_primary

`TRUE`

---

## Metric Chain (FIXED)

```text
onboarding_conversion_rate → new_restaurants → active_restaurants
```

---

## Formula (CRITICAL FIX — DELTA MODEL)

We now model **uplift**, not absolute:

```text
lead_volume * (conversion_rate_after - conversion_rate_before)
```

---

## Assumptions

* Lead volume remains stable
* Conversion uplift is causal from self-serve onboarding
* No bottleneck in onboarding capacity
* All new restaurants become active within the period

---

## approved_by_user

👉 `TRUE`

---

# 4️⃣ Seed Params

Running:

👉 **Seed Math Params**

Extracts:

* `lead_volume`
* `conversion_rate_before`
* `conversion_rate_after`

---

# 5️⃣ Params Tab (UPDATED)

---

## Param 1: lead_volume

* Value: `500`

---

## Param 2: conversion_rate_before

* Value: `0.08`

---

## Param 3: conversion_rate_after

* Value: `0.12`

---

# 6️⃣ Computed Output (FIXED)

```text
500 * (0.12 - 0.08) = 20
```

---

## Correct logic:

### Initiative:

Self-serve onboarding

### What does it directly affect?

👉 NOT active restaurants directly
👉 It affects **conversion behavior**

---

## ✅ Correct Immediate KPI

👉 `onboarding_conversion_rate`

---

## Target KPI

👉 `active_restaurants` (valid strategic KPI)

---

## Correct chain

```text
onboarding_conversion_rate → new_restaurants → active_restaurants
```

---

## Interpretation:

* Initiative improves **conversion rate**
* That increases **new restaurants**
* That increases **active restaurants**

---
## ✅ Final Contribution

👉 **+20 active restaurants per month**

---

# 7️⃣ Run Scoring (Scoring_Inputs)

* framework = `MATH_MODEL`
* run:

👉 **Score Selected**

---

# 8️⃣ KPI Contributions (CORRECTED)

```json
{
  "active_restaurants": 20
}
```

---

# 🧠 Final Interpretation (Corrected)

This initiative contributes:

👉 **+20 incremental restaurants/month**

NOT 60.

---


---

# Step 3C — Initiative 2 (Discovery / Demand Generation)

We will now model a **traffic → diner → KPI chain**, which is structurally different from onboarding.

---

## Initiative

`INIT-DG-002 — Incentive Engine for Diner Acquisition`

---

# 1️⃣ Backlog Enrichment (Central Backlog)

### Problem Statement

Qlub currently lacks a scalable, systematic way to drive incremental diner traffic to partner restaurants.

---

### Hypothesis

If we introduce a targeted incentive engine (discounts, cashback, dynamic offers), then:

* more users will engage with Qlub discovery
* more discovery traffic will convert into actual restaurant visits
  → increasing diners channeled via Qlub

---

### Strategic Priority Coefficient

👉 `1.3`
(High — directly drives one of the **core strategic KPIs**)

---

### Candidate Period Key

👉 `Q2_2026`

---

### Is Optimization Candidate

👉 `TRUE`

---

### Active Scoring Framework

👉 `MATH_MODEL`

---

### Use Math Model

👉 `TRUE`

---

# 2️⃣ KPI Mapping (CRITICAL)

## Immediate KPI

👉 `triggered_qlub_discovery_traffic`

Why:

* Incentives directly affect **triggered traffic**
* Not final diners yet

---

## Target KPI

👉 `monthly_diners_channeled_via_qlub`

---

# 3️⃣ Math Model (MathModels Tab)

---

## Core fields

### initiative_key

`INIT-DG-002`

---

### model_name

`incentive_engine_diner_uplift_model`

---

### target_kpi_key

`monthly_diners_channeled_via_qlub`

---

### immediate_kpi_key

`triggered_qlub_discovery_traffic`

---

### is_primary

`TRUE`

---

# 🔗 Metric Chain (CORRECT)

```text
triggered_qlub_discovery_traffic → discovery_conversion_rate → monthly_diners_channeled_via_qlub
```

---

## Interpretation

* Incentives → more **triggered traffic**
* Traffic → converts via **conversion rate**
* → produces **incremental diners**

---

# 4️⃣ Formula (Δ-based, multi-step)

We model:

```text
traffic_uplift * discovery_conversion_rate
```

---

## Meaning:

* traffic increases by X
* X converts to diners via conversion rate

---

# 5️⃣ Assumptions

* Conversion rate remains stable
* Incentives only affect traffic, not conversion rate
* Traffic uplift is incremental (not cannibalized)
* No supply constraint on restaurants

---

### approved_by_user

👉 `TRUE`

---

# 6️⃣ Seed Params

Extracted params:

* `traffic_uplift`
* `discovery_conversion_rate`

---

# 7️⃣ Params Tab (Fill Values)

---

## Param 1: traffic_uplift

👉 `120,000`

Meaning:

* +120k incremental monthly discovery traffic from incentives

---

## Param 2: discovery_conversion_rate

👉 `0.60`

(from baseline model)

---

# 8️⃣ Computed Output

```text
120,000 * 0.60 = 72,000
```

---

# ✅ Final Contribution

👉 **+72,000 diners per month via Qlub**

---

# 9️⃣ Run Scoring (Scoring_Inputs)

* framework = `MATH_MODEL`
* run:

👉 **Score Selected**

---

# 🔟 KPI Contributions Output

```json
{
  "monthly_diners_channeled_via_qlub": 72000
}
```

---

# 🧠 Interpretation

This initiative contributes:

👉 **+72k incremental diners/month**

Which is:

* ~20% uplift over baseline (360k)
* very meaningful growth lever

---

# 🔥 What we validated here

## 1. Multi-step chain works

Traffic → Conversion → KPI ✅

---

## 2. Immediate KPI is NOT final KPI

Correct separation ✅

---

## 3. Δ-based modeling holds

Only incremental traffic used ✅

---

## 4. Different KPI type handled

Not supply-side, but demand-side KPI ✅

---

# ⚠️ Subtle Risk (Important)

This model assumes:

👉 traffic uplift is **purely incremental**

But in reality:

* some traffic may be cannibalized
* some incentives reduce margin

We will handle that later (in monetization models)

---

# 🔜 Next Step

Now we do **third initiative**:

👉 AOV or Monetization (financial chain)

This will introduce:

* revenue linkage
* deeper propagation
* multi-KPI implications

---


---

# Step 3D — Initiative 3 (AOV → Revenue Chain)

## Initiative

`INIT-AOV-001 — Smart Upsell During Payment Flow`

---

# 1️⃣ Backlog Enrichment (Central Backlog)

### Problem Statement

Current payment flow is purely transactional and does not encourage upsell or add-ons, leaving AOV optimization untapped.

---

### Hypothesis

If we introduce contextual upsell recommendations during payment:

* diners will add items or upgrade orders
  → increasing average order value
  → increasing GMV
  → increasing Qlub revenue

---

### Strategic Priority Coefficient

👉 `1.25`

---

### Candidate Period Key

👉 `Q2_2026`

---

### Is Optimization Candidate

👉 `TRUE`

---

### Active Scoring Framework

👉 `MATH_MODEL`

---

### Use Math Model

👉 `TRUE`

---

# 2️⃣ KPI Mapping

## Immediate KPI

👉 `average_order_value` ✅

---

## Target KPI

👉 `qlub_revenue` ✅ (North Star)

---

# 3️⃣ Metric Chain (CRITICAL)

```text
average_order_value → restaurant_gmv → qlub_processed_gmv → qlub_revenue
```

---

## Interpretation

* Increase AOV
  → increases restaurant GMV
  → increases processed GMV
  → increases revenue

---

# 4️⃣ Formula (Δ-based, revenue-oriented)

We model incremental revenue directly:

```text
delta_aov * monthly_transactions * net_adoption_rate * monetization_rate
```

---

## Why this works

We collapse the chain mathematically:

* AOV increase → multiplies all transactions
* only portion processed via Qlub → net adoption
* Qlub monetizes → monetization rate

---

# 5️⃣ Assumptions

* Transaction volume remains stable
* Upsell affects only AOV (not traffic or conversion)
* Adoption rate unaffected
* Monetization rate unchanged
* Upsell is incremental (no substitution)

---

### approved_by_user

👉 `TRUE`

---

# 6️⃣ Seed Params

Extracted params:

* `delta_aov`
* `monthly_transactions`
* `net_adoption_rate`
* `monetization_rate`

---

# 7️⃣ Params Tab (Fill Values)

---

## Param 1: delta_aov

👉 `+1.5`

Meaning:

* +1.5 currency units per order

---

## Param 2: monthly_transactions

We compute from baseline:

From Step 1:

* per restaurant = 2,137 transactions
* total restaurants = 1,200

👉 `2,137 × 1,200 ≈ 2,564,400`

So:

👉 `monthly_transactions = 2,564,400`

---

## Param 3: net_adoption_rate

👉 `0.67`

---

## Param 4: monetization_rate

👉 `0.0185`

---

# 8️⃣ Computed Output

```text
1.5 * 2,564,400 * 0.67 * 0.0185
```

Let’s calculate step-by-step:

* 1.5 × 2,564,400 = 3,846,600
* × 0.67 = 2,577,222
* × 0.0185 ≈ **47,676**

---

# ✅ Final Contribution

👉 **+47,676 revenue per month**

---

# 9️⃣ Run Scoring

* framework = `MATH_MODEL`
* run:

👉 **Score Selected**

---

# 🔟 KPI Contributions Output

```json
{
  "qlub_revenue": 47676
}
```

---

# 🧠 Interpretation

This initiative contributes:

👉 **+47.7k revenue/month**

👉 ≈ +143k per quarter

---

# 🔥 What we validated here

## 1. Multi-hop KPI chain works

AOV → GMV → Revenue ✅

---

## 2. Direct financial modeling works

We didn’t need to explicitly model every node in scoring — we compressed it into formula ✅

---

## 3. Different KPI types are now unified

We now have:

* Supply-side (restaurants)
* Demand-side (diners)
* Financial (revenue)

👉 All comparable via contributions

---

# ⚠️ Important Observations

## 1. This is now directly comparable in optimization

Now solver can compare:

* +20 restaurants
* +72k diners
* +47k revenue

👉 (depending on objective function)

---

## 2. Hidden assumptions risk

This model assumes:

* no elasticity effects
* no cannibalization
* no operational constraints

Later, your system can evolve to:

* multi-variable models
* scenario-based assumptions
* confidence scoring

---



---

---

# 🔥 One Clear Rule to Remember

## Your system now has **two valid modes**

---

## Mode 1 — weighted_kpis (your normalization)

👉 Current modeling (what we did) is **already sufficient**

You can keep:

* Initiative 1 → restaurants
* Initiative 2 → diners
* Initiative 3 → revenue

✔ Solver handles normalization
✔ Everything comparable
✔ Very flexible

---

## Mode 2 — north_star

👉 Requires:

**ALL initiatives → revenue**

So:

* onboarding → restaurants → GMV → revenue
* discovery → diners → GMV → revenue
* AOV → already revenue

---

# 🧠 5. Key Insight (This is BIG)

You now have **two layers of modeling**:

---

## Layer A — Local KPI Modeling (what we just did)

* intuitive
* PM-friendly
* matches product thinking

---

## Layer B — Objective Projection

Depends on mode:

### weighted_kpis:

👉 normalization handles it automatically

### north_star:

👉 PM must model full propagation to revenue

---

