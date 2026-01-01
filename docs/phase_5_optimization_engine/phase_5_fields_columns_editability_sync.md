
## 1) Metrics_Config in ProductOps

✅ Fully agree.

* **Location**: ProductOps workbook as a new tab: `Metrics_Config`
* **Purpose**: org-level KPI universe + single active North Star + active Strategic KPIs
* **Save mechanism**: via existing `pm.save_selected` (tab-aware branch) once we add a new branch for `Metrics_Config`. For now, we can implement a minimal `MetricsConfigSyncService` exactly like MathModels/Params sync.

This matches your philosophy: ProductOps is the PM control center.

---

## 2) Metric chain entry via MathModels tab


### What I agree with

✅ DB-persisted `metric_chain_json` (initiative-level)
✅ PM-editable via sheets
✅ LLM can suggest it
✅ Stored to DB when PM approves and hits “Save Selected”

### The key clarification (so we don’t create ambiguity)

You proposed: “Add another column to **MathModels** tab for PM to enter chain.”

That’s good, because MathModels is where PM already describes the **logic** and **assumptions**. BUT:


> The metric chain is an initiative-level “causal story”, not a math-model version.

So we can still **enter it in MathModels**, but we should store it **on the Initiative** (or in a related InitiativeMetricChain table later), not in InitiativeMathModel.

### How to implement cleanly (recommended)

* Add **two columns** to MathModels:

  1. `metric_chain_text` (PM editable; human-friendly)
  2. `llm_suggested_metric_chain_text` (LLM writes; PM read-only)
     *(Optional: `metric_chain_approved` if you want separate approval; but you can reuse existing `approved_by_user` if you prefer, which I do)*

* When PM sets `approved_by_user = TRUE` and runs `pm.save_selected` on MathModels tab:

  * Save:

    * math model fields → `InitiativeMathModel`
    * metric chain → `Initiative.metric_chain_json` (after parsing)

### Parsing format (so it’s usable)

Let PM enter something simple like:

**Option A (simple arrow chain, v1)**

```
page_load_time -> checkout_conversion_rate -> gmv
```

Backend converts it to JSON graph:

```json
{"nodes":["page_load_time","checkout_conversion_rate","gmv"],
 "edges":[["page_load_time","checkout_conversion_rate"],
          ["checkout_conversion_rate","gmv"]]}
```

This keeps PM UX dead simple and still yields structured JSON for DB.

✅ So yes: I’m happy with your design, with the refinement that the chain is edited in MathModels but **persisted onto Initiative.metric_chain_json**.

---

## LOCKED decisions (confirm)

1. `Metrics_Config` tab exists in **ProductOps** and is the authoritative UI for North Star + Strategic KPIs.
2. Metric chain:

   * PM enters it in **ProductOps → MathModels**
   * LLM can suggest it into a separate suggestion column
   * On `pm.save_selected` (MathModels tab), backend persists it into **DB Initiative.metric_chain_json** (structured JSON)

Locked ✅:

ProductOps/Metrics_Config is the authoritative UI for North Star + Strategic KPIs.

ProductOps/MathModels contains PM-entered metric chain + LLM suggestion, and pm.save_selected persists to DB Initiative.metric_chain_json.

Sync directions as we clarified are now fixed.

---

# Step 4 (Revised) — with explicit sheet/tab per sync direction

## 4.1 Governance types

* **Editable**: PM/owners can set; saved from a specific tab into DB.
* **Derived**: backend computes; written to specific tabs for visibility.
* **Enforced**: backend validates at save/run time; failures written back to the initiating tab’s `run_status`.


Locked ✅

## What “editable allowlists” means

An **editable allowlist** is the explicit list of columns that the backend is allowed to accept from a given sheet/tab when the PM clicks **Save** (Sheet → DB).

It’s the same idea you already use in:

* `BacklogService.CENTRAL_EDITABLE_FIELDS`
* `IntakeService.INTAKE_EDITABLE_FIELDS`

Purpose:

* prevent accidental writes from computed/output columns
* prevent PMs from unknowingly overwriting system fields
* make sync deterministic and safe

---

## What we did in 4.6 vs what we’ll do in 4.7

### Step 4.6 (what we just finished)

We locked the **governance model** at a conceptual level:

* which fields are **Editable vs Derived vs Enforced**
* who owns them (PM vs backend vs LLM)
* where they live (DB vs sheet-only)
* which **tab** is the authoritative UI surface
* and which direction sync flows (Sheet → DB vs DB → Sheet), now explicitly by tab

So 4.6 = “policy + ownership + surfaces”.

---

### Step 4.7 (what we do next)

We translate that policy into **implementation contracts**:

For each relevant tab, we will define:

1. **ALLOWLIST_COLUMNS_<TAB>**
   Exactly which columns are writable from that tab into DB.

2. For each allowed column:

   * target DB field (or model)
   * type coercion rules (bool/float/json/list/date)
   * validation rules (hard fail vs warning)

3. For tab-aware saves:

   * how `pm.save_selected` routes to the correct SyncService
   * and how each SyncService uses its allowlist when building updates

So 4.7 = “paste-ready allowlists + mapping rules” that can be dropped into:

* `app/sheets/models.py` (header aliases + allowlist constants)
* plus the corresponding `*_sync_service.py` update mapping

---

## 4.2 Global KPI configuration (NEW, in ProductOps)

### North Star metric (global, single)

