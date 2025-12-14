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

#### Deep Dive A1 – Turn on math model (Central Backlog)

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

#### Deep Dive A2 – Define the formula (MathModels tab)

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

#### Deep Dive A3 – Params get auto-seeded via **parse + LLM metadata** (Params tab)

**Tab:** ProductOps → Params
**Backend actions (no PM yet):**

1. **Deterministic identifier extraction**

   * Backend parses `formula_text_final` to extract raw variable identifiers on the right-hand side:

     ```text
     uplift_conv, baseline_conv, monthly_sessions, aov, margin, horizon_months, infra_cost
     ```

   * This Deep Dive is purely mechanical (no semantics), just: “Which symbols occur in this formula?”

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

#### Deep Dive A4 – PM & others fill numbers and approve (Params tab)

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

#### Deep Dive A5 – System scores it (Central Backlog & Scoring tab reflect results)

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

#### Deep Dive B1 – Enable math model (Central Backlog)

Same as A1:

* `active_scoring_framework = "MATH_MODEL"`
* `use_math_model = TRUE`

---

#### Deep Dive B2 – Describe and request help (MathModels tab)

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

#### Deep Dive B3 – LLM proposes a formula & assumptions (MathModels tab)

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

#### Deep Dive B4 – PM reviews, edits, and approves (MathModels tab)

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

#### Deep Dive B5 – Params auto-seeded via parse + LLM metadata (Params tab)

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

---

Now, Let’s lock in the **MVP column spec** for the two key tabs:

* **ProductOps → MathModels**
* **ProductOps → Params**

We’ll be explicit about:

* Column name
* Purpose
* Type
* **Who can edit** (PM vs LLM vs backend)
* Whether it’s **MVP** or **Future**

No code yet, just the contract.

---

## 1️⃣ MathModels tab – MVP column spec

**Role:**
Per-initiative per-framework **model definition** and LLM collaboration.
For v1, we focus pretty much on `framework = MATH_MODEL`, but design it generic enough to later host other formula-based frameworks (RICE/WSJF templates, custom frameworks).

### MathModels – column list (MVP vs Future)

I’ll mark:

* **MVP** = must have for v1
* *(future)* = we design for it conceptually but can omit from first implementation

---

### 1. `initiative_key` – **MVP**

* **Type:** string
* **Example:** `INIT-000123`
* **Who writes:**

  * Backend populates (from DB / Central Backlog)
* **Who edits in Sheet:**

  * PM: **read-only** (should not be changed)
* **Purpose:**

  * Primary join key to `Initiative` and Params rows.
* **Notes:**

  * This is the first column in the tab.

---

### 2. `framework` – **MVP**

* **Type:** string enum
* **Example:** `MATH_MODEL` (later `RICE`, `WSJF`, `CUSTOM_X`)
* **Who writes:**

  * Backend seeds (based on `active_scoring_framework` or template)
  * PM could change in some advanced flows, but in v1: treat as **backend-owned**.
* **Who edits in Sheet:**

  * PM: **read-only** in v1
* **Purpose:**

  * Tells backend which scoring framework this row describes.
* **Notes:**

  * For v1, we primarily use `MATH_MODEL`.
  * In future, we can have “template rows” like `framework = RICE_TEMPLATE`.

---

### 3. `model_name` – **MVP**

* **Type:** short string
* **Example:** `CheckoutConvValue2025`
* **Who writes:**

  * PM: **editable**
  * Backend: may propose a default name for new rows (like `INIT-123_MATH_MODEL_V1`), but PM can override.
* **Who edits in Sheet:**

  * PM: free to edit
* **Purpose:**

  * Human-friendly label for the model; helps scanning and referencing.

---

### 4. `model_description_free_text` – **MVP**

* **Type:** long text
* **Example:**
  “Value should depend on uplift in conversion, baseline conversion, traffic, AOV, margin, and horizon. Value = X × Y × Z…”
* **Who writes:**

  * PM: **editable**
  * LLM: might read this, but does NOT override.
* **Purpose:**

  * PM’s natural-language explanation of what the model should capture.
* **Notes:**

  * Used heavily as input to `suggest_math_model`.

---

### 5. `model_prompt_to_llm` – *optional MVP (nice but not strictly necessary)*

* **Type:** long text
* **Example:**
  “Propose a formula that outputs annual value in £, using uplift %, traffic, AOV, and margin.”
* **Who writes:**

  * PM: **editable**
  * LLM: only reads.
* **Purpose:**

  * Optional extra steering for LLM beyond `model_description_free_text`.
* **Decision:**

  * I’d include it in MVP, but PM can leave it blank most of the time.

---

### 6. `llm_suggested_formula_text` – **MVP**

* **Type:** long text (machine-generated)
* **Example:**
  `value = uplift_conv * baseline_conv * monthly_sessions * aov * margin * horizon_months - infra_cost`
* **Who writes:**

  * LLM/Backend: **writes**
  * PM: **read-only** (they *copy/tweak* into `formula_text_final`, not here)
* **Purpose:**

  * Proposed model formula from the LLM.
* **Notes:**

  * We treat this as a draft; actual used formula is `formula_text_final`.

---

### 7. `assumptions_text` – **MVP**

* **Type:** long text
* **Example:**
  “Assumes uplift is sustained for 12 months, margin constant, infra cost is one-off, traffic stable.”
* **Who writes:**

  * LLM/Backend: seeds initial content.
  * PM: **editable** to adjust/add assumptions.
* **Purpose:**

  * Explicitly documents assumptions behind the model.
* **Notes:**

  * LLM writes first, PM refines.

---

### 8. `llm_notes` – **MVP**

* **Type:** long text
* **Example:**
  “Main driver of value is conversion uplift on high-traffic mobile checkout; infra cost relatively small.”
* **Who writes:**

  * LLM/Backend: seeds initial explanation.
  * PM: optionally edits/extends.
* **Purpose:**

  * Commentary / reasoning from LLM about the model.
* **Notes:**

  * Useful for PM/Stakeholders; not used in computation.

---

### 9. `formula_text_final` – **MVP**

* **Type:** long text (machine-readable, in our chosen safe expression syntax)
* **Example:**
  `value = uplift_conv * baseline_conv * monthly_sessions * aov * margin * horizon_months - infra_cost`
* **Who writes:**

  * PM: **editable** (could start from scratch or paste from `llm_suggested_formula_text`)
  * Backend: may auto-copy the LLM suggestion as a starting value once, but PM owns the final content.
* **Purpose:**

  * The **approved**, canonical formula used for scoring & param extraction.
* **Notes:**

  * Backend never executes `llm_suggested_formula_text` directly; only `formula_text_final`.

---

### 10. `formula_text_approved` – **MVP**

* **Type:** boolean (checkbox)
* **Example:** `TRUE` / `FALSE`
* **Who writes:**

  * PM: **editable** (they decide when it’s ready)
* **Purpose:**

  * Gatekeeper: only when this is `TRUE` do we:

    * Treat `formula_text_final` as canonical,
    * Extract parameters,
    * Use it for scoring.
* **Notes:**

  * Backend respects this flag strictly.

---

### 11. `version` – *future (nice-to-have)*

* **Type:** integer
* **Example:** `1`, `2`
* **Who writes:**

  * Backend: increments when `formula_text_final` changes significantly.
* **PM:** read-only.
* **Purpose:**

  * Track model evolution per initiative.
* **Decision:**

  * We can design for it now, implement later.

---

### 12. `scenario_label` – *future*

* **Type:** string
* **Example:** `Base`, `Optimistic`, `Conservative`
* **Who writes:**

  * PM: **editable**
* **Purpose:**

  * Let PM define multiple scenario variants of the math model.
* **Decision:**

  * Not needed in MVP; we can start with just a “Base” model per initiative.

---

### Summary – MathModels MVP

Minimum columns we should implement **now**:

1. `initiative_key` (RO, backend)
2. `framework` (RO, backend; v1 = `MATH_MODEL`)
3. `model_name` (PM editable)
4. `model_description_free_text` (PM editable)
5. `model_prompt_to_llm` (PM editable, optional)
6. `llm_suggested_formula_text` (LLM writes; PM read-only)
7. `assumptions_text` (LLM seeds; PM editable)
8. `llm_notes` (LLM seeds; PM editable)
9. `formula_text_final` (PM editable; canonical)
10. `formula_text_approved` (PM checkbox)

Everything else (version, scenario_label) can be future.

---

## 2️⃣ Params tab – MVP column spec

**Role:**
Normalized table for **all parameter values** across initiatives and frameworks.
One row per `(initiative_key, framework, param_name)`.

This will ultimately support:

* Math models (`MATH_MODEL`)
* RICE (`RICE`)
* WSJF (`WSJF`)
* Future custom frameworks.

### Params – column list

---

### 1. `initiative_key` – **MVP**

* **Type:** string
* **Example:** `INIT-000123`
* **Who writes:**

  * Backend when seeding params from formula/framework.
* **Who edits:**

  * PM: read-only.
* **Purpose:**

  * Joins this param row to an Initiative (and to the relevant MathModels row).

---

### 2. `framework` – **MVP**

* **Type:** string enum
* **Example:** `MATH_MODEL`, `RICE`, `WSJF`
* **Who writes:**

  * Backend: when seeding parameters from MathModels or from template frameworks.
* **Who edits:**

  * PM: read-only in v1.
* **Purpose:**

  * Tells us which scoring framework this parameter belongs to.

---

### 3. `param_name` – **MVP**

* **Type:** string (identifier)
* **Example:** `uplift_conv`, `baseline_conv`, `monthly_sessions`, `reach`, `impact`
* **Who writes:**

  * Backend: from deterministic formula parsing or framework template.
  * PM: may create **new manual rows** later, but in MVP we can focus on backend-seeded ones.
* **Who edits in v1:**

  * For auto-seeded rows: **read-only** (to avoid breaking references).
  * For manually-added rows (future): PM editable.
* **Purpose:**

  * Internal stable identifier used in formula evaluation and scoring code.

---

### 4. `param_display` – **MVP**

* **Type:** string
* **Example:** `Uplift in Conversion Rate`
* **Who writes:**

  * LLM: suggests initial value, based on param_name + context.
  * PM: **editable** (can refine labels).
* **Purpose:**

  * Friendly label visible in the sheet and future UI; not used in computation.

---

### 5. `description` – **MVP**

* **Type:** long text
* **Example:**
  “Expected absolute uplift in conversion rate (e.g. from 4% to 6% ⇒ 2%).”
* **Who writes:**

  * LLM: seeds initial description.
  * PM / Analytics: **editable**.
* **Purpose:**

  * Explains meaning and interpretation of the parameter to humans.

---

### 6. `value` – **MVP**

* **Type:** number or string (primarily numeric)
* **Example:** `0.04`, `500000`, `45`
* **Who writes:**

  * PM / Analytics / Finance / Eng: **editable**.
  * LLM: may **suggest** values in some flows, but in MVP we can treat this as human-entered.
* **Purpose:**

  * Actual value used by the scoring engine when evaluating the formula/framework.

---

### 7. `unit` – **MVP**

* **Type:** string
* **Example:** `%`, `£`, `sessions`, `days`
* **Who writes:**

  * LLM: suggests initial unit.
  * PM / others: **editable**.
* **Purpose:**

  * Unit for the value, mainly for display and sanity checking.

---

### 8. `min` – *MVP but can be nullable*

* **Type:** number (nullable)
* **Example:** `0.0`
* **Who writes:**

  * LLM: may propose.
  * PM / Analytics: **editable**.
* **Purpose:**

  * Lower bound for parameter when we later do uncertainty/Monte Carlo.
  * In MVP, we can treat it as optional; no scoring logic depends on it yet.

