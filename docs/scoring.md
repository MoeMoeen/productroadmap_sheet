

* Scoring ≠ just “RICE-style value/effort”.
* Scoring = **pluggable frameworks**, including:

  * Simple heuristic ones (RICE, MoSCoW, etc.).
  * **Full mathematical models** per initiative with:

    * A formula,
    * Explicit assumptions,
    * LLM-suggested inputs and even suggested scores,
    * Human review / override.

So, we should treat **scoring** as a first-class, modular subsystem.

---

## 1. Core design adjustment (conceptual)

We want:

1. **A unified output** for optimization:
   For each initiative → some canonical numeric fields like:

   * `value_score`
   * `effort_score`
   * `overall_score`
   * `score_framework` (which framework produced it)
   * maybe `score_version` or `score_run_id`

2. **Multiple input frameworks** for scoring:

   * RICE: Reach, Impact, Confidence, Effort
   * MoSCoW: Must/Should/Could/Won’t (mapped to numeric)
   * “Weighted X/Y/Z” frameworks
   * **Full mathematical model**: `Value = f(parameters | assumptions)`

3. **LLM as a scoring assistant**, not the source of truth:

   * Suggests:

     * Framework inputs (e.g. Reach, Impact, Confidence…),
     * For the math model: the **formula** and **assumptions** and **parameter estimates**,
     * Optional suggested final score.
   * Human can:

     * Accept / tweak inputs & assumptions,
     * Accept / override score.

4. A way to **store the formula & assumptions** per initiative so we can:

   * Recalculate when assumptions change,
   * Show the logic to stakeholders,
   * Run Monte Carlo on the model.

This affects mainly the **services**, **LLM**, and **DB/models** layers.

---


#### `app/db/models/scoring.py` (conceptual)

We’ll likely have domain entities like:

* **ScoringFramework** (or just an enum field, but we can model it as a table if we want more metadata):

  * `id`, `name` (`"RICE"`, `"MATH_MODEL"`, …), description.

* **InitiativeScore**

  * FK to `Initiative`
  * FK or enum `framework`
  * `value_score`, `effort_score`, `overall_score`
  * `inputs_json` (all raw inputs like Reach, Impact, etc.)
  * `suggested_by_llm: bool`
  * `approved_by_user: bool`
  * timestamps, maybe `approved_by_user_id`

* **InitiativeMathModel** (for the full mathematical quantification framework):

  * FK to `Initiative`
  * `formula_text` (string representation of the model, e.g. `value = a * uplift * traffic - infra_cost`)
  * `parameters_json` (names, types, ranges)
  * `assumptions_text` (human-readable assumptions)
  * `suggested_by_llm: bool`
  * `approved_by_user: bool`
  * maybe `engine` (e.g. “safe expression language / sympy / custom DSL”)

We’ll formalize these when we get to Step 3, but this gives us a home for:

* The **scores**,
* The **math model**,
* The **LLM vs human** distinction.

#### `app/services/scoring/base_framework.py`

Defines a common interface:

```python
class ScoringFramework(Protocol):
    name: str

    def compute_inputs(self, initiative) -> dict:
        """Optionally compute or fetch needed inputs (maybe using LLM)."""

    def score(self, initiative, inputs: dict) -> "ScoreResult":
        """Return a numeric value/effort/overall score."""
```

Then:

* `RICE_framework.py` requires inputs: Reach, Impact, Confidence, Effort.
* `math_model_framework.py`:

  * Ensures `InitiativeMathModel` exists for the initiative (possibly via LLM suggestion),
  * Evaluates the formula using parameters & assumptions,
  * Returns a `ScoreResult`.

#### `app/services/scoring_service.py`

This is the **orchestrator**:

* For each initiative:

  * Decide which **framework(s)** to apply:

    * Based on a field like `initiative.preferred_framework` or global defaults.
  * If framework needs LLM help:

    * Call functions in `llm/scoring_assistant.py` to:

      * Suggest RICE inputs,
      * Suggest math model formula & assumptions,
      * Suggest parameter values.
  * Store suggestions in `InitiativeScore` / `InitiativeMathModel` as `suggested_by_llm=True`.
  * If human has already approved:

    * Use approved values.
  * Produce a canonical `overall_score` used later by `optimization_service`.

This keeps **optimization** totally agnostic:

* It just sees numeric scores, not how they were generated.

#### `app/llm/scoring_assistant.py`

Here we put LLM helpers like:

* `suggest_RICE_inputs(initiative_context) -> dict`
* `suggest_math_model(initiative_context) -> {formula_text, parameters, assumptions}`
* `suggest_math_parameters(initiative, model) -> dict`
* `summarize_scoring_rationale(...) -> str`

And prompts for those live in `prompts.py`.

#### `app/jobs/scoring_job.py`

Scheduled job like:

* “Re-score all initiatives that:

  * are approved-in-principle,
  * have changed significantly,
  * or whose assumptions changed.”

Then persists updated scores.

---

## 2. How this ties into Sheets & human review

On the **Sheets side**, for each initiative in the central backlog / roadmap sheet, we can expose:

* Which frameworks were used: `scoring_framework = "RICE+MATH_MODEL"`.
* Key inputs:

  * RICE: Reach, Impact, Confidence, Effort.
  * Math model: high-level formula name or ID.
* Scores:

  * `value_score`, `effort_score`, `overall_score`.
* Flags:

  * `llm_suggested = TRUE/FALSE`
  * `score_approved = TRUE/FALSE`

Product managers can have a **review sheet** where they:

* See LLM-suggested inputs/assumptions,
* Adjust them,
* Tick “approved” to lock them in.

The backend then:

* Treats approved values as canonical,
* Uses those for optimization,
* Keeps LLM suggestions in history if you want.

---

1. **Scoring frameworks interface + factory + orchestrator**

## 1. Scoring frameworks: interface + factory + orchestrator

### 1.1. Interface / protocol

**File:** `app/services/scoring/base_framework.py`

```python
from typing import Protocol, Any, Dict, Optional
from app.db.models.initiative import Initiative


class ScoreResult:
    """
    Canonical result type from any framework.
    Everything else is framework-specific detail.
    """
    def __init__(
        self,
        value_score: Optional[float],
        effort_score: Optional[float],
        overall_score: Optional[float],
        raw_inputs: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.value_score = value_score
        self.effort_score = effort_score
        self.overall_score = overall_score
        self.raw_inputs = raw_inputs or {}


class ScoringFramework(Protocol):
    """
    Interface that every scoring framework must implement.
    """

    name: str  # e.g. "RICE", "MATH_MODEL", "CUSTOM_X"

    def score(self, initiative: Initiative) -> ScoreResult:
        """
        Compute scores for a given initiative based on its fields
        and possibly related entities (math models, etc.).

        Should NOT commit to DB; just compute values.
        """
        ...
```

---

### 1.2. Example framework: RICE

**File:** `app/services/scoring/rice_framework.py`

```python
from typing import Optional, Dict, Any

from app.db.models.initiative import Initiative
from app.services.scoring.base_framework import ScoringFramework, ScoreResult


class RiceFramework(ScoringFramework):
    """
    Classic RICE: (Reach * Impact * Confidence) / Effort

    For simplicity, assume the initiative has some RICE-specific fields
    stored in linked_objectives or in a separate JSON config later.
    Here we just fake them or derive them from existing impact fields.
    """

    name = "RICE"

    def score(self, initiative: Initiative) -> ScoreResult:
        # In a real impl, you'd fetch these from dedicated fields or a JSON blob.
        # For now, we'll derive simple placeholders:
        # - reach: number of users/customers affected (normalized)
        # - impact: use impact_expected
        # - confidence: from risk_level (low risk -> higher confidence)
        # - effort: from effort_engineering_days / tshirt size

        reach = self._estimate_reach(initiative)
        impact = initiative.impact_expected or 0.0
        confidence = self._estimate_confidence(initiative)
        effort = self._estimate_effort(initiative)

        if effort <= 0:
            overall = None
        else:
            overall = (reach * impact * confidence) / effort

        raw_inputs: Dict[str, Any] = {
            "reach": reach,
            "impact": impact,
            "confidence": confidence,
            "effort": effort,
        }

        # For RICE, you can treat `value_score` as reach*impact*confidence
        value_score = reach * impact * confidence if impact else None
        effort_score = effort

        return ScoreResult(
            value_score=value_score,
            effort_score=effort_score,
            overall_score=overall,
            raw_inputs=raw_inputs,
        )

    def _estimate_reach(self, initiative: Initiative) -> float:
        # Placeholder – later you can pull from proper fields or LLM suggestions
        # For now, treat all initiatives as reach 1.0
        return 1.0

    def _estimate_confidence(self, initiative: Initiative) -> float:
        # Basic mapping from risk_level to confidence
        mapping = {
            "Low": 0.9,
            "Medium": 0.7,
            "High": 0.5,
        }
        return mapping.get(initiative.risk_level or "Medium", 0.7)

    def _estimate_effort(self, initiative: Initiative) -> float:
        if initiative.effort_engineering_days:
            return max(initiative.effort_engineering_days, 0.1)
        # Fallback from T-shirt size
        tshirt_map = {
            "XS": 1.0,
            "S": 3.0,
            "M": 8.0,
            "L": 13.0,
            "XL": 21.0,
        }
        return tshirt_map.get(initiative.effort_tshirt_size or "M", 8.0)
```

---

### 1.3. Example framework: Math model wrapper

**File:** `app/services/scoring/math_model_framework.py`