* Type: **Editable + Enforced**
* Owner: **PM/Leadership**
* DB: **Yes** (`OrganizationMetricsConfig.north_star_kpi_key`)
* Sheet UI: **ProductOps → Metrics_Config**
* Sync:

  * **ProductOps/Metrics_Config → DB** (save)
  * **DB → ProductOps/Metrics_Config** (refresh/display; optional v1)

### Strategic KPI set (global)

* Type: **Editable + Enforced**
* Owner: **PM/Leadership**
* DB: **Yes** (`OrganizationMetricsConfig.strategic_kpi_keys`)
* Sheet UI: **ProductOps → Metrics_Config**
* Sync:

  * **ProductOps/Metrics_Config → DB**
  * **DB → ProductOps/Metrics_Config** (optional v1)

Enforcement:

* Exactly one active north star
* Strategic KPIs must be from defined KPI keys

---

## 4.3 Initiative-level metric chain

### metric_chain_json (initiative-level structured)

* Type: **Editable (advanced)**
* Owner: **PM** (LLM suggests)
* DB: **Yes** (`Initiative.metric_chain_json`)
* Sheet UI (edit surface): **ProductOps → MathModels**

  * `metric_chain_text` (PM)
  * `llm_suggested_metric_chain_text` (LLM)
* Sync:

  * **ProductOps/MathModels → DB** (on `pm.save_selected` when formula approved)
  * **DB → ProductOps/MathModels** (optional: display the canonical chain; v1 can be one-way)

Enforcement:

* optional v1 (warning only if invalid)
* later required for explainability

---

## 4.4 Initiative fields & Optimization Center surfaces (explicit)

### A) Initiative optimization inputs (canonical DB truth)

These are **initiative properties**: edited in **Central Backlog** (preferred) and/or **Optimization Center → Candidates** (if we allow edits there).

I’ll specify the primary edit surface and the allowed secondary one.

#### Eligibility

* `is_optimization_candidate`

  * Editable by PM
  * Primary sheet: **Central Backlog**
  * Optional secondary: **Optimization Center/Candidates**
  * Sync:

    * **Central Backlog → DB** (Flow1 backlog update / pm.save in backlog)
    * **Optimization Center/Candidates → DB** (if we implement candidate-save)
    * **DB → Central Backlog** (backlog sync regen)
    * **DB → Optimization Center/Candidates** (candidate refresh/write)

* `candidate_period_key`

  * Same sync surfaces as above

#### Capacity

* `engineering_tokens`, variants, `scope_mode`

  * Editable by PM/Eng
  * Primary sheet: **Central Backlog**
  * Optional secondary: **Optimization Center/Candidates**
  * Sync: same pattern as above
  * Enforcement on optimization run: required for selected candidates

#### Dimensions

* `market`, `department`, `category`

  * Editable by PM (backend can suggest)
  * Primary sheet: **Central Backlog**
  * Optional secondary: **Optimization Center/Candidates**
  * Sync: same pattern

#### Governance

* `is_mandatory`, `mandate_reason`, `bundle_key`, `program_key`, `prerequisite_keys`, `exclusion_keys`, `synergy_group_keys`

  * Editable by PM
  * Primary sheet: **Central Backlog**
  * Optional secondary: **Optimization Center/Candidates**
  * Sync: same pattern
  * Enforcement:

    * mandate_reason required if is_mandatory true
    * prerequisite/exclusion keys must resolve

#### KPI fields

* `immediate_kpi_key`

  * Editable by PM
  * Primary: **Central Backlog** or **ProductOps/Scoring_Inputs** (if you already capture it there)
  * Optional: **Optimization Center/Candidates**
  * Sync: Sheet → DB from whichever surface is enabled

* `kpi_contribution_json`

  * Editable by PM/Analytics
  * Primary sheet (recommended): **Central Backlog** OR **ProductOps** (we can decide exact tab later; not Optimization Center by default)
  * Sync:

    * **(Chosen primary tab) → DB**
    * **DB → Optimization Center/Candidates** (for display)
  * Enforcement:

    * keys ⊆ {North Star + Strategic KPIs} from ProductOps/Metrics_Config

---

### B) Optimization Center tabs (Phase 5 sheet)

#### Candidates tab

* `is_selected_for_run`

  * Sheet-only (PM)
  * Sync: **None** (backend reads it but doesn’t persist)

* `run_status`, `updated_source`

  * Sheet-only (backend writes)
  * Sync: **DB/ActionRun → Optimization Center/Candidates** (write)

Most other columns in Candidates are:

* either DB-derived fields (initiative metadata)
* or derived display (north_star_contribution = from kpi_contribution_json)

So:

* **DB → Optimization Center/Candidates** is dominant.

#### Scenario_Config tab

* Editable scenario inputs (PM)
* Sync:

  * **Optimization Center/Scenario_Config → DB** (OptimizationScenario)
  * **DB → Optimization Center/Scenario_Config** (optional refresh)

#### Constraints tab

* Editable constraints (PM)
* Sync:

  * **Optimization Center/Constraints → DB** (OptimizationConstraintSet)
  * **DB → Optimization Center/Constraints** (optional refresh)

#### Targets tab

* Editable targets (PM/Analytics)
* Sync:

  * **Optimization Center/Targets → DB** (targets_json or a normalized table)
  * **DB → Optimization Center/Targets** (optional refresh)

#### Runs tab

* Derived
* Sync:

  * **DB → Optimization Center/Runs** only

#### Results_Portfolio tab

* Derived (v1)
* Sync:

  * **DB → Optimization Center/Results_Portfolio** only

#### Gaps_And_Alerts tab

* Derived (v1)
* Sync:

  * **DB → Optimization Center/Gaps_And_Alerts** only

---