---

### 9. `max` – *MVP but nullable*

* **Type:** number (nullable)
* **Example:** `0.1`
* **Who writes:**

  * LLM: may propose.
  * PM / Analytics: **editable**.
* **Purpose:**

  * Upper bound for parameter when modeling uncertainty.

---

### 10. `source` – **MVP**

* **Type:** string enum
* **Example:** `PM`, `Analytics`, `Finance`, `Eng`, `LLM`
* **Who writes:**

  * LLM: may set a default guess based on parameter type.
  * PM / others: **editable**.
* **Purpose:**

  * Indicates who is considered the owner of the parameter (for accountability).

---

### 11. `approved` – **MVP**

* **Type:** boolean (checkbox)
* **Example:** `TRUE` / `FALSE`
* **Who writes:**

  * PM / appropriate owner: **editable**.
* **Purpose:**

  * Indicates that the parameter is ready to be used in scoring.
  * Backend may choose to use only `approved = TRUE` params (MVP rule).

---

### 12. `is_auto_seeded` – **MVP**

* **Type:** boolean
* **Example:** `TRUE` / `FALSE`
* **Who writes:**

  * Backend: sets `TRUE` when it creates the row from the formula/framework template.
* **PM:** read-only.
* **Purpose:**

  * Distinguish system-created params from manually added ones.

---

### 13. `last_updated_by` – *future*

* **Type:** string
* **Example:** `moeen@company.com`
* **Who writes:**

  * Backend: sets based on identity (if we have auth context).
* **PM:** read-only.
* **Purpose:**

  * Auditing and collaboration clarity.

---

### 14. `last_updated_at` – *future*

* **Type:** datetime
* **Example:** `2025-12-10T14:32:05Z`
* **Who writes:**

  * Backend.
* **PM:** read-only.
* **Purpose:**

  * Auditing / debugging.

---

### 15. `notes` – **MVP**

* **Type:** long text
* **Example:**
  “Using latest Q4 traffic; revisit after marketing campaign.”
* **Who writes:**

  * PM / Analytics / Finance / Eng: **editable**.
* **Purpose:**

  * Free-form comments regarding parameter choice or caveats.

---

### Summary – Params MVP

Minimum columns to implement now:

1. `initiative_key` (RO, backend)
2. `framework` (RO, backend)
3. `param_name` (RO for seeded; possibly editable for manual-extra later)
4. `param_display` (LLM seeds, PM editable)
5. `description` (LLM seeds, PM editable)
6. `value` (human editable; core)
7. `unit` (LLM seeds, editable)
8. `min` (optional, editable)
9. `max` (optional, editable)
10. `source` (LLM seeds, editable)
11. `approved` (checkbox, human)
12. `is_auto_seeded` (RO, backend)
13. `notes` (editable)

`last_updated_by` / `last_updated_at` can be added later if/when we tie in user identity.

---

## 3️⃣ Who can write what (MVP roles summary)

### MathModels tab

* **PM can edit:**

  * `model_name`
  * `model_description_free_text`
  * `model_prompt_to_llm`
  * `assumptions_text` (after LLM seeds)
  * `llm_notes` (after LLM seeds)
  * `formula_text_final`
  * `formula_text_approved`

* **LLM can write/overwrite:**

  * `llm_suggested_formula_text`
  * initial `assumptions_text`
  * initial `llm_notes`

* **Backend-only fields:**

  * `initiative_key`
  * `framework`
  * (future) `version`, `scenario_label` if we store them programmatically.

### Params tab

* **PM / Analytics / Finance / Eng can edit:**

  * `param_display`
  * `description`
  * `value`
  * `unit`
  * `min`, `max`
  * `source`
  * `approved`
  * `notes`

* **LLM can write/seed (initial only):**

  * `param_display`
  * `description`
  * `unit`
  * `min`, `max`
  * `source` (guess)

* **Backend-only fields:**

  * `initiative_key`
  * `framework`
  * `param_name` (for auto-seeded params)
  * `is_auto_seeded`
  * (future) `last_updated_by`, `last_updated_at`.

---

Now, let’s nail these down properly so when we implement, it’s just “follow the spec”.

We’ll define **two workflows**:

1. `suggest_math_model` – works on **MathModels** tab row → proposes formula + assumptions + notes
2. `suggest_param_metadata` – works on **formula_text_final + raw identifiers** → proposes metadata for **Params** rows

For each, we’ll cover:

* When it runs (trigger)
* What data we send to the LLM
* Prompt shape (system + user message, high level)
* Expected JSON output
* How we write back to Sheets
* How PM stays in control (loops, idempotency)

---

## 1️⃣ Workflow: `suggest_math_model`

> Goal: Given an initiative and a PM’s free-text description, propose a **candidate formula**, **assumptions**, and **explanatory notes** for that initiative’s value model.

### 1.1. When does it run?

We run `suggest_math_model` for rows in **ProductOps → MathModels** where:

* `framework = MATH_MODEL`
* `formula_text_approved = FALSE`
* (`llm_suggested_formula_text` is empty **or** PM explicitly wants a refresh – e.g. via a “regenerate” flag or manual deletion)

Rough job logic:

* Cron / CLI job: `math_model_generation_job`
* For each eligible row:

  * Load initiative context from DB (using `initiative_key`)
  * Call `suggest_math_model`
  * Write suggestions into the MathModels tab row

### 1.2. Inputs for the LLM

We want to give the model *rich but structured context*.

**From Initiative (DB):**

* `initiative_key`
* `title`
* `problem_statement`
* `desired_outcome`
* `expected_impact_description`
* `impact_metric`, `impact_unit`, `impact_low`, `impact_expected`, `impact_high`
* `effort_engineering_days`, `effort_tshirt_size`
* `country/market`, `product_area`, `strategic_theme`, etc.
* `llm_summary` (short 2–3 line description)

**From MathModels row:**

* `model_name`
* `model_description_free_text`
* `model_prompt_to_llm` (if present)
* Any existing `llm_suggested_formula_text` / `assumptions_text` we might want to show as “previous draft” (optional, case by case)

### 1.3. Prompt design (high level)

**System message** (conceptual):

> “You are an expert product/finance analyst helping design quantitative value models for product initiatives.
> You must propose a **single, explicit mathematical formula** for the value of an initiative, using named parameters that can be estimated by PMs, Analytics, Finance, and Engineering.
> The output must be valid JSON in a specified schema. Do not invent business context beyond what is given.”

**User message** (content):

* Short section: **initiative summary**

  * title, llm_summary, problem, desired_outcome
* Short section: **existing numeric context**

  * any impact_x, effort, costs
* Short section: **PM request**

  * `model_description_free_text`
  * `model_prompt_to_llm` (if present)
* Instructions:

  * Propose a formula in a simple expression language with:

    * A single left-hand side, usually `value`.
    * A right-hand side made of parameters and arithmetic.
  * Don’t plug in numeric values – keep symbolic parameters.
  * Pick parameter names that are:

    * Lower_snake_case
    * Self-explanatory-ish (e.g. `monthly_sessions`, `baseline_conv`, `uplift_conv`)
  * Explicitly state assumptions.
  * Produce a JSON object that exactly matches our schema.

### 1.4. Expected output shape

We ask for a **single JSON object**, e.g.:

```json
{
  "formula_text": "value = uplift_conv * baseline_conv * monthly_sessions * aov * margin * horizon_months - infra_cost",
  "assumptions": [
    "Uplift in conversion rate is sustained for the full horizon.",
    "Baseline conversion rate stays constant aside from the uplift.",
    "Monthly sessions remain approximately constant over the horizon.",
    "Margin and AOV remain stable.",
    "Infra cost is a one-off upfront expense."
  ],
  "notes": "This model treats value as incremental gross profit from increased conversion minus one-off infra cost. The biggest drivers are uplift_conv, monthly_sessions and aov."
}
```

Key points:

* `formula_text` – this becomes `llm_suggested_formula_text` in MathModels.
* `assumptions` – array of strings, joined into `assumptions_text`.
* `notes` – written into `llm_notes`.

We can later add optional fields (like recommended parameter names with descriptions), but core is these three.

### 1.5. Writing back to MathModels tab

For the matching row:

* Set `llm_suggested_formula_text = formula_text`
* Set `assumptions_text = join(assumptions, "\n")` **only if** cell is empty OR we’re explicitly regenerating
* Set `llm_notes = notes` (same policy)
* **Do not touch**:

  * `formula_text_final`
  * `formula_text_approved`

PM then:

* Reviews these.
* Copies/tweaks the formula into `formula_text_final`.
* Adjusts `assumptions_text` if needed.
* Ticks `formula_text_approved = TRUE` when satisfied.

### 1.6. Idempotency & PM control

* We **never overwrite** `formula_text_final` or `formula_text_approved`.
* We either:

  * Only fill `llm_suggested_formula_text` if blank, OR
  * Respect a “regenerate” signal (e.g. PM clears the cell or sets some `llm_refresh` flag).
* PM always has explicit control over when the formula becomes canonical.

---

## 2️⃣ Workflow: `suggest_param_metadata`

> Goal: Given an approved formula and the list of raw identifiers, propose **human-friendly labels, units, descriptions, ranges, and sources** for each parameter to populate the Params tab.

### 2.1. When does it run?

We run `suggest_param_metadata` for `(initiative_key, framework)` where:

* In MathModels:

  * `formula_text_final` is non-empty
  * `formula_text_approved = TRUE`
* In Params:

  * For each parameter name that has **no existing row** (or is newly introduced):

    * We need to create rows and fill metadata.

Rough flow:

1. Formula is approved.
2. Backend runs a deterministic parse:

   * `raw_identifiers = ["uplift_conv", "baseline_conv", "monthly_sessions", ...]`
3. For any identifiers not already present as rows in Params for `(initiative_key, framework)`:

   * Call `suggest_param_metadata(initiative_context, formula_text_final, raw_identifiers)`
   * Use the response to seed new rows.

### 2.2. Inputs for the LLM

We provide:

**A. Initiative context** (same as before, but shorter if we like):

* `title`, `llm_summary`, `problem_statement`, `desired_outcome`
* `impact_metric`, `impact_unit`, etc. (optional but helpful)

**B. Math model context:**

* `framework` name (`MATH_MODEL` or others later)
* `model_name`
* `formula_text_final` (canonical)
* Maybe `assumptions_text` (if we want the LLM aware of them)

**C. Raw identifiers list:**

```json
["uplift_conv", "baseline_conv", "monthly_sessions", "aov", "margin", "horizon_months", "infra_cost"]
```

We **explicitly instruct**:

* Do not invent extra parameters.
* Do not drop any.
* For each raw name given, return exactly one metadata object.

### 2.3. Prompt design (high level)

**System message:**

> “You are helping define metadata for parameters used in a mathematical model of initiative value.
> For each raw parameter name, you must propose:
>
> * A human-readable display name,
> * A short description,
> * A suggested unit (if applicable),
> * Optional min/max bounds,
> * A likely owner/source (PM, Analytics, Finance, Eng, LLM).
>   Do not invent parameters not in the input list. Return valid JSON.”

**User message:**

* Recap:

  * Initiative summary.
  * Formula text: `value = ...`
  * Assumptions (if we want).
* Provide the array of raw identifiers.
* Ask for output in a precise JSON shape.

### 2.4. Expected output shape

Something like:

```json
{
  "parameters": [
    {
      "name": "uplift_conv",
      "display": "Uplift in Conversion Rate",
      "description": "Expected absolute uplift in conversion rate (e.g. from 4% to 6% gives 0.02).",
      "unit": "fraction",
      "min": 0.0,
      "max": 0.2,
      "source": "Analytics"
    },
    {
      "name": "baseline_conv",
      "display": "Baseline Conversion Rate",
      "description": "Current conversion rate before the change.",
      "unit": "fraction",
      "min": 0.0,
      "max": 0.5,
      "source": "Analytics"
    },
    {
      "name": "monthly_sessions",
      "display": "Monthly Sessions",
      "description": "Average number of relevant user sessions per month.",
      "unit": "sessions",
      "min": null,
      "max": null,
      "source": "Analytics"
    },
    {
      "name": "aov",
      "display": "Average Order Value",
      "description": "Average transaction value for relevant orders.",
      "unit": "GBP",
      "min": null,
      "max": null,
      "source": "Finance"
    },
    {
      "name": "margin",
      "display": "Profit Margin",
      "description": "Average profit margin as a fraction of revenue.",
      "unit": "fraction",
      "min": 0.0,
      "max": 1.0,
      "source": "Finance"
    },
    {
      "name": "horizon_months",
      "display": "Time Horizon (Months)",
      "description": "Number of months over which the value is calculated.",
      "unit": "months",
      "min": 1.0,
      "max": 36.0,
      "source": "PM"
    },
    {
      "name": "infra_cost",
      "display": "Infra Cost (One-off)",
      "description": "One-time infrastructure or platform costs required to deliver the initiative.",
      "unit": "GBP",
      "min": 0.0,
      "max": null,
      "source": "Eng"
    }
  ]
}
```

Note:

* We treat `unit` as free text, but we can guide the model:

  * For numeric fractions, we might use `"percentage"` or `"fraction"`.
  * Currency as `"GBP"` or generic `"currency"` depending on our future plans.

### 2.5. Writing back to Params tab

For each object in `parameters`:

* Check if row already exists in Params for `(initiative_key, framework, name)`:

  * If not, create new row.
  * If yes (rare in MVP), we might skip or only fill missing metadata.

New row fields:

* `initiative_key` = from context
* `framework` = from MathModels (`MATH_MODEL`)
* `param_name` = `name` (raw identifier)
* `param_display` = `display`
* `description` = `description`
* `unit` = `unit` (can normalize later)
* `min` = `min` (if present)
* `max` = `max` (if present)
* `source` = `source`
* `approved` = `FALSE` (let humans approve)
* `is_auto_seeded` = `TRUE`
* `value` = empty (humans fill)
* `notes` = empty (humans fill)

**PM & others then:**

* Go to Params tab.
* Filter by `initiative_key` + `framework`.
* Fill `value`, tweak metadata if needed, then tick `approved`.

### 2.6. Idempotency & updates

* If LLM is run multiple times for the same formula:

  * We can adopt a simple rule:

    * Only create **new** params when new identifiers appear (e.g. formula changed).
    * Don’t overwrite `param_display` / `description` / `unit` for existing rows unless we have a “regenerate metadata” flag.
  * Human edits always win.

* If PM changes `formula_text_final` significantly:

  * Backend detects new identifiers.
  * Calls `suggest_param_metadata` only for *new* ones.
  * Leaves existing param rows as-is, unless PM manually deletes or marks them for regeneration.

---

## 3️⃣ How the two workflows fit together in the PM journey

Putting it together:

1. PM turns on `MATH_MODEL` in Central Backlog.
2. PM goes to **MathModels**:

   * Writes `model_description_free_text` (and optional `model_prompt_to_llm`).
3. **`suggest_math_model`** runs:

   * Adds `llm_suggested_formula_text`, `assumptions_text`, `llm_notes`.
4. PM reviews and writes/edits `formula_text_final`, then ticks `formula_text_approved`.
5. Backend:

   * Parses identifiers from `formula_text_final`.
6. **`suggest_param_metadata`** runs:

   * For each identifier, proposes label, description, unit, min/max, source.
   * Seeds rows in **Params**.
7. PM/Analytics/Finance go to **Params**:

   * Fill `value`, adjust metadata, tick `approved`.
8. Scoring job:

   * Evaluates the formula with approved params → `value_score`, `overall_score`.
   * Propagates to Central Backlog and Scoring tab.

---

The next Deep Dive after this design layer is to:

* Decide **how strict** we want to be in v1 (e.g. must all params be `approved = TRUE` before scoring, or do we allow partial?).
* Then start translating this into concrete code structure:

  * LLM client methods
  * Pydantic schemas for the JSON outputs
  * Jobs that walk MathModels & Params tabs and call these functions.

But at the workflow/UX + LLM-behavior level: this is now pretty concrete.

---


Now, let’s move from “thinking” to “how we’ll actually wire this in” – but still at the **planning level**, no code yet.

Phase 4 – Deep Dive 1 is basically:

> **Add MathModels + Params plumbing to the existing ProductOps + DB architecture, without LLM or scoring logic yet.**

We’ll lay this out as a **sequence of concrete sub-steps**, with:

* Which modules/files we’ll touch
* What each step’s goal is
* How it fits into our existing structure (Flows 1–3, ProductOps config, etc.)

---

## Phase 4 – Deep Dive 1: Implementation plan (high-level sequence)

### Deep Dive 1.1 – Extend ProductOps config to add **MathModels** and **Params** tabs

**Goal:** teach the backend that the ProductOps workbook now has **three** tabs it cares about:

* `Scoring_Inputs` (already exists)
* `MathModels`
* `Params`

**Files to touch:**

* `product_ops_config.json`

  * Add something like:

    ```json
    {
      "spreadsheet_id": "PRODUCT_OPS_SHEET_ID",
      "scoring_inputs_tab": "Scoring_Inputs",
      "mathmodels_tab": "MathModels",
      "params_tab": "Params",
      "config_tab": "Config"
    }
    ```
* `app/config.py` – `ProductOpsConfig` model and `Settings`

  * Extend `ProductOpsConfig` to include `mathmodels_tab` and `params_tab`.
  * Ensure the existing model validator loads these from JSON.

**Outcome:**

* Everywhere else in the code we can do:

  * `settings.PRODUCT_OPS.mathmodels_tab`
  * `settings.PRODUCT_OPS.params_tab`
* No behavior change yet, just new config fields.

---

### Deep Dive 1.2 – Add DB models: **InitiativeMathModel** & generic Parameter structure

**Goal:** create persistent homes in the DB for:

* The approved formula & assumptions per initiative (`InitiativeMathModel`).
* Parameter values/metadata per initiative–framework–parameter (either a dedicated table or embedded in existing scoring models).

We already conceptually reserved `InitiativeMathModel` in the docs.

**Files to touch:**

* `app/db/models/scoring.py`

  * Define `InitiativeMathModel`:

    * `id`
    * `initiative_id` (FK)
    * `framework` (e.g. `"MATH_MODEL"`)
    * `model_name`
    * `formula_text`
    * `assumptions_text`
    * `parameters_json` (for now we can mirror Params tab here)
    * `llm_notes`
    * `suggested_by_llm` (bool)
    * `approved_by_user` (bool)
    * timestamps

* Option A (recommended): a generic param table, e.g. `InitiativeParam`:

  * `id`
  * `initiative_id`
  * `framework`
  * `param_name`
  * `param_display`
  * `description`
  * `value`
  * `unit`
  * `min`
  * `max`
  * `source`
  * `approved`
  * `is_auto_seeded`
  * `notes`

* Option B (simpler MVP): keep Params tab as sheet-only, and store a consolidated `parameters_json` in `InitiativeMathModel` after sync. 

We will with option A here.

* Alembic migration:

  * Create `initiative_math_models` table (and `initiative_params` if we go with Option A).

**Outcome:**

* We have DB entities ready for:

  * Math model metadata.
  * Parameter data, if we choose Option A.

---

### Deep Dive 1.3 – Add Pydantic schemas for MathModels & Params

**Goal:** define typed schemas so we can cleanly move data between DB, services, and Sheets.

**Files to touch:**