```python
from typing import Optional, Dict, Any

from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeMathModel
from app.services.scoring.base_framework import ScoringFramework, ScoreResult


class MathModelFramework(ScoringFramework):
    """
    Uses InitiativeMathModel to compute a numeric value_score.
    Effort is still taken from the initiative (e.g. engineering_days).
    """

    name = "MATH_MODEL"

    def score(self, initiative: Initiative) -> ScoreResult:
        math_model: Optional[InitiativeMathModel] = initiative.math_model
        if not math_model:
            # No model: cannot compute meaningful value
            return ScoreResult(value_score=None, effort_score=None, overall_score=None)

        # Here you'd parse math_model.formula_text and eval it safely
        # against parameters_json; for now we just illustrate:
        params: Dict[str, Any] = math_model.parameters_json or {}
        value = self._evaluate_model(math_model.formula_text, params)
        effort = initiative.effort_engineering_days or None

        raw_inputs: Dict[str, Any] = {
            "formula": math_model.formula_text,
            "parameters": params,
        }

        overall = None
        if value is not None and effort and effort > 0:
            overall = value / effort  # simple ROI-style ratio

        return ScoreResult(
            value_score=value,
            effort_score=effort,
            overall_score=overall,
            raw_inputs=raw_inputs,
        )

    def _evaluate_model(self, formula_text: str, params: Dict[str, Any]) -> Optional[float]:
        """
        Placeholder: later use a safe expression engine (e.g. asteval, sympy, custom DSL).
        """
        # For now, just pretend `value` is in params.
        return params.get("value")
```

(Real implementation later; this is just the plug-in shape.)

---

### 1.4. Framework registry / factory

**File:** `app/services/scoring/factory.py`

```python
from typing import Dict

from app.services.scoring.base_framework import ScoringFramework
from app.services.scoring.rice_framework import RiceFramework
from app.services.scoring.math_model_framework import MathModelFramework


class ScoringFrameworkFactory:
    """
    Simple registry for available frameworks.
    """

    def __init__(self) -> None:
        self._frameworks: Dict[str, ScoringFramework] = {}
        self.register(RiceFramework())
        self.register(MathModelFramework())
        # later: register more (MoSCoW, WSJF, custom…)

    def register(self, framework: ScoringFramework) -> None:
        self._frameworks[framework.name] = framework

    def get(self, name: str) -> ScoringFramework:
        if name not in self._frameworks:
            raise ValueError(f"Unknown scoring framework: {name}")
        return self._frameworks[name]

    def list_names(self) -> list[str]:
        return list(self._frameworks.keys())


framework_factory = ScoringFrameworkFactory()
```

Later you can make this configurable (DB-driven frameworks, etc.), but this is good for now.

---

### 1.5. Scoring orchestrator service

**File:** `app/services/scoring_service.py`

```python
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeScore
from app.services.scoring.factory import framework_factory
from app.services.scoring.base_framework import ScoreResult


class ScoringService:
    """
    Orchestrates how scoring frameworks are applied to initiatives.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def score_initiative(self, initiative: Initiative) -> Initiative:
        """
        Compute scores for a single initiative using the active framework
        and update the initiative (and optional scoring history) in DB.
        """
        framework_name = initiative.active_scoring_framework or "RICE"
        framework = framework_factory.get(framework_name)

        result: ScoreResult = framework.score(initiative)

        # Update initiative's canonical scoring fields
        initiative.value_score = result.value_score
        initiative.effort_score = result.effort_score
        initiative.overall_score = result.overall_score

        # For now assume LLM may have been used outside this function;
        # here we don't toggle score_llm_suggested unless you pass a flag.
        # initiative.score_llm_suggested = ...

        self.db.add(initiative)

        # Optional: append to scoring history
        score_history = InitiativeScore(
            initiative_id=initiative.id,
            framework_name=framework_name,
            value_score=result.value_score,
            effort_score=result.effort_score,
            overall_score=result.overall_score,
            inputs_json=result.raw_inputs,
            # llm_suggested=initiative.score_llm_suggested,
            approved_by_user=initiative.score_approved_by_user,
        )
        self.db.add(score_history)

        self.db.commit()
        self.db.refresh(initiative)
        return initiative

    def score_all_approved(self) -> None:
        """
        Example batch job: score all initiatives with status 'approved_in_principle'.
        """
        initiatives = (
            self.db.query(Initiative)
            .filter(Initiative.status == "approved_in_principle")
            .all()
        )
        for init in initiatives:
            self.score_initiative(init)
```

This is the plug: optimization later just reads `value_score`, `effort_score`, `overall_score` from `Initiative` (or from `RoadmapEntry.value_score_used` if you snapshot them per roadmap).

---


Great question, and exactly the right time to ask it.

Let me walk you through:

1. A **concrete end-to-end example** for the math model.
2. Then compare **Sheet-driven vs Backend-driven vs Hybrid**.
3. And show how the same pattern applies to **RICE & other frameworks**.

---

## 1. Concrete example: custom math model for one initiative

Say we have an initiative:

> “Improve checkout UX to increase conversion on UK mobile traffic.”

A PM wants to **quantify value** using a custom model like:

> **Value (£) = uplift_in_conv × baseline_conv × monthly_sessions × AOV × margin% × 12 months − infra_cost**

### Step 1 – On the Google Sheet (central backlog)

On the **central backlog sheet**, for this initiative, we’d have extra columns for **parameters** and **result**.

Something like:

| Column                        | Example value               | Who edits         |
| ----------------------------- | --------------------------- | ----------------- |
| `use_math_model`              | ✅                           | Product           |
| `math_param_baseline_conv`    | `0.04` (4%)                 | Product/Analytics |
| `math_param_uplift_conv`      | `0.02` (2% uplift)          | Product/Analytics |
| `math_param_monthly_sessions` | `500000`                    | Product/Analytics |
| `math_param_aov`              | `45`                        | Product/Finance   |
| `math_param_margin`           | `0.35`                      | Product/Finance   |
| `math_param_horizon_months`   | `12`                        | Product           |
| `math_param_infra_cost`       | `20000`                     | Eng/Infra         |
| `value_score`                 | `something`                 | Auto + override   |
| `overall_score`               | `something`                 | Auto + override   |
| `llm_notes`                   | text explaining assumptions | Auto + Product    |

