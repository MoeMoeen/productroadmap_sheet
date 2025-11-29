
---

# 🎯 **FLOW 2 — GAMEPLAY & ROADMAP**

Flow 2 is where you transform raw initiative data into **actionable prioritization signals** using scoring frameworks.

Think of Flow 1 as *ETL*
and Flow 2 as *Analytics + AI + Decision Intelligence.*

Flow 2 transforms:

> **Intake Rows → DB Initiatives → Scored Priorities → Backlog Sheet**

Let's break down the entire scope.

---

# 🧩 OVERVIEW — What Flow 2 Must Do

Flow 2 consists of **five logical layers**, each of which we will design & implement in small steps:

---

## **Layer 1 — Framework Engine (RICE / WSJF / Custom)**

A pluggable, clean scoring engine that can compute:

* **RICE**

  * Reach
  * Impact
  * Confidence
  * Effort

* **WSJF**

  * User/Business value
  * Time criticality
  * Risk reduction / Opportunity enablement
  * Job size

* **Custom frameworks**

  * Math models
  * AI-generated scoring
  * Any future formulas

### Deliverable:

A **framework registry** like:

```python
SCORING_FRAMEWORKS = {
    "RICE": RiceScoringEngine(),
    "WSJF": WsjfScoringEngine(),
    "CUSTOM": CustomFrameworkEngine(),
}
```

Where each engine has:

```python
compute_scores(initiative: Initiative) -> ScoreResult
```

---

## **Layer 2 — Domain Models & Storage**

We already have:

* `Initiative`
* `InitiativeMathModel`
* `InitiativeScore`

Flow 2 will use these to store:

* scoring metadata
* detailed scoring inputs
* scoring outputs
* scoring run-by-run history
* LLM-generated values

### Deliverable:

Extend or finalize:

* `InitiativeScore` for historical scoring
* Optional `Initiative.current_scores` cached on Initiative
* Optional `Initiative.active_scoring_framework` field updates

---

## **Layer 3 — Scoring Service (Core Logic)**

This is the “brains” orchestrating scoring:

```python
class ScoringService:
    def compute_for_initiative(self, initiative: Initiative, framework: str) -> InitiativeScore
```

Responsibilities:

1. Fetch initiative data

2. Normalize missing or raw fields

3. Delegate to appropriate scoring engine

4. Store `InitiativeScore` in DB

5. Update initiative fields, e.g.:

   * `value_score`
   * `effort_score`
   * `overall_score`
   * `active_scoring_framework`

6. Handle multi-framework runs

7. Idempotent re-scoring

---

## **Layer 4 — CLI + Jobs (Flow Automation)**

Flow 2’s job runner will do:

```text
For each initiative:
    1. Choose framework (default: RICE)
    2. Compute scores
    3. Save results
    4. Update initiative
```

### Deliverables:

* `app/jobs/scoring_job.py`
* CLI:

```bash
python -m scoring_cli --framework RICE
python -m scoring_cli --all
```

* Logging and batched DB commits

---

## **Layer 5 — Backlog Sheet Sync (Flow 1 + Flow 2 Combined)**

Flow 1 already rebuilds the central backlog sheet.

Flow 2 must plug into that:

* Write

  * `Value Score`
  * `Effort Score`
  * `Overall Score`
  * `Active Scoring Framework`
  * `Use Math Model`
* Pull scores from DB each time backlog sheet is regenerated.

### Deliverable:

Modify:

* `initiative_to_backlog_row()`
* Keep Flow 1 + Flow 2 integrated.

---

# 🔁 **Gameplay Flow — End-to-End Logic**

Here is the Flow 2 gameplay in natural language sequence:

---

## **Step 0 — Inputs Ready**

(Flow 1 has populated the DB with initiatives.)

You now have a clean DB table:

| initiative_key | title | data... | value_score | effort_score | ... |
| -------------- | ----- | ------- | ----------- | ------------ | --- |

---

## **Step 1 — Select Scoring Framework**

Either:

* Global default (RICE)
* Per-initiative setting (`active_scoring_framework`)
* CLI argument: `--framework`
* Future: AI suggestion

---

## **Step 2 — Normalize Inputs**

Frameworks expect certain numeric fields:

* Impact
* Effort
* Reach
* Confidence
* Dependencies
* Time sensitivity

The Scoring Service ensures:

* None/null → convert to defaults (e.g., 0 or median)
* Strings → numeric parsing
* Incorrect formats → ignored or coerced
* Missing fields → logged

---

## **Step 3 — Compute Scores**

Each framework provides:

```python
ScoreResult(
    value_score: float,
    effort_score: float,
    overall_score: float,
    inputs_json: dict
)
```

`inputs_json` will be written to `initiative_scores.inputs_json` for transparency.

---

## **Step 4 — Save to DB**

The `InitiativeScore` model stores:

* Historical scoring runs
* Framework name
* Values
* Inputs used

And Initiative receives:

* `initiative.value_score`
* `initiative.effort_score`
* `initiative.overall_score`
* `initiative.active_scoring_framework`

### → Makes backlog sheet always up-to-date.

---

## **Step 5 — Backlog Sync**

Flow 1’s backlog writer already has columns for:

* Value Score
* Effort Score
* Overall Score
* Active Scoring Framework

Flow 2 plugs into this by simply updating DB fields.

Backlog sync = one line change.

---

# 📌 **Flow 2: Implementation Roadmap (Coding Order)**

Here is the exact order we should implement Flow 2:

---

## **Phase 1 — Framework Engine (RICE first)**

**(1)** Create base scoring interface
**(2)** Implement RICE scoring
**(3)** Implement WSJF scoring
**(4)** Add framework registry

---

## **Phase 2 — Domain Model Extensions**

**(1)** Review `InitiativeScore` for needed fields
**(2)** Add missing fields (if any)
**(3)** Migration script
**(4)** Add optional "scoring history" table toggle

---

## **Phase 3 — ScoringService**

**(1)** Implement input normalization
**(2)** Implement `compute_for_initiative()`
**(3)** Implement batch scoring for all initiatives
**(4)** Logging & error handling
**(5)** Integration test with a few DB rows

---

## **Phase 4 — CLI + Automation**

**(1)** Create scoring CLI (`scoring_cli.py`)
**(2)** Add flags:

* `--framework RICE`
* `--all`
* `--limit N`

**(3)** Add job:

* `run_scoring_full_sync()`

---

## **Phase 5 — Integration with Backlog Writer**

**(1)** Ensure scores are written into `initiative_to_backlog_row()`
**(2)** Re-run Flow 1 after scoring
**(3)** Confirm central backlog sheet shows scoring values correctly

---

## **Phase 6 — AI Scoring (Optional, but powerful)**

**(1)** Use LLM to estimate missing values
**(2)** Generate RICE components
**(3)** Generate custom math model
**(4)** Save generated math models to DB
**(5)** Plug into scoring framework

---

# 🚀 **End Result After Flow 2**

Flow 2 will give you:

* **Automated scoring of all initiatives**
* **Consistent decision-making framework**
* **Full historical scoring logs**
* **Backlog sheet with live scoring fields**
* **AI-enabled scoring for incomplete/intuitive fields**

Flow 2 makes your roadmap system become a **decision intelligence engine**, not just a data sync pipeline.

---

# Where do manual scoring inputs from backlog fit in?

Your understanding is exactly right:

> “Certain inputs for various scoring flows and frameworks must come from the central backlog sheet and be passed to the backend scoring service to compute scores, then update the DB, and reflect back on the central backlog.”

Conceptually, the full loop is:

1. **Product team edits central backlog sheet**

   * E.g. fields like:

     * `Impact Expected`
     * `Effort Engineering Days`
     * `Strategic Priority Coefficient`
     * `Business Value` (in future)
     * `Time Sensitivity` / `Risk Level`

2. **Flow 1 – Backlog Update (Sheet → DB)**

   * `run_backlog_update(...)` reads the backlog sheet
   * `BacklogService.update_many(...)` writes those central fields into `Initiative`.

3. **Flow 2 – Scoring (DB → scores)**

   * `ScoringService` reads `Initiative` fields
   * Maps them to `ScoreInputs`
   * Runs RICE / WSJF
   * Updates `Initiative` scores + optional `InitiativeScore` history

4. **Flow 1 – Backlog Sync (DB → Sheet)**

   * `write_backlog_from_db(...)` writes:

     * `Value Score`
     * `Effort Score`
     * `Overall Score`
     * `Active Scoring Framework`
   * Back into the central backlog sheet.

So **yes**: product team edits **central sheet** → values go to **DB** via Flow 1 → Flow 2 reads them → scores go back to **DB** → Flow 1 writes the results back to **central sheet**.

# Flow 1:
uv run python -m test_scripts.flow1_cli --log-level INFO

# Flow 2:
uv run python -m test_scripts.flow2_scoring_cli --framework RICE --only-missing --log-level INFO
uv run python -m test_scripts.backlog_sync_cli --log-level INFO


---