* `app/schemas/scoring.py` (or a new module if we prefer to keep it separate):

  * `MathModelSchema` (for InitiativeMathModel)

    * mirrors DB fields we care about in flows (formula_text, assumptions, etc.)
  * `ParamSchema` (assuming we'll go with a dedicated param table):

    * mirrors InitiativeParam fields.

These will be used by:

* Readers/writers (to/from sheets).
* Services that transform between ORM objects and sheet rows.

**Outcome:**

* Strongly-typed internal representation of:

  * A math model row.
  * A parameter row.

---

### Deep Dive 1.4 – Implement **MathModelsReader** & **MathModelsWriter** (Sheets layer)

**Goal:** create the plumbing that reads/writes the MathModels tab, similar to how `ScoringInputsReader` and `productops_writer` work today.

**Files to touch:**

* `app/sheets/mathmodels_reader.py` (new):

  * Use `SheetsClient` to read `MathModels!A1:...`.

  * Interpret the first row as headers (as we do elsewhere).

  * For each data row:

    ```python
    class MathModelRow(BaseModel):
        initiative_key: str
        framework: str
        model_name: Optional[str]
        model_description_free_text: Optional[str]
        model_prompt_to_llm: Optional[str]
        llm_suggested_formula_text: Optional[str]
        assumptions_text: Optional[str]
        llm_notes: Optional[str]
        formula_text_final: Optional[str]
        formula_text_approved: bool
        row_number: int  # store for writing back
    ```

  * Return `List[MathModelRow]`.

* `app/sheets/mathmodels_writer.py` (new):

  * Takes `List[MathModelRow]` and writes selected columns back to the sheet (e.g. filling `llm_suggested_formula_text`, `assumptions_text`, `llm_notes` later).
  * For Deep Dive 1, we mostly need **round-trip sync** (Sheet → DB & DB → Sheet) without LLM.

**Outcome:**

* We can:

  * Preview all MathModels rows from the sheet.
  * Later update them (e.g., backfilling `framework` or `initiative_key` if needed).

---

### Deep Dive 1.5 – Implement **ParamsReader** & **ParamsWriter** (Sheets layer)

**Goal:** same as above, but for the Params tab – one row per `(initiative_key, framework, param_name)`.

**Files to touch:**

* `app/sheets/params_reader.py` (new):

  * Read `Params` tab.
  * Produce `ParamRow` objects:

    ```python
    class ParamRow(BaseModel):
        initiative_key: str
        framework: str
        param_name: str
        param_display: Optional[str]
        description: Optional[str]
        value: Optional[float]
        unit: Optional[str]
        min: Optional[float]
        max: Optional[float]
        source: Optional[str]
        approved: bool
        is_auto_seeded: bool
        notes: Optional[str]
        row_number: int
    ```

* `app/sheets/params_writer.py` (new):

  * Given a list of `ParamRow`s, write them back.
  * Deep Dive 1 use-case: probably mostly for **preview** and maybe small controlled updates (e.g. backfilling `is_auto_seeded` flags).

**Outcome:**

* Plumbing in place for the Params tab; we can inspect rows, and later the LLM / seeding logic will use this to write new rows.

---

### Deep Dive 1.6 – Implement **MathModelSyncService** (DB ↔ MathModels tab)

**Goal:** define a service that manages **synchronization** between the MathModels tab and the DB `InitiativeMathModel` table.

**Files to touch:**

* `app/services/math_model_service.py` (new):

  Core responsibilities:

  1. **Sheet → DB (strong-ish sync):**

     * For each `MathModelRow` from MathModelsReader:

       * Resolve `initiative` via `initiative_key`.
       * Find or create `InitiativeMathModel` for `(initiative_id, framework)`.
       * Update DB fields from sheet fields:

         * `model_name`
         * `formula_text_final`
         * `assumptions_text`
         * `llm_notes`
         * `approved_by_user` from `formula_text_approved`
         * (We **do not** populate `llm_suggested_formula_text` into DB; it stays sheet-only or goes as a “scratchpad” field if needed.)

  2. **DB → Sheet (write-back):**

     * For cases where DB is the source of some truth (e.g. `framework` or `initiative_key`), we might write them back to the sheet (less critical in v1).
     * In Deep Dive 1, the main direction is **Sheet → DB**, because PMs own the definitions.

* This service looks very much like `IntakeService` and `BacklogService`, but focused on math model metadata

**Outcome:**

* A job can now:

  * Read MathModels tab.
  * Call `MathModelSyncService.sync_all_from_sheet(...)`.
  * Persist formulas and approvals in DB.

---

### Deep Dive 1.7 – Implement **ParamsSyncService** (DB ↔ Params tab)

**Goal:** manage synchronization between Params tab and DB representation of parameters (or `parameters_json` if we go with Option B).

**Files to touch:**

* `app/services/params_service.py` (new):

  Responsibilities:

  1. **Sheet → DB:**

     * For each `ParamRow`:

       * Resolve `initiative` via `initiative_key`.
       * For Option A:

         * Upsert `InitiativeParam` for `(initiative_id, framework, param_name)`.
         * Store `value`, `unit`, `approved`, `notes`, etc.
       * For Option B:

         * Build `parameters_json` in `InitiativeMathModel` from all rows.

  2. **DB → Sheet:**

     * Optional in Deep Dive 1.
     * Later needed when we auto-seed parameters (we’ll be writing new rows to sheet).

**Outcome:**

* Parameters from Params tab are persisted in DB, which is crucial for:

  * Scoring.
  * LLM introspection (if needed).
  * Optimization in later phases.

---

### Deep Dive 1.8 – Add a **Flow 4 (MathModel plumbing) CLI** for preview & sync

**Goal:** mirror Flow 3 style CLIs with a CLI for Phase 4 Deep Dive 1:

* `--preview-mathmodels`
* `--sync-mathmodels`
* `--preview-params`
* `--sync-params`

**Files to touch:**

* `test_scripts/flow4_mathmodels_cli.py` (or similar):

  * `--preview-mathmodels`:

    * Just read MathModels tab, parse rows, log a summary.
  * `--sync-mathmodels`:

    * Run `MathModelSyncService` (Sheet → DB) and commit.
  * `--preview-params`:

    * Read Params tab, parse rows, log some.
  * `--sync-params`:

    * Run `ParamsSyncService` (Sheet → DB).

**Outcome:**

* we can locally verify the wiring:

  * Config works.
  * Sheets reading/writing works.
  * DB models and services are behaving as expected.
* Still **no LLM** and **no scoring** yet — pure plumbing.

---

### Deep Dive 1.9 – Add a **formula parsing utility** (no LLM yet)

**Goal:** prepare for later steps, but already be able to:

* Extract identifiers from `formula_text_final`.
* Keep it simple and safe (just enough for LLM later).

**Files to touch:**

* `app/utils/formula_parser.py` (new):

  * Function like:

    ```python
    def extract_identifiers(formula_text: str) -> list[str]:
        ...
    ```

  * For Deep Dive 1, we can stub or implement a simple version using regex / AST.

**Outcome:**

* When we get to `suggest_param_metadata`, we already have the deterministic extraction done.

---

## 3️⃣ After Deep Dive 1 – What’s next in Phase 4

Once Deep Dive 1 is done, we’ll have:

* Config & JSON aware of MathModels + Params tabs.
* DB models for InitiativeMathModel (+ optional InitiativeParam).
* Readers/writers for both tabs.
* Services to sync them into DB.
* CLI to preview & sync.
* A formula parsing stub.

The **next steps in Phase 4** will then be:

* **Deep Dive 2:** Wire in `suggest_math_model` (LLM) and update `math_model_generation_job`.
* **Deep Dive 3:** Wire in `suggest_param_metadata` and auto-seeding of Params rows.
* **Deep Dive 4:** Extend `ScoringService` with `MathModelFramework` to compute scores from DB-stored models & params and write back to sheets.
* **Deep Dive 5:** Integrate with Flow 2 & Flow 3 so the math model scores participate fully in the flows.

---

Now, we’ll outline **Deep Dive 2** only.

---

# Phase 4 – Deep Dive 2: Wire in `suggest_math_model` (LLM) for MathModels

**Goal:**
Enable the system to take a MathModels row + initiative context and **auto-populate**:

* `llm_suggested_formula_text`
* `assumptions_text`
* `llm_notes`

…without yet touching params or scoring.

Think of Deep Dive 2 as: **“LLM as co-author for formulas, PM still final gatekeeper.”**

---

## 2.1 High-level behavior

After Deep Dive 2 is implemented, we'll be able to:

1. PM sets `MATH_MODEL` as active + `use_math_model = TRUE` in Central Backlog.

2. A row appears in MathModels tab (from Deep Dive 1 plumbing).

3. PM writes:

   * `model_name`
   * `model_description_free_text`
   * optionally `model_prompt_to_llm`.

4. we run a CLI like:

   ```bash
   uv run python -m test_scripts.flow4_mathmodels_cli --suggest-mathmodel --log-level INFO
   ```

5. Backend:

   * Reads MathModels rows,
   * For those needing suggestions, calls LLM,
   * Fills `llm_suggested_formula_text`, `assumptions_text`, `llm_notes`.

6. PM reviews, edits `formula_text_final`, and ticks `formula_text_approved` (still manual).

No params, no scoring yet – just LLM suggestions.

---

## 2.2 Modules we’ll touch in Deep Dive 2

Building on Deep Dive 1:

1. **LLM client / integration**

   * `app/llm/client.py`
   * `app/llm/scoring_assistant.py`

2. **MathModel generation job**

   * `app/jobs/math_model_generation_job.py`

3. **MathModels writer**

   * `app/sheets/mathmodels_writer.py` (we’ll extend it to update suggestion columns)

4. **Flow 4 CLI**

   * `test_scripts/flow4_mathmodels_cli.py` – add flags to trigger the LLM suggestion job.

No changes yet to Params, scoring, or flows 2–3.

---

## 2.3 LLM client & helper: `suggest_math_model`

### 2.3.1 `app/llm/client.py`

**Goal:**
Provide a simple wrapper around OpenAI (or whatever we use) so all LLM calls go through a single interface.

* A method like:

  ```python
  class LLMClient:
      def suggest_math_model(self, payload: MathModelPromptInput) -> MathModelSuggestion:
          ...
  ```

* `MathModelPromptInput` – Pydantic model capturing:

  * initiative summary fields
  * `model_description_free_text`
  * `model_prompt_to_llm`

* `MathModelSuggestion` – Pydantic model capturing:

  * `formula_text: str`
  * `assumptions: List[str]`
  * `notes: str`

We already designed this JSON shape in concept; Deep Dive 2 is wiring it concretely.

### 2.3.2 `app/llm/scoring_assistant.py`

**Goal:**
Hide prompt construction away from jobs/services.

* Add a function:

  ```python
  def suggest_math_model_for_initiative(
      initiative: Initiative,
      math_model_row: MathModelRow,
      llm_client: LLMClient,
  ) -> MathModelSuggestion:
      ...
  ```

Inside it:

* Build the full prompt:

  * System + user messages, including:

    * Initiative context
    * `model_description_free_text`
    * `model_prompt_to_llm`

* Call `llm_client.suggest_math_model(...)`.

* Return a `MathModelSuggestion`.

This keeps business logic (jobs/services) clean.

---

## 2.4 Math model generation job

### 2.4.1 `app/jobs/math_model_generation_job.py`

**Goal:**
Scan MathModels tab → call LLM for relevant rows → write suggestions back.

High-level structure:

```python
def run_math_model_generation_job(db: Session, sheets_client: SheetsClient, llm_client: LLMClient):
    # 1. Read MathModels tab
    reader = MathModelsReader(sheets_client)
    rows = reader.get_rows(
        spreadsheet_id=settings.PRODUCT_OPS.spreadsheet_id,
        tab_name=settings.PRODUCT_OPS.mathmodels_tab,
    )

    # 2. For each row, decide if we need LLM suggestion
    updatable_rows = []
    for row in rows:
        if should_suggest_math_model(row):
            initiative = find_initiative_by_key(db, row.initiative_key)
            suggestion = suggest_math_model_for_initiative(initiative, row, llm_client)
            # 3. Update in-memory MathModelRow with suggestion fields
            row.llm_suggested_formula_text = suggestion.formula_text
            row.assumptions_text = join(suggestion.assumptions, "\n")
            row.llm_notes = suggestion.notes
            updatable_rows.append(row)

    # 4. Write updated rows back to MathModels tab
    writer = MathModelsWriter(sheets_client)
    writer.write_suggestions(
        spreadsheet_id=settings.PRODUCT_OPS.spreadsheet_id,
        tab_name=settings.PRODUCT_OPS.mathmodels_tab,
        rows=updatable_rows,
    )
```

### 2.4.2 `should_suggest_math_model(row: MathModelRow)`

We encode the eligibility logic we designed:

* `row.framework == "MATH_MODEL"` (in v1)
* `row.formula_text_approved is False`
* `row.model_description_free_text` not empty (or we allow even empty)
* Either:

  * `row.llm_suggested_formula_text` is empty, **or**
  * Some explicit “refresh” condition (we can add a `llm_refresh` boolean column later).

---

## 2.5 MathModelsWriter – suggestion update

### `app/sheets/mathmodels_writer.py`

We add a method that writes **only** the suggestion columns:

* `llm_suggested_formula_text`
* `assumptions_text`
* `llm_notes`

And leaves all other columns intact.

Implementation sketch:

* Map headers → column indices.
* For each `MathModelRow` in `rows`:

  * Compute A1 range for the three columns at that row_number.
  * Use Sheets `batchUpdate` to update all suggestion cells in one go.

This mirrors how we already do `--write-scores` for ProductOps Scoring tab.

---

## 2.6 Flow 4 CLI – add `--suggest-mathmodel`

### `test_scripts/flow4_mathmodels_cli.py`

Add a mode:

```bash
uv run python -m test_scripts.flow4_mathmodels_cli --suggest-mathmodel --log-level INFO
```

CLI flow:

1. Open DB session + SheetsClient + LLMClient.
2. Call `run_math_model_generation_job`.
3. Log summary:

   * how many rows scanned
   * how many suggestions written
   * log a couple of examples (initiative_key, formula excerpt).

---

## 2.7 Safeguards & PM control

* We **never** touch:

  * `formula_text_final`
  * `formula_text_approved`

* We only fill or update:

  * `llm_suggested_formula_text`
  * `assumptions_text` (if empty or allowed to refresh)
  * `llm_notes` (same rule)

* If PM wants to fully override LLM:

  * They can ignore the suggestion and write their own `formula_text_final`.
  * Once they tick `formula_text_approved = TRUE`, LLM suggestions become irrelevant for param seeding and scoring.

---

Now — let’s outline **Phase 4 – Deep Dive 3: `suggest_param_metadata` + automatic Params seeding**.

This is the second half of the LLM-assisted experience:
**once a formula is approved, the system discovers its variables and generates parameter rows (with labels, units, descriptions, ranges, etc.) in the Params tab.**

This is the heart of turning PM-defined math logic into a functioning, data-driven scoring framework.

---

# Phase 4 – Deep Dive 3: `suggest_param_metadata` + Auto-Seeding Params

## 🎯 Goal

When a PM approves a formula in MathModels:

* Backend extracts raw identifiers from `formula_text_final`
* Backend calls LLM to generate **metadata** for each parameter:

  * `param_display`
  * `description`
  * `unit`
  * `min`, `max`
  * `source`
* Backend creates new rows in the **Params** tab (only for missing params)
* All rows are created with:

  * `is_auto_seeded = TRUE`
  * `approved = FALSE` (PM must approve manually)

This enables:

* Clean parameters for scoring
* Consistent modeling UX
* No column explosion because Params is row-normalized

This Deep Dive does **not** evaluate formulas or compute scores — that’s Deep Dive 4.

---

# 🔧 Deep Dive 3.1 – Identify rows that require parameter seeding

### When to run param seeding

We run this in a job like:

```bash
uv run python -m test_scripts.flow4_mathmodels_cli --seed-params
```

A MathModels row is eligible when:

1. `formula_text_final` is **not empty**
2. `formula_text_approved = TRUE`
3. `framework = MATH_MODEL` (v1)
4. Some parameters in the formula **do not yet exist in Params tab** for this initiative+framework

This ensures:

* PM is always in control
* LLM never seeds params prematurely
* Changes in formula are handled gracefully (new params only)

---

# 🧠 Deep Dive 3.2 – Deterministic extraction of raw identifiers

We use a purely mechanical function to extract variable names:

```python
raw_identifiers = extract_identifiers(formula_text_final)
```

This guarantees:

* No hallucinated parameters
* No missing parameters
* No renaming surprises

Examples:

`value = uplift_conv * baseline_conv * monthly_sessions * aov - infra_cost`

Extracts:

```python
["uplift_conv", "baseline_conv", "monthly_sessions", "aov", "infra_cost"]
```

**DO NOT** ask LLM to tell us which variables appear — LLM only interprets them.

---

# 🤖 Deep Dive 3.3 – LLM call: `suggest_param_metadata`

### Inputs passed into LLM

We send:

* Initiative summary fields:

  * title
  * llm_summary
  * problem_statement
  * desired_outcome
  * any impact/effort values that help
* Math model fields:

  * `model_name`
  * `formula_text_final`
  * `assumptions_text`
* Raw identifiers list
* Additional context:

  * Typical parameter categories (traffic, conversion, margin, cost)
  * Role hints (`Analytics` owns traffic, `Finance` owns margin/AOV, etc.)

LLM is instructed:

* **DO NOT** invent new parameters
* Return metadata **for each identifier**
* Use a stable JSON format

---

# 📤 Deep Dive 3.4 – Expected LLM output schema

We instruct LLM to return:

```json
{
  "parameters": [
    {
      "name": "uplift_conv",
      "display": "Uplift in Conversion Rate",
      "description": "Expected absolute conversion uplift caused by this initiative.",
      "unit": "fraction",
      "min": 0,
      "max": 0.2,
      "source": "Analytics"
    },
    {
      "name": "baseline_conv",
      "display": "Baseline Conversion Rate",
      ...
    }
  ]
}
```

We will define a Pydantic schema to validate this output.

---

# 📝 Deep Dive 3.5 – ParamsWriter: add new rows to Params tab

For each new parameter:

We create a row in `Params` tab:

| Column         | Value                         | Notes     |
| -------------- | ----------------------------- | --------- |
| initiative_key | e.g., `INIT-123`              | RO        |
| framework      | `"MATH_MODEL"`                | RO        |
| param_name     | `"uplift_conv"`               | RO        |
| param_display  | `"Uplift in Conversion Rate"` | Editable  |
| description    | Text                          | Editable  |
| value          | *(blank)*                     | PM fills  |
| unit           | `"%"` or `"fraction"`         | Editable  |
| min            | as suggested                  | Editable  |
| max            | as suggested                  | Editable  |
| source         | `"Analytics"`                 | Editable  |
| approved       | `FALSE`                       | PM checks |
| is_auto_seeded | `TRUE`                        | RO        |
| notes          | *(blank)*                     | Editable  |

All rows must have:

* `is_auto_seeded = TRUE`
* `approved = FALSE`

We explicitly require PM/Analytics/Finance to approve parameter values before scoring.

---

# 🔁 Deep Dive 3.6 – Updating DB side (Params → InitiativeMathModel / Param table)

Depending on which DB design option we adopt (A or B):

### **Option A – Dedicated param table (`InitiativeParam`)**

* Upsert each param row into DB
* Link via `(initiative_id, framework, param_name)`
* Store:

  * full metadata + value

### **Option B – parameters_json inside `InitiativeMathModel`**

* Collect all params inside a dict:

  ```python
  parameters_json = {
    "uplift_conv": {"value":…, "unit":…, "min":…, …},
    ...
  }
  ```
* Persist after param sync.

Either way, scoring in Deep Dive 4 will read from DB, not directly from Params tab.

---

# 🔄 Deep Dive 3.7 – Idempotency & how formula updates trigger param updates

We define rules:

1. **New identifiers** → create new Params rows
2. **Removed identifiers** → keep old Params rows (for safety) but mark them unused
   (Later, we can add a “deprecate param” feature)
3. **Changed identifiers** → treat as new parameters
4. **LLM regenerations** do NOT override existing metadata
   unless explicitly requested by PM (future “refresh metadata” flag)
5. **Human edits always win** — we never override human-edited fields

---

# 🚦 Deep Dive 3.8 – CLI operations

We extend Flow 4 CLI:

```
--seed-params
    Reads MathModels tab
    For each approved formula:
        - Extract identifiers
        - Call LLM for metadata only for new params
        - Write new param rows to Params sheet
        - Sync new params to DB
```

Optional:

```
--preview-params-needed
    Shows which initiatives/formulas need parameter seeding
```

---

# 📌 Deep Dive 3.9 – What PM experiences after Deep Dive 3

**PM flow now becomes:**

1. PM approves a formula in MathModels.
2. Backend automatically:

   * Extracts variables
   * Calls LLM to propose metadata
   * Populates Params tab with new rows
3. PM/team fills numbers (`value`, maybe unit/min/max)
4. PM checks `approved = TRUE`
5. PM triggers scoring (or Flow 3 / Flow 2 handles it downstream)

This UX is extremely clean and powerful.

---

# Phase 4 – Deep Dive 4 (Updated): MathModel Scoring via SafeEvaluator + ScoringService

**High-level goal**

After Deep Dive 4:

* Each initiative can have **its own math model script** in `formula_text_final` (with sub-formulas + master formula).
* Parameters live in the **Params** tab (then in DB).
* A generic **MathModelFramework** can:

  * Load the script for that initiative,
  * Load the parameter values,
  * Run the script in a **safe math sandbox**,
  * Read `value`, `effort`/`overall`, and return scores.
* Flow 2’s scoring activation integrates MATH_MODEL like RICE/WSJF.

No hardcoding per initiative; formula is fully data-driven.

---

## 4.1 What a math model script looks like (from PM perspective)

In **MathModels tab → `formula_text_final`**, a PM (or LLM, then PM edits) might write:

```text
# Ticket savings
ticket_savings = ticket_reduction_per_month * cost_per_ticket * horizon_months

# Churn savings
churn_savings = churn_reduction * affected_customers * customer_lifetime_value

# Total cost
total_cost = one_off_cost + monthly_running_cost * horizon_months

# Master value formula
value = ticket_savings + churn_savings - total_cost

# Optional explicit effort / ROI
# (if omitted, backend falls back to initiative.effort_engineering_days)
effort = effort_days
overall = value / effort
```

Key properties:

* Multi-line, multiple sub-formulas.
* Named variables, not cell references.
* Final outputs:

  * `value` (required for scoring),
  * optionally `effort` and/or `overall` (optional, but supported).

Different initiatives can have completely different scripts.

---

## 4.2 Backend engine: SafeEvaluator mini-language

We define a **small, safe “language”** that the engine will accept:

* Syntax:

  * lines of: `name = expression`
  * optional comments starting with `#`
* Expressions:

  * numeric literals (`1`, `0.05`, `100000`)
  * arithmetic `+ - * /`, parentheses
  * parameter names (from Params tab)
  * previously defined variables (`ticket_savings`, etc.)
  * a small set of safe functions (v1: maybe `min`, `max`; later could add more)

No loops, no imports, no file/network IO.

**At runtime**:

```python
env = {param_name: param_value, ...}  # from DB/Params
env = evaluate_script(formula_text_final, env)  # SafeEvaluator does this
value_score = env["value"]
effort_score = env.get("effort") or initiative.effort_engineering_days
overall_score = env.get("overall") or (value_score / effort_score if both present)
```

So the compute function is:

> “Run this script in a sandbox with these variables, then read the results.”

---

## 4.3 DB and model changes

We keep the DB design consistent with our per-framework pattern.

### 4.3.1 InitiativeMathModel (from Deep Dive 1)

Already planned/created:

* `InitiativeMathModel`:

  * `id`
  * `initiative_id` (FK)
  * `framework` (e.g. `"MATH_MODEL"`)
  * `model_name`
  * `formula_text` (synced from `formula_text_final`)
  * `assumptions_text`
  * `parameters_json` (optional, if we mirror Params)
  * `llm_notes`
  * `approved_by_user` (mirrors `formula_text_approved`)

### 4.3.2 Per-framework score fields for math (Recommended)

Add fields to `Initiative`:

* `math_value_score: float | None`
* `math_effort_score: float | None`
* `math_overall_score: float | None`

**Files:**

* `app/db/models/initiative.py`
* Alembic migration

**Why:** keep symmetry with RICE/WSJF (`rice_*`, `wsjf_*`) for Flow 3 & comparisons.

### 4.3.3 Parameters

From Deep Dive 1/3, Params are already syncing to DB (either as `InitiativeParam` rows or via `parameters_json`). We’ll assume:

* `MathModelFramework` can get a dict:

  ```python
  params = {"ticket_reduction_per_month": ..., "cost_per_ticket": ..., ...}
  ```

only for parameters where `approved = TRUE`.

---

## 4.4 Implement `evaluate_script` (SafeEvaluator)

We introduce a reusable utility:

**File:** `app/utils/math_eval.py`

Key function:

```python
def evaluate_script(script: str, initial_env: dict[str, float]) -> dict[str, float]:
    """
    Run a multi-line math script in a safe sandbox.
    - script: contents of formula_text_final
    - initial_env: parameter name -> value
    Returns the final environment (including new variables like 'value', 'overall', etc.)
    """
    ...
```

Responsibilities:

1. **Preprocess**:

   * Split by lines.
   * Ignore blank lines, comments (`# ...`).

2. **Parse lines**:

   * Each line must be `name = expression`.
   * Validate `name` format (e.g. snake_case, not reserved).

3. **Evaluate expressions** with a safe evaluator:

   * Provide `initial_env` as symbol table.
   * Only allow:

     * numbers, variables, `+ - * /`, parentheses
     * maybe `min`, `max`, etc. via a white-listed functions dict.

4. **Update env** line by line:

   * Evaluate expression  → result (float)
   * Set `env[name] = result`

5. Return the final `env`.

This function is **generic and stateless**: it doesn’t know about initiatives; just “run script with this env”.

---

## 4.5 Implement `MathModelFramework`

**File:** `app/services/scoring/math_model_framework.py`

Responsibilities:

1. **Load model**:

   * Find `InitiativeMathModel` for `(initiative.id, framework="MATH_MODEL")`.
   * Ensure `approved_by_user = True` (or else skip/return None).

2. **Load parameters**:

   * From DB:

     * Either via `InitiativeParam` table, or
     * Converting `parameters_json` into a dict.
   * Include only `approved = TRUE`.

   Example:

   ```python
   params = {
       "ticket_reduction_per_month": 2000,
       "cost_per_ticket": 5.0,
       "horizon_months": 12,
       "churn_reduction": 0.01,
       "affected_customers": 100000,
       "customer_lifetime_value": 120.0,
       "one_off_cost": 50000,
       "monthly_running_cost": 10000,
       "effort_days": 70.0,
   }
   ```

3. **Run script**:

   ```python
   env = evaluate_script(model.formula_text, params)
   ```

4. **Read outputs**:

   * `value_score = env.get("value")`

   * `effort_score`:

     ```python
     effort_score = (
         env.get("effort")
         or env.get("effort_days")
         or initiative.effort_engineering_days
     )
     ```

   * `overall_score`:

     ```python
     overall_score = env.get("overall")
     if overall_score is None and value_score is not None and effort_score:
         overall_score = value_score / effort_score
     ```

5. **Return `ScoreResult`**:

   ```python
   return ScoreResult(
       value_score=value_score,
       effort_score=effort_score,
       overall_score=overall_score,
       raw_inputs={"formula": model.formula_text, "params": params},
   )
   ```

No knowledge of particular formulas needed; it just interprets the script.

---

## 4.6 Register `MathModelFramework` 

In `app/services/scoring/interfaces.py` (where `ScoringFramework` is defined), add something like:

```python
from enum import Enum

class ScoringFramework(str, Enum):
    RICE = "RICE"
    WSJF = "WSJF"
    MATH_MODEL = "MATH_MODEL"   # NEW
```

Now the rest of the system can refer to `ScoringFramework.MATH_MODEL`.

---

Under our existing structure:

* `app/services/scoring/engines/`

  * `rice.py`
  * `wsjf.py`
  * ➕ **`math_model.py` (new)**

In `math_model.py` we’ll implement something like:

```python
from app.services.scoring.interfaces import ScoringEngine
from app.db.models.initiative import Initiative
from app.utils.math_eval import evaluate_script

class MathModelScoringEngine(ScoringEngine):
    """
    Engine that evaluates per-initiative math model scripts using the SafeEvaluator.
    """

    def score(self, initiative: Initiative) -> "ScoreResult":
        # 1. Load InitiativeMathModel for this initiative (from DB)
        # 2. Load approved params into a dict
        # 3. env = evaluate_script(model.formula_text, params)
        # 4. Read value / effort / overall from env
        # 5. Return ScoreResult(value_score, effort_score, overall_score, raw_inputs=...)
        ...
```

---

In `app/services/scoring/registry.py`, import the new engine and extend the `SCORING_FRAMEWORKS` dict:

```python
from app.services.scoring.interfaces import ScoringFramework, ScoringEngine
from app.services.scoring.engines import RiceScoringEngine, WsjfScoringEngine
from app.services.scoring.engines.math_model import MathModelScoringEngine  # NEW


SCORING_FRAMEWORKS: Dict[ScoringFramework, FrameworkInfo] = {
    ScoringFramework.RICE: FrameworkInfo(
        name=ScoringFramework.RICE,
        label="RICE",
        description="Reach * Impact * Confidence / Effort",
        required_fields=["reach", "impact", "confidence", "effort"],
        engine=RiceScoringEngine(),
    ),
    ScoringFramework.WSJF: FrameworkInfo(
        name=ScoringFramework.WSJF,
        label="WSJF",
        description="(Business Value + Time Criticality + Risk Reduction) / Job Size",
        required_fields=["business_value", "time_criticality", "risk_reduction", "job_size"],
        engine=WsjfScoringEngine(),
    ),
    ScoringFramework.MATH_MODEL: FrameworkInfo(                    # NEW
        name=ScoringFramework.MATH_MODEL,
        label="MATH_MODEL",
        description="Custom per-initiative math model script",
        required_fields=[],  # we treat params as external; or put something minimal here
        engine=MathModelScoringEngine(),
    ),
}
```

Now `get_engine(ScoringFramework.MATH_MODEL)` returns our math engine.

---

Wherever we currently do something like:

```python
from app.services.scoring.registry import get_engine
from app.services.scoring.interfaces import ScoringFramework

engine = get_engine(ScoringFramework.RICE)
result = engine.score(initiative)
```

We’ll now also be able to do:

```python
engine = get_engine(ScoringFramework.MATH_MODEL)
result = engine.score(initiative)
```

And where we use the `active_scoring_framework` attribute of `Initiative` (or from sheets):

```python
engine = get_engine(initiative.active_scoring_framework)
result = engine.score(initiative)
```

Math model just becomes another key in the same map.

The **per-framework fields update** (like `math_value_score`, etc.) will live in the layer that calls the engine (our existing scoring service / job), not in the engine itself — that’s exactly parallel to how we likely treat RICE/WSJF today.

---

To be explicit:

* ✅ **Keep**:

  * `registry.py` (this *is* the factory/registry)
  * `engines/` structure (`RiceScoringEngine`, `WsjfScoringEngine`, etc.)
  * `ScoringFramework` enum in `interfaces.py`

* ✅ **Add**:

  * New enum member: `MATH_MODEL`
  * New engine class: `MathModelScoringEngine` in `engines/math_model.py`
  * New registry entry: `ScoringFramework.MATH_MODEL` in `SCORING_FRAMEWORKS`

---

## 4.7 Extend ScoringService to handle MATH_MODEL per-framework fields

**File:** `app/services/scoring_service.py`

Where we already have per-framework branching (RICE, WSJF), extend to handle `MATH_MODEL`:

* In `_compute_framework_scores_only(initiative, framework, enable_history)`:

  * For `framework == "MATH_MODEL"`:

    ```python
    result = math_model_framework.score(initiative)

    initiative.math_value_score = result.value_score
    initiative.math_effort_score = result.effort_score
    initiative.math_overall_score = result.overall_score
    ```

  * And create `InitiativeScore` history row:

    * `framework_name = "MATH_MODEL"`
    * `inputs_json = result.raw_inputs` (formula + params snapshot)

* In `score_initiative_all_frameworks(initiative, enable_history)`:

  * Optionally compute math model alongside RICE/WSJF if `use_math_model = True`.

No change yet to active fields — Flow 2 will still manage activation.

---

## 4.8 Integrate with Flow 2 (activation of active scores)

**File:** `app/jobs/flow2_scoring_cli.py` / `app/jobs/scoring_job.py`

Flow 2’s existing logic:

* For each initiative:

  * Uses `active_scoring_framework` to decide which per-framework fields to copy into:

    * `value_score`
    * `effort_score`
    * `overall_score`

We extend:

* When `active_scoring_framework = "MATH_MODEL"`:

  ```python
  initiative.value_score = initiative.math_value_score
  initiative.effort_score = initiative.math_effort_score
  initiative.overall_score = initiative.math_overall_score
  ```

Then:

* Flow 2 remains the **only** place that sets active scores based on the chosen framework.
* Flow 3 + Flow 1 continue to propagate `value_score`/`overall_score` to ProductOps Scoring tab & Central Backlog sheet as already documented.

---

## 4.9 CLI usage & test flow

Once Deep Dive 4 is done, the end-to-end test for math models will look like:

1. **Sync data from ProductOps tabs ⇆ DB** (Deep Dive 1 services):

   ```bash
   uv run python -m test_scripts.flow4_mathmodels_cli --sync-mathmodels
   uv run python -m test_scripts.flow4_mathmodels_cli --sync-params
   ```

2. **Compute per-framework scores** (including MATH_MODEL):

   ```bash
   uv run python -m test_scripts.flow3_product_ops_cli --compute-all --log-level INFO
   # Or a dedicated scoring CLI that calls ScoringService for math model too
   ```

3. **Activate active scores per initiative**:

   ```bash
   uv run python -m test_scripts.flow2_scoring_cli --all --log-level INFO
   ```

4. **Write scores back to ProductOps Scoring tab & Central Backlog**:

   ```bash
   uv run python -m test_scripts.flow3_product_ops_cli --write-scores --log-level INFO
   uv run python -m test_scripts.backlog_sync_cli --log-level INFO
   ```

---

## 4.10 Resulting behavior

After Deep Dive 4:

* PMs / LLM can define **rich, multi-line math scripts** per initiative.
* Parameters are defined & approved via Params tab.
* The backend:

  * Safely evaluates scripts per initiative using parameter values.
  * Stores math-specific scores in `math_*_score` fields.
  * Lets Flow 2 treat MATH_MODEL just like RICE/WSJF for activation and propagation.

And we hit our key requirement:

> “I want our system to be able to build proper logical financial models per initiative… potentially different structure per initiative, master + sub-formulas, etc.”

All that is just “different scripts for different initiatives” executed in the same SafeEvaluator engine.

---


Now, let’s do **Deep Dive 5** properly and close the loop from “math model scores computed” → “PM can actually *see and compare* them”.

We’ll keep everything consistent with:

* Existing ProductOps **Scoring_Inputs** tab (I’ll just call it **Scoring tab**)
* Existing Central Backlog
* Flows 1, 2, 3 we already have

---

# Phase 4 – Deep Dive 5: Surfacing Math Model Scores in ProductOps & Central Backlog

## 🎯 Goal

After Deep Dive 5:

1. **ProductOps → Scoring tab** shows **RICE**, **WSJF**, **MATH_MODEL** scores side-by-side for each initiative.
2. PM can:

   * Compare frameworks per initiative (RICE vs WSJF vs MathModel).
   * Choose `active_scoring_framework` based on these comparisons.
3. **Central Backlog** continues to show:

   * The **active** scores (`value_score`, `effort_score`, `overall_score`) for the chosen framework.
   * Optionally, we can add “reference” columns for per-framework scores if we want.
4. All of this is driven by existing flows:

   * Flow 3 `--compute-all` + `--write-scores`
   * Flow 2 `--all`
   * Flow 1 Backlog Sync

---

## 5.1 ProductOps Scoring tab – what it will look like

Right now, our **Scoring_Inputs** tab already contains:

* `initiative_key`
* `active_scoring_framework`
* `use_math_model`
* RICE input fields + output columns (`rice_value_score`, `rice_overall_score`, etc.)
* WSJF inputs/outputs

For v1 of MathModel, we want this tab to be primarily a **scoreboard**, not a parameter entry sheet (parameters live in **Params** now). So we’ll evolve it to something like:

### Scoring tab – MVP columns (post-Phase 4)

Per row (one initiative):

* Identity & control:

  * `initiative_key`
  * maybe `title` (nice to have)
  * `active_scoring_framework` (dropdown: `RICE`, `WSJF`, `MATH_MODEL`, …)
  * `use_math_model` (checkbox)
  * `strategic_priority_coefficient` (already there)

* RICE scores:

  * `rice_value_score`
  * `rice_effort_score`
  * `rice_overall_score`

* WSJF scores:

  * `wsjf_value_score`
  * `wsjf_effort_score`
  * `wsjf_overall_score`

* **MATH_MODEL scores (new):**

  * `math_value_score`
  * `math_effort_score`
  * `math_overall_score`

Optionally, we can also show the **active** scores as a quick reference:

* `active_value_score` (mirror of Initiative.value_score)
* `active_effort_score`
* `active_overall_score`

But core comparison happens in those per-framework columns.

### Editability:

* `initiative_key` – read-only
* `active_scoring_framework` – **PM editable**
* `use_math_model` – **PM editable**
* `strategic_priority_coefficient` – **PM editable**
* All per-framework score columns (`rice_*_score`, `wsjf_*_score`, `math_*_score`) – **backend-owned / read-only** (written by Flow 3 `--write-scores`)

So in Scoring tab, PM doesn’t type scores; they just **see them and choose** which framework is active.

---

## 5.2 How scores get into the Scoring tab

### 5.2.1 DB: where scores live

After Deep Dive 4, DB has per-framework math scores on `Initiative`:

* `rice_value_score`, `rice_effort_score`, `rice_overall_score`
* `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`
* `math_value_score`, `math_effort_score`, `math_overall_score`  **(new)**

ScoringService + engines populate those.

### 5.2.2 Flow 3 `--compute-all` – now also does MathModel

we already have Flow 3 `--compute-all` computing **RICE + WSJF per-framework fields** without touching active scores.

We extend its behavior:

* For each initiative:

  * **RICE**: as before (if full inputs available).
  * **WSJF**: as before.
  * **MATH_MODEL**:

    * If:

      * `use_math_model = TRUE`, and
      * `InitiativeMathModel` exists and `approved_by_user = TRUE`, and
      * Required params exist & are `approved = TRUE` in DB,
    * Then run `MathModelScoringEngine.score(initiative)`.
    * Write result to:

      * `initiative.math_value_score`
      * `initiative.math_effort_score`
      * `initiative.math_overall_score`

* Commit in batches as we already do.

### 5.2.3 Flow 3 `--write-scores` – extend writer to include MathModel

we already have a ProductOps writer that writes RICE & WSJF score columns back to Scoring tab (`rice_*_score`, `wsjf_*_score`).

We extend the mapping to also include:

* `math_value_score`
* `math_effort_score`
* `math_overall_score`

**Files to touch:**

* `app/sheets/productops_writer.py` (or equivalent)

  * When building `values` to write:

    ```python
    row["math_value_score"] = initiative.math_value_score
    row["math_effort_score"] = initiative.math_effort_score
    row["math_overall_score"] = initiative.math_overall_score
    ```

* `test_scripts/flow3_product_ops_cli.py`

  * No new flags needed; `--write-scores` just writes all per-framework scores including math now.

---

## 5.3 How PM compares frameworks in ProductOps

Once Deep Dive 5 is in place, the **PM workflow** for comparison looks like this:

1. **Run all computations** (RICE + WSJF + MATH_MODEL):

   ```bash
   uv run python -m test_scripts.flow3_product_ops_cli --compute-all --log-level INFO
   uv run python -m test_scripts.flow3_product_ops_cli --write-scores --log-level INFO
   ```

2. **Open ProductOps → Scoring tab**.

For an initiative, they will see something like:

| initiative_key | active_scoring_framework | use_math_model | rice_overall_score | wsjf_overall_score | math_overall_score |
| -------------- | ------------------------ | -------------- | ------------------ | ------------------ | ------------------ |
| INIT-001       | RICE                     | FALSE          | 45.2               | 38.7               |                    |
| INIT-002       | MATH_MODEL               | TRUE           | 30.1               | 27.4               | 52.3               |
| INIT-003       | WSJF                     | TRUE           | 18.0               | 55.6               | 49.0               |

The PM can:

* Compare scores across RICE/WSJF/MathModel.
* Decide which framework should drive the **active** prioritization for each initiative:

  * For `INIT-002`, maybe keep `MATH_MODEL`.
  * For `INIT-003`, maybe keep `WSJF` even though math model exists, depending on trust.

They then:

* Change `active_scoring_framework` cell per initiative accordingly (dropdown).

---

## 5.4 How this flows into Central Backlog

Central Backlog is designed to show:

* One set of **active** scores per initiative (plus some metadata).
* Not necessarily every framework’s scores (to keep it simpler).

### 5.4.1 Flow 2: activate chosen framework

we already have Flow 2 doing:

* For each initiative:

  * Read `active_scoring_framework` from DB.
  * Copy per-framework scores into:

    * `value_score`
    * `effort_score`
    * `overall_score`

With MathModel integrated, the logic becomes:

```python
if initiative.active_scoring_framework == ScoringFramework.RICE:
    initiative.value_score = initiative.rice_value_score
    initiative.effort_score = initiative.rice_effort_score
    initiative.overall_score = initiative.rice_overall_score

elif initiative.active_scoring_framework == ScoringFramework.WSJF:
    initiative.value_score = initiative.wsjf_value_score
    initiative.effort_score = initiative.wsjf_effort_score
    initiative.overall_score = initiative.wsjf_overall_score

elif initiative.active_scoring_framework == ScoringFramework.MATH_MODEL:
    initiative.value_score = initiative.math_value_score
    initiative.effort_score = initiative.math_effort_score
    initiative.overall_score = initiative.math_overall_score
```

Then Flow 2 commits.

### 5.4.2 Flow 1: Backlog Sync (DB → Central Backlog sheet)

our Backlog writer already writes:

* `value_score`, `effort_score`, `overall_score`
* `active_scoring_framework`
* `use_math_model`
* plus many other initiative fields

We keep Central Backlog as **framework-agnostic**:

* It **doesn’t need to know** RICE vs WSJF vs MATH_MODEL; it just shows the final active numbers.
* It shows `active_scoring_framework` so people know **where those numbers come from**.

If we want, we could later add extra columns like:

* `rice_overall_score`
* `wsjf_overall_score`
* `math_overall_score`

But I would recommend:

* **MVP**: Central Backlog shows **active** scores only.
* Detailed per-framework comparison lives in the ProductOps Scoring tab.

That keeps Central Backlog clean & easier to maintain.

---

## 5.5 Updated “full flow” including MathModel

Putting it all together:

1. **ProductOps / PM side**:

   * PM defines/approves math model scripts in **MathModels tab**.
   * PM/Analytics/Finance fill & approve parameters in **Params tab**.
   * PM runs RICE/WSJF inputs as usual (or via Params when we migrate those too).

2. **Flow 3 – ProductOps scoring**:

   * `--compute-all`:

     * Computes RICE + WSJF + MATH_MODEL per-framework scores into DB fields:

       * `rice_*_score`, `wsjf_*_score`, `math_*_score`.
   * `--write-scores`:

     * Writes those per-framework scores to **ProductOps → Scoring tab**.

3. **PM comparison & choice**:

   * Opens Scoring tab.
   * Compares `rice_overall_score`, `wsjf_overall_score`, `math_overall_score`.
   * Sets `active_scoring_framework` per initiative.

4. **Flow 2 – active score activation**:

   * `uv run python -m test_scripts.flow2_scoring_cli --all --log-level INFO`
   * Copies from selected per-framework fields into:

     * `value_score`, `effort_score`, `overall_score`.

5. **Flow 1 – Backlog Sync to Central Backlog**:

   * `uv run python -m test_scripts.backlog_sync_cli --log-level INFO`
   * Writes updated active scores & `active_scoring_framework` to Central Backlog sheet.

Result:

* **ProductOps Scoring tab** is where PMs **play and compare frameworks**.
* **Central Backlog** is the clean, simplified view that shows “here’s the final score we’re using and which framework it comes from.”

---

## 5.6 PM-facing summary

From the PM’s point of view:

1. They design a math model in MathModels + Params.

2. They run scoring flows (or someone runs them).

3. They go to ProductOps → Scoring tab and see:

   > “For INIT-123, RICE says 40, WSJF says 35, MathModel says 55 overall.”

4. They think: “MathModel is the most realistic for this initiative,” so they set:

   * `active_scoring_framework = MATH_MODEL`.

5. After Flow 2 + Backlog Sync:

   * Central Backlog’s `value_score` / `overall_score` now reflect the MathModel numbers.
   * `active_scoring_framework = MATH_MODEL` on Central Backlog explains where the score came from.
   * All downstream things (roadmap generation, optimization, etc.) use those active numbers.

---

If we’re happy with this Deep Dive 5 design (Scoring tab as multi-framework scoreboard, Central Backlog as active view, flows wired as above), then the roadmap for Deep Dive 5 implementation is:

* Update Scoring tab schema & ProductOps writer to include `math_*_score` columns.
* Extend Flow 3 compute/write logic accordingly.
* Confirm Flow 2 activation already handles MATH_MODEL (from Deep Dive 4).
* Decide later if we want Central Backlog to show per-framework scores or only the active ones.



---

After reviewing all deep dives, now, this can be the actual implementation plan:

# 🌗 Phase 4 – Updated Step-by-Step Implementation Plan

## **Step 1 – ProductOps plumbing & sheet schemas (MathModels + Params + Scoring)**

**Goal:** Wire the ProductOps workbook so the backend knows about all relevant tabs and their columns.

1. **Config:**

   * Extend `ProductOpsConfig` + `product_ops_config.json` to include:

     * `mathmodels_tab = "MathModels"`
     * `params_tab = "Params"`
     * Keep `scoring_inputs_tab = "Scoring_Inputs"`
     * (Future: `config_tab = "Config"`)

2. **MathModels tab schema (MVP columns):**

   * `initiative_key` (RO, backend)
   * `framework` (RO, backend; v1: `MATH_MODEL`)
   * `model_name` (PM)
   * `model_description_free_text` (PM)
   * `model_prompt_to_llm` (PM, optional)
   * `llm_suggested_formula_text` (LLM → RO)
   * `assumptions_text` (LLM seeds, PM editable)
   * `llm_notes` (LLM seeds, PM editable)
   * `formula_text_final` (PM – canonical script)
   * `formula_text_approved` (PM checkbox)

3. **Params tab schema (MVP columns):**

   * `initiative_key` (RO, backend)
   * `framework` (RO, backend; e.g. `MATH_MODEL`, `RICE`, `WSJF`)
   * `param_name` (RO for auto-seeded)
   * `param_display` (LLM seeds, PM editable)
   * `description` (LLM seeds, PM editable)
   * `value` (humans)
   * `unit` (LLM seeds, editable)
   * `min`, `max` (optional, editable)
   * `source` (LLM suggests, editable)
   * `approved` (checkbox)
   * `is_auto_seeded` (RO, backend)
   * `notes` (editable)

4. **Scoring tab evolution (structure only for now):**

   * Ensure we plan for per-framework score columns:

     * `rice_value_score`, `rice_effort_score`, `rice_overall_score`
     * `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`
     * `math_value_score`, `math_effort_score`, `math_overall_score` (new)

> Output: config + sheet schemas frozen; no logic yet.

---

## **Step 2 – DB models & Pydantic schemas**

**Goal:** Create persistent homes in DB and internal schemas for math models & params.

1. **DB models (`app/db/models/scoring.py`):**

   * `InitiativeMathModel`:

     * `initiative_id`, `framework`, `model_name`
     * `formula_text`
     * `assumptions_text`
     * `parameters_json` (optional mirror of Params)
     * `llm_notes`
     * `approved_by_user` (mirrors `formula_text_approved`)
   * (Optional/Recommended) `InitiativeParam`:

     * `initiative_id`, `framework`, `param_name`
     * `param_display`, `description`
     * `value`, `unit`, `min`, `max`
     * `source`, `approved`, `is_auto_seeded`, `notes`

2. **Add per-framework math score fields to `Initiative`:**

   * `math_value_score`, `math_effort_score`, `math_overall_score`.

3. **Pydantic schemas (`app/schemas/scoring.py`):**

   * `MathModelSchema` (for `InitiativeMathModel`)
   * `ParamSchema` (for `InitiativeParam` or Params JSON)

4. **Alembic migrations** for all new columns/tables.

> Output: DB + schemas ready; nothing talking to Sheets/LLM yet.

---

## **Step 3 – Sheets readers/writers for MathModels & Params**

**Goal:** Bi-directional I/O layer for the new tabs, similar to your existing Flow 3 ProductOps readers/writers.

1. **MathModelsReader / Writer (`app/sheets/mathmodels_reader.py`, `mathmodels_writer.py`):**

   * Reader:

     * Reads `MathModels` tab.
     * Returns `MathModelRow` objects with `row_number`.
   * Writer:

     * Can update suggestion columns (`llm_suggested_formula_text`, `assumptions_text`, `llm_notes`) for specific rows.
     * Can later be extended for other fields if needed.

2. **ParamsReader / Writer (`app/sheets/params_reader.py`, `params_writer.py`):**

   * Reader:

     * Reads `Params` tab into `ParamRow` objects (with `row_number`).
   * Writer:

     * Can append new param rows.
     * Can update existing param rows selectively (for seeding/update flows).
     * Implement row-level locking or append-only strategy for new params
     * Backend never updates existing value/approved fields
     * Add last_sync_timestamp to detect stale reads

> Output: we can read & write MathModels and Params tabs just like ProductOps Scoring tab.

---

## **Step 4 – Sync services + Flow 4 CLI plumbing (no LLM yet)**

**Goal:** Wire Sheet ↔ DB sync for MathModels and Params; get basic preview & sync CLIs.

1. **MathModelSyncService (`app/services/math_model_service.py`):**

   * Sheet → DB:

     * For each `MathModelRow`:

       * Resolve `initiative` via `initiative_key`.
       * Upsert `InitiativeMathModel` (fields: name, formula_text_final → formula_text, assumptions, llm_notes, approved_by_user).
   * (DB → Sheet optional in v1; mostly Sheet is source of truth here.)

2. **ParamsSyncService (`app/services/params_service.py`):**

   * Sheet → DB:

     * For each `ParamRow`:

       * Resolve initiative.
       * Upsert `InitiativeParam` (or update `parameters_json`).
   * DB → Sheet will be used later for auto-seeding; for now we just need Sheet → DB.

3. **Flow 4 CLI (`test_scripts/flow4_mathmodels_cli.py`):**

   * `--preview-mathmodels`
   * `--sync-mathmodels`
   * `--preview-params`
   * `--sync-params`

> Output: we can sync both tabs into DB and inspect them via CLI without any LLM or scoring logic.

---

## **Step 5 – Formula parsing & SafeEvaluator engine**

**Goal:** Provide a robust math engine to evaluate per-initiative scripts from `formula_text_final`.

1. **Identifier extraction (`app/utils/formula_parser.py`):**

   * `extract_identifiers(formula_text: str) -> list[str]`
   * Used for param seeding (Step 7), not for evaluation.
   * extract_identifiers() needs to distinguish between:
        
        * Parameter names (uplift_conv)
        * Sub-formula variables (ticket_savings)
        * Built-in functions (min, max)
    * Step 5.1 should use AST parsing (Python's ast module) not regex
        
        * Return only leaf identifiers (not assigned-to names on LHS)
        * Exclude built-ins from parameter list


2. **Safe math script evaluation (`app/utils/math_eval.py`):**

   * `evaluate_script(script: str, initial_env: dict[str, float]) -> dict[str, float]`
   * Multi-line support:

     * Ignore comments & blanks.
     * Each non-empty line must be `name = expression`.
   * Expression support:

     * Numeric literals, `+ - * /`, parentheses.
     * Variables from env (params + previously assigned vars).
     * Small whitelist of functions (`min`, `max`, maybe more later).
   * No loops, no imports, no system access.
   * ASTEVAL: app/utils/math_eval.py - REQUIRED IMPLEMENTATION
    from asteval import Interpreter

    def evaluate_script(script: str, initial_env: dict[str, float]) -> dict[str, float]:
        aeval = Interpreter(usersyms=initial_env)
        # Parse line-by-line, update aeval.symtable
        # Return final symtable as dict
    * Formula Validation: 
        
        * def validate_formula(script: str) -> List[str]:
            """Return list of errors (empty = valid)"""
            errors = []
            env = evaluate_script(script, {"dummy": 0.0})
            if "value" not in env:
                errors.append("Formula must assign 'value'")
            return errors


3. **Unit tests** for `evaluate_script` & `extract_identifiers` independently (very important).

> Output: a generic, safe math engine ready for MathModel scoring and param metadata LLM calls.

---

## **Step 6 – MathModel scoring engine + registry integration**

**Goal:** Integrate math model scoring with your existing scoring registry/engines setup.

1. **Extend `ScoringFramework` enum (`app/services/scoring/interfaces.py`):**

   * Add `MATH_MODEL = "MATH_MODEL"`.

2. **Implement `MathModelScoringEngine` (`app/services/scoring/engines/math_model.py`):**

   * `score(initiative: Initiative) -> ScoreResult`:

     * Fetch `InitiativeMathModel` (approved).
     * Fetch approved parameters (`InitiativeParam` or `parameters_json` → dict).
     * Call `evaluate_script(model.formula_text, params)`.
     * Read `value`, `effort`/`effort_days`, `overall` from env.
     * Return `ScoreResult(value_score, effort_score, overall_score, raw_inputs={...})`.
     * Parameter Approval Enforcement:

        * def score(self, initiative: Initiative) -> ScoreResult:
            params = get_approved_params(initiative, "MATH_MODEL")
            if not params or len(params) < required_count:
                return ScoreResult(
                    value_score=None, 
                    error="Unapproved or missing parameters"
                )
            #### ... rest of scoring

3. **Register in `registry.py`:**

   * Import `MathModelScoringEngine`.
   * Add `ScoringFramework.MATH_MODEL` entry in `SCORING_FRAMEWORKS` with label/description and engine instance.

4. **Extend ScoringService (`app/services/scoring_service.py`):**

   * Where it currently calls RICE/WSJF engines via `get_engine`, allow `MATH_MODEL` as well.
   * When scoring MATH_MODEL:

     * Write to `initiative.math_value_score`, `math_effort_score`, `math_overall_score`.
     * Add `InitiativeScore` history row with framework `"MATH_MODEL"`.

> Output: MATH_MODEL is a full first-class framework in your scoring system.

---

## **Step 7 – LLM-assisted formula generation (`suggest_math_model`)**

**Goal:** Use LLM to help PMs create math scripts in MathModels tab.

1. **LLM client support (`app/llm/client.py`):**

   * Add `suggest_math_model()` method returning `MathModelSuggestion` (formula_text, assumptions[], notes).

2. **Scoring assistant helper (`app/llm/scoring_assistant.py`):**

   * `suggest_math_model_for_initiative(initiative, math_model_row, llm_client) -> MathModelSuggestion`
   * Builds prompt using initiative fields + `model_description_free_text` + `model_prompt_to_llm`.

3. **Math model generation job (`app/jobs/math_model_generation_job.py`):**

   * Uses `MathModelsReader` to get rows.
   * Filters rows where:

     * `framework = MATH_MODEL`
     * `formula_text_approved = FALSE`
     * `llm_suggested_formula_text` empty or flagged for refresh.
   * For each:

     * Fetch initiative from DB.
     * Call `suggest_math_model_for_initiative`.
     * Update in-memory `MathModelRow` with:

       * `llm_suggested_formula_text`
       * `assumptions_text` (joined from list)
       * `llm_notes`.
    * Congig for LLM Cost Management:
        - MAX_LLM_CALLS_PER_RUN = 50
        - SKIP_SUGGESTIONS_IF_RECENT = timedelta(hours=24)  # debounce

4. **MathModelsWriter – suggestion updater:**

   * Add method to write suggestion columns for specific rows back to sheet.

5. **Flow 4 CLI:**

   * Add `--suggest-mathmodel` to trigger this job.

> Output: PM can describe the model; LLM fills in candidate formula, assumptions, notes; PM then edits `formula_text_final` and approves.

---

## **Step 8 – LLM-assisted parameter metadata + auto-seeding Params (`suggest_param_metadata`)**

**Goal:** After PM approves a formula, automatically generate nicely structured Params rows for all variables.

1. **Identify eligible formulas:**

   * `framework = MATH_MODEL`
   * `formula_text_final` non-empty
   * `formula_text_approved = TRUE`

2. **Extract raw identifiers via `extract_identifiers`.**

3. **LLM param metadata helper (`app/llm/scoring_assistant.py`):**

   * `suggest_param_metadata(initiative, model, identifiers, llm_client) -> List[ParamSuggestion]`
   * Each suggestion has: `name`, `display`, `description`, `unit`, `min`, `max`, `source`.

4. **Param seeding service (`app/services/param_seeding_service.py`):**

   * For each new identifier not already in Params for (initiative, framework):

     * Construct `ParamRow` with:

       * `initiative_key`, `framework`, `param_name`
       * `param_display`, `description`, `unit`, `min`, `max`, `source`
       * `value` = empty
       * `approved` = FALSE
       * `is_auto_seeded` = TRUE
     * Write to **Params** tab via `ParamsWriter`.
   * Optionally sync these new rows into DB via ParamsSyncService.

5. **Param seeding job (`app/jobs/param_seeding_job.py`):**

   * Scan MathModels for formulas needing params.
   * For each, run the above flow.

6. **Flow 4 CLI:**

   * Add `--seed-params` to trigger param seeding job.

> Output: whenever a formula is approved, Params tab automatically gets rows for its variables, with LLM-suggested labels/units/etc., ready for PM/Analytics to fill `value` and `approved`.

---

## **Step 9 – Integrate MathModel into Flow 3 & Flow 2 (compute + activation)**

**Goal:** Make MATH_MODEL fully participate in the existing scoring and activation flows.

1. **Flow 3 `--compute-all` (`app/jobs/flow3_product_ops_job.py`):**

   * For each initiative:

     * Compute RICE & WSJF as today.
     * If `use_math_model = TRUE` and math model + params are ready:

       * Call `MathModelScoringEngine` via registry.
       * Write `math_value_score`, `math_effort_score`, `math_overall_score`.

2. **Flow 3 `--write-scores` (ProductOps writer):**

   * Extend Scoring tab writer to output:

     * `math_value_score`, `math_effort_score`, `math_overall_score` columns.

3. **Flow 2 `--all` (activation):**

   * Update activation logic:

     * When `active_scoring_framework = MATH_MODEL`:

       * Copy from `math_*_score` to:

         * `value_score`, `effort_score`, `overall_score`.

4. **Keep Flow 1 (Backlog Sync) unchanged conceptually:**

   * Central Backlog sees active scores + `active_scoring_framework`.

> Output: Math model scores are computed along with RICE/WSJF, written into ProductOps Scoring tab, and activated into Initiative’s main score fields when PM selects MATH_MODEL.

---

## **Step 10 – UI consistency, docs, and tests**

**Goal:** Make the whole thing usable and trustworthy.

1. **UI / Sheet consistency:**

   * Ensure:

     * MathModels tab is discoverable and documented for PMs.
     * Params tab has clear header row and notes.
     * Scoring tab per-framework columns appear in a sensible order, with some light formatting.

2. **Documentation:**

   * Update:

     * `initiative_schema.md` with MATH_MODEL, MathModels, Params references.
     * `flow_3_productops.md` with the updated pipeline including MathModel.
     * `scoring.md` with MATH_MODEL description & examples.

3. **Tests:**

   * Unit tests for:

     * `evaluate_script`
     * `extract_identifiers`
     * `MathModelScoringEngine.score` (with example scripts + params)
   * Integration tests for:

     * Param seeding end-to-end on a dummy formula.
     * Scoring end-to-end for a sample initiative using RICE + MATH_MODEL side by side.

4. **Ops notes:**

   * Add cheatsheet entries for new CLIs:

     * `--suggest-mathmodel`
     * `--seed-params`
     * Extended `--compute-all` behavior.

> Output: a solid, documented Phase 4 that’s safe to use in your real-world prioritization flows.

---