The **formula itself** doesn’t have to be in the Sheet. It can be:

* Stored once in the backend (`formula_text`), and
* Optionally shown in a read-only column like `math_model_human_readable` (“Value = uplift × base × sessions × AOV × margin × months − infra”).

The PM’s job on the sheet is to **fill/adjust parameters**, not maintain fragile formulas.

### Step 2 – On the backend (DB + math model entity)

When `use_math_model = TRUE`, your backend:

1. Reads parameter values from those `math_param_*` columns.

2. Maps them to `parameters_json` for this initiative’s `InitiativeMathModel`:

   ```json
   {
     "baseline_conv": 0.04,
     "uplift_conv": 0.02,
     "monthly_sessions": 500000,
     "aov": 45,
     "margin": 0.35,
     "horizon_months": 12,
     "infra_cost": 20000
   }
   ```

3. Stores/updates an `InitiativeMathModel` row:

   * `formula_text`: `"value = baseline_conv * uplift_conv * monthly_sessions * aov * margin * horizon_months - infra_cost"`
   * `parameters_json`: as above.
   * `assumptions_text`: maybe written or suggested by LLM (“assumes uplift is sustained for 12 months, margin constant, etc.”).
   * `suggested_by_llm` / `approved_by_user`.

4. The **MathModelFramework** (backend) then evaluates this:

   * Computes a **value in £** → `value_score`.
   * Uses `effort_engineering_days` to get `effort_score`.
   * Computes `overall_score = value_score / effort_score` or similar.
   * Writes those into the Initiative record:

     * `value_score`, `effort_score`, `overall_score`.

5. Those scores are then **written back** to the central sheet in their columns.

Product can still **override** `value_score` / `overall_score` directly if they really disagree.

### Step 3 – Per-initiative uniqueness

For another initiative, the PM might choose a completely different model, e.g.:

> **Value = reduction_in_ticket_volume_per_month × cost_per_ticket × horizon_months**

Parameters & formula for that initiative are different:

* Different set of `math_param_*` columns filled.
* Different `formula_text` & `parameters_json` in `InitiativeMathModel`.
* The Sheet stays the *view* and input for parameters; backend remains the **calculator** and single source of truth.

---


### Hybrid Way of Applying Scoring Frameworks

* **Parameters** are editable on the Sheet (central backlog).
* **Formulas** live in the backend (`InitiativeMathModel.formula_text`), but:

* PM can describe the model in natural language (or structured text) on a sheet:

    * “Multiply these parameters like X…”

    * Or “LLM, please propose a formula for this initiative”.

* Backend + LLM:

    * Turn that into a safe formula → InitiativeMathModel.formula_text.

    * Define & store parameters → parameters_json.

    * Generate hypotheses & notes.

    * Recalculate scores when parameters or formulas change.

    * Store assumptions & model versions centrally in DB.

Concretely:

* Sheet:

  * Parameter columns (`math_param_*`) – editable by product.
  * A `proposed_math_formula` / `math_model_description` column – PM can describe the model in natural language.
* Backend:

  * LLM takes `proposed_math_formula` + parameters → generates:

    * `formula_text` in a safe expression language,
    * initial `parameters_json` structure,
    * assumptions.
  * You store that in `InitiativeMathModel`.
  * MathModelFramework computes `value_score` etc.
* Sheet:

  * Shows `value_score`, `overall_score`, `llm_notes`.
  * PM can still tweak parameters if needed and trigger a recalculation.

This gives:

* PM creativity & flexibility.
* Backend robustness & long-term power (Monte Carlo, histories, audits).

---

## 3. How this pattern applies to RICE & other frameworks

### RICE

We treat RICE exactly the same way conceptually:

* **Sheet holds inputs**:

  | Column            | Example | Who edits   |
  | ----------------- | ------- | ----------- |
  | `rice_reach`      | 10000   | Product/PM  |
  | `rice_impact`     | 3       | Product/PM  |
  | `rice_confidence` | 0.7     | Product/PM  |
  | `rice_effort`     | 20      | Eng/Product |

* Backend:

  * `RiceFramework.score()` reads those (either from dedicated columns or via JSON).
  * Computes:

    * `value_score = reach * impact * confidence`
    * `effort_score = effort`
    * `overall_score = (reach * impact * confidence) / effort`
  * Writes them into `Initiative.value_score`, `effort_score`, `overall_score`.
  * Optionally writes a RICE-specific row into `InitiativeScore` history.

* Sheet shows scores; PM can override them manually if needed.

### MoSCoW, math model, custom frameworks

* All follow the same pattern:

  * **Inputs**: live in sheet columns (per framework).
  * **Formula/logic**: lives in backend framework implementation.
  * **Outputs** (`value_score`, `effort_score`, `overall_score`): show in sheet & DB.

