PHASE 4: Math Models

## 1. Mental model: which *tabs* do what?

From the PM’s point of view there are **three main places** (all inside the ProductOps workbook, plus the Central Backlog sheet):

### 1) Central Backlog sheet (already exists)

* One row per initiative (global view).
* Main columns that matter for math models:

  * `initiative_key`
  * `title`, `problem_statement`, etc.
  * `active_scoring_framework`  (dropdown: `RICE`, `WSJF`, `MATH_MODEL`, …)
  * `use_math_model`            (checkbox)
  * `value_score`, `effort_score`, `overall_score` (final *active* scores)
  * `llm_summary`, `llm_notes`, etc.

> **From PM POV:**
> “This is where I **decide** that an initiative should use a math model (or RICE/WSJF/etc.) and where I see the final scores. I don’t define formulas or parameters here.”

---

### 2) ProductOps → **MathModels tab**

*(one row per initiative per math model/framework instance)*

This is the **“model definition & explanation”** tab.

Key columns the PM sees (for v1):

* `initiative_key` (read-only, filled by backend)
* `framework` (e.g. `MATH_MODEL`, `RICE`, `WSJF` in future, or custom name)
* `model_name` (editable): short name, e.g. `CheckoutConvValue2025`
* `model_description_free_text` (editable): PM’s natural language description of how value *should* be modeled
* `model_prompt_to_llm` (editable, optional): extra instructions to the LLM (“propose an annual £ formula”, etc.)
* `llm_suggested_formula_text` (read-only to PM): formula suggested by LLM
* `assumptions_text` (editable after LLM seeds): assumptions behind the model
* `llm_notes` (editable after LLM seeds): explanation / commentary
* `formula_text_final` (editable): **approved** formula actually used in scoring
* `formula_text_approved` (checkbox): PM marks when final formula is ready
* `version` (read-only, optional): auto-incremented when formula changes
* (Future) `scenario_label` if/when we support multiple scenarios per initiative.

> **From PM POV:**
> “This is where I **explain, co-design, and approve** the math logic: what the formula is and what assumptions it makes.”

---

### 3) ProductOps → **Params tab**

*(one row per initiative–framework–parameter)*

This is the **“numbers & knobs”** tab.

Key columns the PM / Analytics / Finance see:

* `initiative_key` (read-only)
* `framework` (e.g. `MATH_MODEL`, `RICE`, `WSJF`, `CUSTOM_X`)
* `param_name` (read-only for auto-seeded ones; editable for manual extras)
* `param_display` (editable): human-friendly label (“Baseline Conversion Rate”)
* `description` (editable): what this parameter means
* `value` (editable): the actual value for this initiative (e.g. `0.04`, `500000`, `45`)
* `unit` (editable): `%`, `£`, `sessions`, `days`, etc.
* `min`, `max` (editable): optional bounds for uncertainty
* `source` (editable): `PM`, `Analytics`, `Finance`, `Eng`, `LLM`
* `approved` (checkbox): mark once value is agreed / good enough for scoring
* `is_auto_seeded` (read-only): whether backend created this row automatically (from template/formula/LLM)
* `last_updated_by`, `last_updated_at` (read-only, optional)
* `notes` (editable): free-form comments (“using latest Q4 traffic”, etc.)

> **From PM/Analytics/Finance POV:**
> “This is where we **enter and maintain the numbers** for each variable in the formula (or RICE/WSJF inputs, etc.), then approve them.”

---

## 2. PM journey phases (math model path)

From the PM’s perspective, the **math model journey** has 4 phases:

1. **Turn on math model for an initiative**
   (Central Backlog: choose `MATH_MODEL`, set `use_math_model = TRUE`.)

2. **Define the model** (formula & assumptions)
   (MathModels tab: describe, get LLM help if desired, finalize formula and assumptions.)

3. **Fill and approve parameters**
   (Params tab: numeric values, units, ranges, approvals.)

4. **Let the system compute scores & use them**
   (Backend evaluates → scores appear in Central Backlog & ProductOps Scoring tab.)

Right now we’re zooming into **Phase 2 (creation)**.

---

## 3. Creation flows: Manual, LLM-assisted, Hybrid (updated)

Assumptions:

* Initiative row exists in Central Backlog with `initiative_key`.
* PM wants more sophisticated value modeling than a plain RICE/WSJF.

I’ll walk each scenario with explicit:

* Which tab
* Which columns
* What backend + LLM do

---

### Scenario A – **Manual math model** (PM fully designs formula & structure)

**Use case:** advanced PM / quant; they already know precisely how they want to express value.

---

#### Step A1 – Turn on math model (Central Backlog)

