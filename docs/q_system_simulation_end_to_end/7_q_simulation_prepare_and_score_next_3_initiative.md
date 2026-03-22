We’ll do **3 initiatives** from different categories:

1. **Monetization** → (Pattern: MONETIZATION_RATE_UPLIFT)
2. **Mandatory / Platform** → (Pattern: LOSS_REDUCTION)
3. **Retention** → (Pattern: RATE_UPLIFT)

And we will follow **exactly the same structure as before**.

---

# Step 3H — Apply Templates to 3 More Initiatives

---

# 🟣 Initiative 4 — Monetization

## Initiative

`INIT-MZ-001 — Dynamic Commission Pricing`

---

## 1️⃣ Backlog Enrichment

### Problem Statement

Current commission structure is static and does not optimize for restaurant segment, demand elasticity, or willingness to pay.

---

### Hypothesis

If commission rates are dynamically adjusted:

* high-value restaurants can sustain higher take rates
  → increasing monetization rate
  → increasing Qlub revenue

---

### Strategic Priority Coefficient

👉 `1.3`

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

👉 `monetization_rate` ✅

---

## Target KPI

👉 `qlub_revenue` ✅

---

# 3️⃣ Template Used

👉 **MONETIZATION_RATE_UPLIFT**

---

# 4️⃣ Metric Chain

```text
monetization_rate → qlub_revenue
```

---

# 5️⃣ Formula (Δ-based)

```text
base_processed_gmv * (monetization_rate_after - monetization_rate_before)
```

---

# 6️⃣ Assumptions

* No impact on transaction volume
* No churn due to higher commission
* Adoption rate remains constant

---

# 7️⃣ Params

* `base_processed_gmv = 72,179,100`
* `monetization_rate_before = 0.0185`
* `monetization_rate_after = 0.0200`

---

# 8️⃣ Computation

```text
72,179,100 * (0.0200 - 0.0185)
= 72,179,100 * 0.0015
≈ 108,268
```

---

# ✅ Contribution

👉 **+108,268 revenue/month**

---

# 9️⃣ KPI Contribution

```json
{
  "qlub_revenue": 108268
}
```

---

---

# 🔴 Initiative 5 — Mandatory / Platform

## Initiative

`INIT-MP-003 — Fraud Detection & Risk Engine`

---

## 1️⃣ Backlog Enrichment

### Problem Statement

Fraudulent transactions and chargebacks lead to revenue leakage and financial risk.

---

### Hypothesis

If we improve fraud detection:

* fraud losses decrease
  → more revenue retained

---

### Strategic Priority Coefficient

👉 `1.4` (high — risk mitigation)

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

👉 `fraud_loss_rate` ✅

---

## Target KPI

👉 `qlub_revenue` ✅

---

# 3️⃣ Template Used

👉 **LOSS_REDUCTION**

---

# 4️⃣ Metric Chain

```text
fraud_loss_rate → recovered_gmv → qlub_revenue
```

---

# 5️⃣ Formula

```text
base_processed_gmv * (fraud_rate_before - fraud_rate_after) * monetization_rate
```

---

# 6️⃣ Assumptions

* Fraud reduction directly translates to recoverable GMV
* No increase in false positives affecting conversion
* Monetization rate unchanged

---

# 7️⃣ Params

* `base_processed_gmv = 72,179,100`
* `fraud_rate_before = 0.015`
* `fraud_rate_after = 0.010`
* `monetization_rate = 0.0185`

---

# 8️⃣ Computation

```text
72,179,100 * (0.015 - 0.010) * 0.0185
= 72,179,100 * 0.005 * 0.0185
≈ 6,673
```

---

# ✅ Contribution

👉 **+6,673 revenue/month (recovered)**

---

# 9️⃣ KPI Contribution

```json
{
  "qlub_revenue": 6673
}
```

---

---

# 🟢 Initiative 6 — Retention / Loyalty

## Initiative

`INIT-RL-003 — Push Notification Re-engagement`

---

## 1️⃣ Backlog Enrichment

### Problem Statement

A large portion of users become inactive after initial usage.

---

### Hypothesis

If we re-engage users via targeted push notifications:

* repeat rate increases
  → more returning diners
  → more diners channeled via Qlub

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

# 2️⃣ KPI Mapping

## Immediate KPI

👉 `repeat_rate` ✅

---

## Target KPI

👉 `monthly_diners_channeled_via_qlub` ✅

---

# 3️⃣ Template Used

👉 **RATE_UPLIFT**

---

# 4️⃣ Metric Chain

```text
repeat_rate → returning_users → monthly_diners_channeled_via_qlub
```

---

# 5️⃣ Formula

```text
existing_qlub_customer_base * (repeat_rate_after - repeat_rate_before)
```

---

# 6️⃣ Assumptions

* Existing customer base remains stable
* No overlap with acquisition initiatives
* Repeat visits convert to diners

---

# 7️⃣ Params

* `existing_qlub_customer_base = 400,000`
* `repeat_rate_before = 0.30`
* `repeat_rate_after = 0.34`

---

# 8️⃣ Computation

```text
400,000 * (0.34 - 0.30)
= 400,000 * 0.04
= 16,000
```

---

# ✅ Contribution

👉 **+16,000 diners/month**

---

# 9️⃣ KPI Contribution

```json
{
  "monthly_diners_channeled_via_qlub": 16000
}
```

---

# 🔍 Consistency Check (Quick)

| Initiative | Pattern        | Output Type | Δ-based | Chain OK |
| ---------- | -------------- | ----------- | ------- | -------- |
| MZ-001     | Monetization   | revenue     | ✅       | ✅        |
| MP-003     | Loss reduction | revenue     | ✅       | ✅        |
| RL-003     | Rate uplift    | diners      | ✅       | ✅        |

---

# 🧠 What we achieved

We now have **6 initiatives fully modeled**, covering:

* supply growth ✅
* demand generation ✅
* AOV economics ✅
* monetization ✅
* risk reduction ✅
* retention ✅

👉 This is enough to:

* test scoring
* test KPI contributions
* test normalization
* test solver behavior

---

# 🚀 Next Step

Now we are ready for:

## 👉 Step 3I — System-Level Validation

Where we:

1. Put all 6 initiatives together
2. Simulate scoring outputs
3. Validate KPI contribution consistency
4. Prepare for **Optimization Center (Candidates + Constraints)**

---