The **factory** (`ScoringFrameworkFactory`) then just picks the right implementation according to `active_scoring_framework` (`"RICE"`, `"MATH_MODEL"`, `"CUSTOM_WSJF"`, etc.).

---

## My recommendation

Given:

* We want many different, per-initiative custom mathematical models.
* We want full-blown portfolio optimization, Monte Carlo, and traceability.
* We also want PMs to have freedom and LLM to assist.

We’d go with the **Hybrid, backend-centric** approach:

1. **Sheets**:

   * Input parameters per initiative (`math_param_*`, RICE inputs, etc.).
   * High-level descriptions of models (free text).
   * View & override of final scores (`value_score`, `overall_score`).

2. **Backend**:

   * Owns formula definitions (`InitiativeMathModel.formula_text`) and evaluation.
   * Uses LLM to:

     * Suggest formulas,
     * Suggest parameters,
     * Generate hypotheses & notes.
   * Recalculates scores whenever parameters or formulas change.
   * Stores assumptions & model versions centrally.




#######################################################


Yeah, we’re totally aligned on the *logic* and responsibilities. 💯
Now we’re in “how do we not blow up the sheet” territory.

Let me answer in two parts:

1. Are we conceptually aligned?
2. How to design the Sheets so we **don’t** end up with 10,000 columns.

---

## 1. Alignment check ✅

We agree:

* PM can **describe** the model in natural language (or structured text) on a sheet:

  * “Multiply these parameters like X…”
  * Or “LLM, please propose a formula for this initiative”.

* Backend + LLM:

  * Turn that into a **safe formula** → `InitiativeMathModel.formula_text`.
  * Define & store **parameters** → `parameters_json`.
  * Generate **hypotheses & notes**.
  * Recalculate **scores** when parameters or formulas change.
  * Store **assumptions & model versions** centrally in DB.

So far we’re on the exact same page. ✅

---

## 2. How to avoid column explosion in Sheets

* One MathModels sheet for formula-based frameworks (mainly MATH_MODEL, maybe later other custom formula frameworks).

* One Params sheet that supports all frameworks, with a framework column.

### 🔁 Core idea: keep central backlog clean, add *normalized* scoring sheets

Instead of “one initiative spreads across many custom columns”, think **one initiative spreads across multiple rows** in a separate scoring sheet.

#### Central backlog sheet

Keep this **clean**:

* One row per initiative.
* No per-parameter columns.
* Just high-level stuff + scores:

  * `initiative_key`
  * problem, outcome, etc.
  * `use_math_model`, `active_scoring_framework`
  * `value_score`, `effort_score`, `overall_score`
  * `llm_summary`, `hypothesis`, `llm_notes`, `strategic_priority_coefficient`, etc.

---

### Scoring Sheet 1: `MathModels`

**One row per initiative that uses a math model.**

Columns like:

| Column                        | Example                                                                                |
| ----------------------------- | -------------------------------------------------------------------------------------- |
| `initiative_key`              | `INIT-000123`                                                                          |
| `model_name`                  | `CheckoutConvValue2025`                                                                |
| `model_description_free_text` | “Multiply uplift × base conv × sessions × AOV × …”                                     |
| `framework`                   | `MATH_MODEL`                                                                           |
| `llm_suggested_formula_text`  | `value = uplift_conv * baseline_conv * sessions * aov * margin * horizon - infra_cost` |
| `formula_text_approved`       | ✅ or empty                                                                             |
| `assumptions_text`            | “Assumes uplift holds 12 months, margin stable…”                                       |
| `llm_notes`                   | Any extra hints / explanation                                                          |

**Flow on this sheet:**

1. PM filters by `initiative_key`.
2. They write in `model_description_free_text` (or leave blank and ask LLM to propose).
3. Backend + LLM:

   * Reads `model_description_free_text` + initiative context.
   * Writes `llm_suggested_formula_text` and `assumptions_text`.
4. PM reviews:

   * If happy, copies to a final `formula_text` cell or flips `formula_text_approved = TRUE`.
5. Backend uses approved formula for evaluation (`InitiativeMathModel.formula_text`).

This way:

* You don’t add any new columns *per initiative*,
* You just add rows per initiative that uses a math model.

---

### Scoring Sheet 2: `Params`

**One row per (initiative, parameter). Normalized.**

Columns:

| Column            | Example           | Meaning                                  |
| ----------------- | ----------------- | ---------------------------------------- |
| `initiative_key`  | `INIT-000123`     | Which initiative this row belongs to     |
| `framework`       | `MATH_MODEL`      | `MATH_MODEL`, `RICE`, `WSJF`, `CUSTOM_X` |
| `param_name`      | `baseline_conv`   | Internal parameter identifier            |
| `param_display`   | `Baseline Conv %` | Human-friendly label                     |
| `value`           | `0.04`            | Actual chosen value                      |
| `unit`            | `%`               | Optional unit                            |
| `min`             | `0.02`            | Optional lower bound                     |
| `max`             | `0.06`            | Optional upper bound                     |
| `source`          | `Analytics`       | PM / Analytics / Finance / LLM etc.      |
| `last_updated_by` | `me@company.com`  | Who last changed it                      |
| `approved`        | `TRUE/FALSE`      | Whether this parameter is approved       |