**Tab/Sheet:** Central Backlog
**PM actions:**

* Find the initiative row.
* Set:

  * `active_scoring_framework = "MATH_MODEL"`
  * `use_math_model = TRUE`

**Effect:**

* Backend marks this initiative as “math-modelled”.
* A scheduled/triggered job ensures a corresponding row exists in the **ProductOps → MathModels tab** for this initiative.

---

#### Step A2 – Define the formula (MathModels tab)

**Tab:** ProductOps → MathModels
**What PM sees initially:**

* An auto-created row something like:

  * `initiative_key = INIT-123`
  * `framework = MATH_MODEL`
  * `model_name` blank or default (`INIT-123_MATH_MODEL_V1`)
  * `model_description_free_text` empty
  * `llm_suggested_formula_text` empty
  * `formula_text_final` empty
  * `formula_text_approved = FALSE`

**PM actions (manual path):**

1. Fill:

   * `model_name` – e.g. `CheckoutConvValue2025`
   * `model_description_free_text` – e.g.
     “Value = uplift_in_conv × baseline_conv × monthly_sessions × aov × margin × horizon_months − infra_cost”

   (Free-text, can be informal or almost formulaic.)

2. Fill the **actual formula** in the final field:

   * `formula_text_final` – e.g.
     `value = uplift_conv * baseline_conv * monthly_sessions * aov * margin * horizon_months - infra_cost`

3. Optionally:

   * `assumptions_text` – e.g.
     “Assumes uplift is sustained for 12 months, margin constant, traffic stable.”

4. When happy, tick:

   * `formula_text_approved = TRUE`.

**Effect:**

* Backend treats `formula_text_final` as the canonical model for this initiative (stored in `InitiativeMathModel.formula_text`).

---

#### Step A3 – Params get auto-seeded via **parse + LLM metadata** (Params tab)

**Tab:** ProductOps → Params
**Backend actions (no PM yet):**

1. **Deterministic identifier extraction**

   * Backend parses `formula_text_final` to extract raw variable identifiers on the right-hand side:

     ```text
     uplift_conv, baseline_conv, monthly_sessions, aov, margin, horizon_months, infra_cost
     ```

   * This step is purely mechanical (no semantics), just: “Which symbols occur in this formula?”

2. **LLM enriches parameter metadata**

   Backend calls an LLM helper (e.g. `suggest_param_metadata`) with:

   * Initiative context (title, problem, impact fields)
   * The formula text
   * The list of raw identifiers

   LLM responds with one JSON object per param, including suggestions for:

   * `param_display`
   * `unit`
   * `description`
   * `min` / `max` (if applicable)
   * `source` (likely owner: Analytics, Finance, etc.)

3. **Rows created in Params tab**

   For each param, backend creates a row in Params:

   | initiative_key | framework  | param_name       | param_display             | value | unit   | min  | max  | source    | approved | is_auto_seeded |
   | -------------- | ---------- | ---------------- | ------------------------- | ----- | ------ | ---- | ---- | --------- | -------- | -------------- |
   | INIT-123       | MATH_MODEL | uplift_conv      | Uplift in conversion rate |       | %      | 0.00 | 0.10 | Analytics | FALSE    | TRUE           |
   | INIT-123       | MATH_MODEL | baseline_conv    | Baseline conversion rate  |       | %      | 0.00 | 0.20 | Analytics | FALSE    | TRUE           |
   | INIT-123       | MATH_MODEL | monthly_sessions | Monthly sessions          |       | visits |      |      | Analytics | FALSE    | TRUE           |
   | INIT-123       | MATH_MODEL | aov              | Avg order value           |       | £      |      |      | Finance   | FALSE    | TRUE           |
   | INIT-123       | MATH_MODEL | margin           | Profit margin             |       | %      | 0.00 | 1.00 | Finance   | FALSE    | TRUE           |
   | INIT-123       | MATH_MODEL | horizon_months   | Horizon in months         |       | months | 1    | 36   | PM        | FALSE    | TRUE           |
   | INIT-123       | MATH_MODEL | infra_cost       | Infra cost (one-off)      |       | £      | 0    |      | Eng/Infra | FALSE    | TRUE           |

   > In v1, we can start with conservative defaults (e.g. min/max optional) and update as we learn.

---

#### Step A4 – PM & others fill numbers and approve (Params tab)

**Tab:** ProductOps → Params
**PM / Analytics / Finance actions:**