*** Same initiative might have multiple rows *** and
*** For one initiative you might have ***

RICE rows:

INIT-000123 | RICE       | reach        | ... | 100000
INIT-000123 | RICE       | impact       | ... | 3
INIT-000123 | RICE       | confidence   | ... | 0.7
INIT-000123 | RICE       | effort       | ... | 20


Math model rows:

INIT-000123 | MATH_MODEL | baseline_conv    | ... | 0.04
INIT-000123 | MATH_MODEL | uplift_conv      | ... | 0.02
INIT-000123 | MATH_MODEL | monthly_sessions | ... | 500000
INIT-000123 | MATH_MODEL | aov              | ... | 45
INIT-000123 | MATH_MODEL | margin           | ... | 0.35
INIT-000123 | MATH_MODEL | infra_cost       | ... | 20000

**This is the flow:** 

* PM defines / approves a formula in MathModels (or picks a framework like RICE, MATH_MODEL, WSJF).

* Backend / LLM:

    * Backend automatically seeds parameter rows based on formula or framework.
    * Parses formula (or uses known template for RICE, WSJF).

    * Identifies the parameter names used in the formula.

    * For each parameter, creates a row in Params with:

        * initiative_key

        * framework

        * param_name

        * param_display (LLM can suggest a nice label)

        * unit (maybe suggested)

        * min/max (optional suggestions)

        * source = "LLM" or "Template"

        * approved = FALSE

* PM (and Analytics/Finance/Eng) go to Params sheet:

    * Filter by initiative_key & framework.

    * Fill/adjust the value, tweak units, maybe edit param names.

    * Flip approved = TRUE when they’re happy.

    * PMs are allowed to add extra parameters manually in Params sheet if they realize they need more.

    * Backend:

        * Treats auto-seeded ones as “primary”.

        * Treats any extra rows as “additional inputs” (which can also be referenced in formulas if you let them).

Backend then only uses parameters where:

* approved = TRUE, or

* value is not null (configurable rule).

### Where does RICE (and other frameworks) fit in?

#### Treat RICE like just another parameterized framework

Use the same `MathParams`-style sheet, but add a `framework` column:

| Column           | Example       |
| ---------------- | ------------- |
| `framework`      | `RICE`        |
| `initiative_key` | `INIT-000123` |
| `param_name`     | `reach`       |
| `value`          | `10000`       |

So then you could eventually unify all frameworks (RICE, WSJF, math model, etc.) into a single **param table**.


*** So, in summary: *** 

1. **One `MathModels` sheet** (normalized, one row per initiative per formula-based framework).

2. **One `Params` sheet** (normalized, one row per initiative–framework–parameter).

3. **Backend-driven parameter creation pipeline**:

   * For **known frameworks** (RICE, WSJF, etc.):

     * Framework definition already knows required parameters → backend seeds them automatically into `Params` sheet as soon as `active_scoring_framework` is set.
   * For **math models**:

     * Once formula is approved in `MathModels`, backend parses it, finds identifiers, seeds parameter rows into `Params`.
   * LLM can help:

     * Suggest `param_display`, `unit`, `min`, `max`, `source`, etc.

4. **PM / stakeholders only review & edit**:

   * They work in `Params` sheet:

     * Fill `value`.
     * Adjust labels/units if needed.
     * Mark `approved = TRUE`.
    
   * PMs are allowed to add extra parameters manually in Params sheet if they realize they need more. 

   * Backend periodically recalculates scores for all initiatives with `use_math_model = TRUE` or where there’s a complete parameter set.

5. **Central backlog stays clean**:

   * It only sees **scores and meta**, not parameter explosion.
   * `value_score`, `effort_score`, `overall_score`, `hypothesis`, `llm_notes`, etc.

---

### So how does the full hybrid flow look like?

**Workflow for math model framework, end-to-end:**

1. PM adds/updates an initiative in **central backlog**.
2. PM decides this initiative needs a custom math model:

   * Sets `use_math_model = TRUE` in central.
3. In **MathModels** sheet:

   * PM writes `model_description_free_text` for that initiative.
   * Or leaves it blank and adds “LLM please suggest formula” in a “prompt” column.
4. Backend job:

   * Reads MathModels sheet rows where `formula_text_approved` is not TRUE.
   * Calls LLM with:

     * Initiative context,
     * `model_description_free_text` (if any),
     * Maybe some default patterns.
   * Writes back:

     * `llm_suggested_formula_text`,
     * `assumptions_text`,
     * maybe `llm_notes`.
5. PM reviews & approves formula on **MathModels** sheet.
6. In **Params** sheet:
    * PM (and Analytics/Finance/Eng) go to Params sheet:

        * Filter by initiative_key & framework.

        * Fill/adjust the value, tweak units, maybe edit param names.

        * Flip approved = TRUE when they’re happy.

        * PMs are allowed to add extra parameters manually in Params sheet if they realize they need more.

        * Treats auto-seeded ones as “primary”.

        * Treats any extra rows as “additional inputs” (which can also be referenced in formulas if you let them).

    * Backend:
        * For **known frameworks** (RICE, WSJF, etc.):

            * Framework definition already knows required parameters → backend seeds them automatically into `Params` sheet as soon as `active_scoring_framework` is set.

        * For **math models**:

            * Once formula is approved in `MathModels`, backend parses it, finds identifiers, seeds parameter rows into `Params`.

        * LLM can help:

            * Suggest `param_display`, `unit`, `min`, `max`, `source`, etc.

        
    