* Filter rows: `initiative_key = INIT-123` AND `framework = MATH_MODEL`.
* For each parameter:

  * Fill `value`.
  * Adjust `unit` / `min` / `max` if the LLM default is off.
  * Adjust `param_display` or `description` if needed.
  * Set `source` to the real owner if different.
  * Tick `approved = TRUE` when that parameter is ready to be used.

**Effect:**

* We now have a **complete, approved set of parameters** for the initiative’s math model.

---

#### Step A5 – System scores it (Central Backlog & Scoring tab reflect results)

Backend:

* MathModelFramework pulls:

  * The approved params for `(initiative_key, MATH_MODEL)` from DB/Params.
  * The formula from `InitiativeMathModel`.

* Evaluates the formula safely → `value_score`.

* Uses `effort_engineering_days` or other effort fields to compute `effort_score` and then `overall_score` (e.g. value/effort).

* Writes per-framework scores into DB, then:

  * Flow 2 activates them as `value_score`, `overall_score` (based on `active_scoring_framework`).
  * Flow 3 / Backlog sync propagate them to:

    * Central Backlog sheet
    * ProductOps Scoring tab (per-framework breakdown)

**PM sees** in Central Backlog (and Scoring tab):

* For that initiative:

  * `value_score` now reflects the math model (often in £ or a normalized index).
  * `overall_score` now reflects the chosen math logic (e.g. ROI).
  * They still retain the ability to override scores if necessary.

---

### Scenario B – **LLM-Assisted from description** (AI proposes a model)

**Use case:** PM has strong intuition but not a precise formula; wants AI to come up with a good starting model.

---

#### Step B1 – Enable math model (Central Backlog)

Same as A1:

* `active_scoring_framework = "MATH_MODEL"`
* `use_math_model = TRUE`

---

#### Step B2 – Describe and request help (MathModels tab)

**Tab:** ProductOps → MathModels
**PM actions:**

On row for `INIT-456`:

* `model_name` = `TicketReductionValue2025`

* `model_description_free_text` =
  “Value should depend on reduction in support tickets, cost per ticket, and horizon. If we reduce tickets by X per month, and each ticket costs Y, we save X*Y per month over Z months. Maybe also factor in CSAT uplift.”

* Optionally:
  `model_prompt_to_llm` = “Propose a formula that gives expected annual value in £, with parameters we can estimate.”

They:

* Do **not** fill `formula_text_final` yet.
* Do **not** tick `formula_text_approved`.

---

#### Step B3 – LLM proposes a formula & assumptions (MathModels tab)

**Backend/LLM action:**

* Finds MathModels rows where:

  * `framework = MATH_MODEL`
  * `formula_text_approved = FALSE`
  * `llm_suggested_formula_text` is empty or stale.

* Calls `suggest_math_model(...)` with:

  * Initiative fields (title, problem, impact, metrics).
  * `model_description_free_text`.
  * `model_prompt_to_llm` (if any).

* LLM returns:

  * A candidate formula, e.g.:

    `value = ticket_reduction_per_month * cost_per_ticket * horizon_months`

  * Assumptions, e.g.:

    “Assumes each avoided ticket saves full cost_per_ticket; no CSAT or churn impact included.”

  * Notes/interpretation.

* Backend writes to MathModels:

  * `llm_suggested_formula_text`
  * `assumptions_text`
  * `llm_notes`

**PM now sees** a suggested model in the MathModels tab.

---

#### Step B4 – PM reviews, edits, and approves (MathModels tab)

**Tab:** ProductOps → MathModels
**PM actions:**

* Review `llm_suggested_formula_text`, `assumptions_text`, `llm_notes`.

If they like it as-is (or mostly):

* Copy/confirm into `formula_text_final` (we might auto-copy once as a UX convenience).
* Optionally tweak the formula (rename variables, add terms, refine).
* Optionally adjust `assumptions_text` (add org-specific assumptions).
* Tick `formula_text_approved = TRUE`.

If they don’t like it:

* Edit `model_description_free_text` or `model_prompt_to_llm` to steer the LLM.
* Leave `formula_text_approved = FALSE`.
* Let the LLM job re-run (or trigger it) to get a revised formula.

> **Key principle:**
> The formula that actually gets used is always `formula_text_final`, never the raw LLM suggestion. PM is always the gatekeeper.

---

#### Step B5 – Params auto-seeded via parse + LLM metadata (Params tab)

Once `formula_text_approved = TRUE`:

* Backend performs **the same two-stage process as in Scenario A**:

  1. Deterministically extract raw identifiers from `formula_text_final`.

  2. Call LLM to suggest metadata:

     * `param_display`, `unit`, `description`, `min`, `max`, `source`.

  3. Write rows into Params tab with `is_auto_seeded = TRUE`, `approved = FALSE`.