7. Backend job:
    * For **known frameworks** (RICE, WSJF, etc.):

            * Framework definition already knows required parameters → backend seeds them automatically into `Params` sheet as soon as `active_scoring_framework` is set.

        * For **math models**:

            * Once formula is approved in `MathModels`, backend parses it, finds identifiers, seeds parameter rows into `Params`.

        * LLM can help:

            * Suggest `param_display`, `unit`, `min`, `max`, `source`, etc.

   * Builds/updates `InitiativeMathModel` & `parameters_json`.
   * Evaluates formula → gets `value_score`.
   * Combines with effort → `overall_score`.
   * Writes scores back into **central backlog** (`value_score`, `overall_score`, etc.).

8. Optimizer & roadmap logic use those scores.

**This way:**
* Nothing explodes.
* Sheets stay usable.
* Backend stays in control.
* PMs have full freedom to define models & parameters without wrecking the central backlog.

---

# 3.Let’s now lock in the **final schemas** for:

* `MathModels` sheet
* `Params` sheet
---

## 1. `MathModels` sheet schema

**(One row per initiative per formula-based framework, e.g. `MATH_MODEL`)**

This sheet captures:

* Which initiative + framework
* PM’s free-text description
* LLM-suggested formula
* Final approved formula
* Assumptions and notes

### Columns for `MathModels`

| Column                        | Type        | Example                                                                                       | Who edits / ownership                                  | Notes                                                                                                                   |
| ----------------------------- | ----------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `initiative_key`              | string      | `INIT-000123`                                                                                 | **Backend seeds** from central backlog; PM read-only   | Join key to Initiative; validated against DB/central sheet                                                              |
| `framework`                   | string enum | `MATH_MODEL`                                                                                  | **Backend seeds or PM selects from dropdown**          | For now mostly `MATH_MODEL`; later could support others (e.g. `CUSTOM_FORMULA_X`)                                       |
| `model_name`                  | string      | `CheckoutConvValue2025`                                                                       | **PM/Product edits**                                   | Optional friendly label for this model instance                                                                         |
| `model_description_free_text` | long text   | “Multiply uplift × base conv × sessions × AOV…”                                               | **PM/Product edits**                                   | Natural-language description of how value should be modeled; can be empty if PM wants LLM to propose from scratch       |
| `model_prompt_to_llm`         | long text   | “LLM, please suggest a model using uplift, traffic, AOV…”                                     | **PM/Product edits**                                   | Optional explicit prompt/instructions for LLM; if empty, backend builds a default from initiative context + description |
| `llm_suggested_formula_text`  | long text   | `value = uplift_conv * baseline_conv * sessions * aov * margin * horizon_months - infra_cost` | **Backend writes**; PM read-only                       | Raw suggested formula in safe DSL or expression syntax; *not* used until approved                                       |
| `assumptions_text`            | long text   | “Assumes uplift holds for 12 months, margin stable…”                                          | **Backend (LLM) writes first**, **PM can edit/extend** | Human-readable assumptions behind the model                                                                             |
| `llm_notes`                   | long text   | “Main driver is uplift × traffic; infra_cost is minor…”                                       | **Backend (LLM) writes first**, **PM can edit/append** | Any explanation, caveats, or interpretation from LLM                                                                    |
| `formula_text_final`          | long text   | `value = uplift_conv * baseline_conv * sessions * aov * margin * horizon_months - infra_cost` | **Product/PM edits** (may copy from suggested)         | The **approved** formula to be stored in `InitiativeMathModel.formula_text` and used for evaluation                     |
| `formula_text_approved`       | boolean     | `TRUE` / `FALSE`                                                                              | **Product/PM toggles**                                 | When `TRUE`, backend treats `formula_text_final` as canonical and seeds parameters, evaluates model, etc.               |
| `version`                     | integer     | `1`                                                                                           | **Backend increments**                                 | Simple model version; incremented when formula changes (optional but nice)                                              |
| `last_updated_by`             | string      | `me@company.com`                                                                              | **Backend updates** from acting user context           | Who last touched formula/description (optional)                                                                         |
| `last_updated_at`             | datetime    | `2025-01-10T14:32`                                                                            | **Backend updates**                                    | Timestamp of last change (optional, but useful)                                                                         |

**Backend mapping:**

* Each row in `MathModels` with `formula_text_approved = TRUE` →
  one `InitiativeMathModel` row in DB with:

  * `initiative_id` (joined via `initiative_key`),
  * `formula_text` ← `formula_text_final`,
  * `parameters_json` (built later from `Params`),
  * `assumptions_text` ← `assumptions_text`,
  * `suggested_by_llm` (bool, based on origin),
  * `approved_by_user` = `formula_text_approved`.

---

## 2. `Params` sheet schema

**(One row per initiative–framework–parameter)**

This sheet is the **single unified place** for all framework parameters:

* Math model params
* RICE params
* WSJF params
* Any future custom frameworks

### Columns for `Params`

| Column            | Type        | Example                                                                     | Who edits / ownership                                                                               | Notes                                                                                                    |
| ----------------- | ----------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `initiative_key`  | string      | `INIT-000123`                                                               | **Backend seeds**, PM read-only (for integrity)                                                     | Foreign key to Initiative; validate against central backlog                                              |
| `framework`       | string enum | `MATH_MODEL`, `RICE`, `WSJF`                                                | **Backend seeds** for auto-created params; **PM can select** if adding a new param row manually     | Identifies which scoring framework this parameter belongs to                                             |
| `param_name`      | string      | `baseline_conv`, `reach`, `impact`                                          | **Backend seeds** when generating params from formula/framework; **PM may adjust in special cases** | Internal identifier used by backend & formula; should be stable and simple                               |
| `param_display`   | string      | `Baseline Conversion Rate`                                                  | **Backend (LLM) suggests** first; **PM/Analytics can refine**                                       | Human-friendly label shown in sheets/UX                                                                  |
| `description`     | long text   | “Baseline conversion rate of current checkout funnel for UK mobile”         | **Backend (LLM) suggests** or **PM fills**                                                          | Optional explanatory text per parameter                                                                  |
| `value`           | number/text | `0.04`, `100000`                                                            | **PM/Analytics/Finance/Eng edit**                                                                   | Actual numeric (or sometimes categorical) value used in calculation; main thing humans fill              |
| `unit`            | string      | `%`, `£`, `sessions`, `days`                                                | **Backend (LLM) suggests**; **PM can edit**                                                         | Unit for value; used for display & sanity checks                                                         |
| `min`             | number      | `0.02`                                                                      | **Backend (LLM/analytics) suggests**, **PM can edit**                                               | Optional: lower bound for uncertainty / Monte Carlo                                                      |
| `max`             | number      | `0.06`                                                                      | **Backend (LLM/analytics) suggests**, **PM can edit**                                               | Optional: upper bound                                                                                    |
| `source`          | string enum | `PM`, `Analytics`, `Finance`, `Eng`, `LLM`                                  | **Backend seeds initially**, **PM can adjust**                                                      | Who is considered the owner/source of this parameter                                                     |
| `approved`        | boolean     | `TRUE` / `FALSE`                                                            | **PM / relevant owner toggles**                                                                     | Only `approved = TRUE` parameters (or ones with non-null `value`, depending on rule) are used in scoring |
| `is_auto_seeded`  | boolean     | `TRUE` / `FALSE`                                                            | **Backend sets**                                                                                    | `TRUE` if backend created this row from a framework or formula; `FALSE` if manually added by PM          |
| `last_updated_by` | string      | `me@company.com`                                                            | **Backend updates** from user context                                                               | Who last changed `value` or related fields                                                               |
| `last_updated_at` | datetime    | `2025-01-10T15:12`                                                          | **Backend updates**                                                                                 | For auditing & debugging                                                                                 |
| `notes`           | long text   | “Using latest Q4 traffic numbers; value to be revisited after new campaign” | **PM / owners edit**                                                                                | Free-form comments re parameter choice, caveats, etc.                                                    |

### How backend uses `Params`

For any initiative + framework (e.g. `INIT-000123` + `MATH_MODEL`):

1. Fetch all rows with:

   * `initiative_key = 'INIT-000123'`
   * `framework = 'MATH_MODEL'`
   * `approved = TRUE` (or non-null `value` if you prefer).

2. Turn them into a `parameters_json` object like:

   ```json
   {
     "baseline_conv": {"value": 0.04, "unit": "%", "min": 0.02, "max": 0.06},
     "uplift_conv": {"value": 0.02, "unit": "%"},
     "monthly_sessions": {"value": 500000, "unit": "sessions"},
     ...
   }
   ```

3. Store that in `InitiativeMathModel.parameters_json`.

4. Pass it to `MathModelFramework` for evaluation.

5. Write resulting `value_score` / `overall_score` into central backlog.

---

## 3. Where frameworks like RICE fit in

For **RICE**, you simply use `framework = 'RICE'` and fixed `param_name`s:

Example rows in `Params`:

```text
initiative_key | framework | param_name  | value   | unit   | source    | approved | is_auto_seeded
---------------+-----------+------------+---------+--------+-----------+----------+----------------
INIT-000123    | RICE      | reach      | 100000  | users  | PM        | TRUE     | TRUE
INIT-000123    | RICE      | impact     | 3       | score  | PM        | TRUE     | TRUE
INIT-000123    | RICE      | confidence | 0.7     | ratio  | PM        | TRUE     | TRUE
INIT-000123    | RICE      | effort     | 20      | days   | Eng       | TRUE     | TRUE
```

* Backend knows “for RICE we need `reach`, `impact`, `confidence`, `effort`”.
* It auto-seeds these rows when `active_scoring_framework = 'RICE'`.
* PMs then fill in `value` / adjust.
* `RiceFramework` reads those params and computes scores.

Same pattern for **WSJF** or any other named framework.

---