* Then PM / Analytics / Finance:

  * Filter by `initiative_key = INIT-456`, `framework = MATH_MODEL`.
  * Fill `value`, adjust metadata if needed, tick `approved`.

From then on, scoring is identical to Scenario A.

---

### Scenario C – **Hybrid** (LLM suggests, PM heavily modifies)

This is explicitly the “LLM as co-pilot, PM as editor” flow.

Steps:

1. **PM describes the model** in `model_description_free_text` (and optionally `model_prompt_to_llm`).

2. LLM fills `llm_suggested_formula_text`, `assumptions_text`, `llm_notes`.

3. PM **uses that as a starting point**:

   * Writes a refined or entirely changed version into `formula_text_final`.
   * Might rename variables, add terms, or remove pieces.
   * Adjusts assumptions accordingly.

4. When the formula is truly what they want, they tick `formula_text_approved = TRUE`.

5. From then on, same as A/B:

   * Backend extracts variable names from `formula_text_final`.
   * LLM suggests param metadata.
   * Params tab gets filled with rows.
   * PM/teams fill `value` & approve.
   * System evaluates and writes scores.

> **UX-wise:**
> “LLM gets me close, I refine the logic and the variable naming, then I lock it. Parameters then flow out automatically for me to fill.”

---

## 4. Multiple math models per initiative / reuse (unchanged logic, just contextualized)

### a) One **active** math model per initiative (per framework) in v1

* For v1, per initiative and per framework (e.g. `MATH_MODEL`), we allow at most **one** row where:

  * `framework = MATH_MODEL`
  * `formula_text_approved = TRUE`
  * (Optionally `scenario_label = 'Base'`)

* We can also support multiple variants (e.g. `Base`, `Optimistic`, `Conservative`) via:

  * `version` and/or
  * `scenario_label`.

* But the one that drives scoring is the designated active/approved row.

> **PM mental model:**
> “For each initiative and each scoring style, I have one official math model. I can have drafts or variants, but there’s a clear one the system uses.”

### b) Reuse across initiatives

1. **Copy–Paste (v1 pragmatic approach)**

   * PM finds an initiative with a math model they like.
   * Copies its row in MathModels tab and adjusts `initiative_key` (and maybe some text).
   * Backend treats that as a separate model instance for the new initiative.
   * Params seeding runs again based on the formula → new rows in Params for that initiative.

2. **Template-based (future)**

   * Some MathModels rows are marked as templates: `is_template = TRUE` or `framework = 'MATH_MODEL_TEMPLATE'`.
   * PM can select a template in a dropdown on MathModels or Central Backlog.
   * Backend clones formula + parameter metadata for the new initiative, then they only change the parameter **values** in Params.

We postpone full template UX to later; copy–paste is good enough for v1.

---

## 5. Quick recap in PM story form (updated with LLM-param role)

> “As a PM, I decide some initiatives need **proper mathematical value models** instead of simple heuristics like RICE.
>
> I go to the Central Backlog and set `active_scoring_framework = MATH_MODEL` and `use_math_model = TRUE`.
>
> Then I open the **ProductOps → MathModels tab** to **define the model logic**. I can:
>
> * Write the formula myself and mark it approved, or
> * Write a natural-language description and let the AI propose a formula, then tweak and approve it.
>
> Once the formula is approved, the system:
>
> * Automatically extracts the parameter names from the formula,
> * Calls the AI to suggest nice labels, units, descriptions, and ranges, and
> * Creates rows for each parameter in the **ProductOps → Params tab**.
>
> In the **Params tab**, I and other stakeholders (Analytics, Finance, Eng) then:
>
> * Fill in the actual numerical values for each parameter,
> * Adjust units/labels/ranges if needed,
> * Mark them as approved.
>
> From that point, the backend evaluates the formula using those parameter values, computes **value_score / overall_score**, and I see the results back in the **Central Backlog** (and the ProductOps Scoring tab), side-by-side with RICE/WSJF if I want to compare frameworks.”

---

If this updated journey matches your mental picture with the new tweaks (LLM doing param semantics, deterministic extraction, unified tabs in ProductOps), then the **next thinking step** is exactly what you said:

> **Next step:**
>
> 1. Freeze the MVP scope for:
>
>    * Columns in **MathModels** tab (mark “future” ones if needed)
>    * Columns in **Params** tab
> 2. Decide per column:
>
>    * PM-editable vs read-only in v1
>    * LLM-writable vs backend-only vs human-only
> 3. Then design the concrete LLM workflows:
>
>    * `suggest_math_model`
>    * `suggest_param_metadata`
>
> And only after that, start implementation.

