### 1. Drop lists

**Db Drop list:** 

current_pain, desired_outcome, target_metrics → narrative; can be covered by problem_statement, hypothesis, llm_summary or kept in sheet-only notes if needed.

strategic_theme, linked_objectives → replaced by explicit KPI alignment (kpi_contribution_json, strategic KPI list); if you still want classification, keep it sheet-only.

expected_impact_description, impact_metric, impact_unit, impact_low/expected/high → replaced by MathModel + Params + KPI contributions (and/or can live as param rows).

total_cost_estimate → redundant if you keep infra_cost_estimate + (future) cost params; also Phase 5 should optimize on clear cost primitives, not a vague total.

time_sensitivity → replaced by time_sensitivity_score + dates.

missing_fields → replaced by validation jobs + status/writebacks; doesn’t need DB persistence as a field unless you rely on it heavily in workflows.

llm_notes and math warnings don't have to be persisted either. Remove from initiative model. 

**Sheets drop list:**

i'll drop Llm notes and strategic theme from central backlog sheet. 
i'll drop strategic_priority_coefficient and risk level and time sensitivity from productops scoring_inputs tab.
Of course, PMs and/or I will have the liberty to add back any of these columns and use formulas to copy their values from other sheets (e.g., central backlog sheet) to this sheet/tab later. 


2. The write logic in backlog writer that is based on the order of columns in the central backlog sheet is rigid, outdated, undesired, and inconsistent with the other sheet writers that find the right columns based on the headers mappings to be updated and then fill out rows accordingly. Backlog writer must get updated accordingly. 


### 2. New db models and/or new db model fields and/or new sheets and/or new columns:

1. sheet column field: metric_chain_text ; db model field: Initiative.metric_chain_json ; sync flow: PM input on productops sheet mathmodels tab → DB (parsed → metric_chain_json)
2. sheet column field: llm_suggested_metric_chain_text ; no db equivalent needed ; sync flow: LLM suggests → Sheet (PM may copy)



### 3. Locks:


---

1) Central Backlog flow/ownership mistakes: intake→DB→backlog, initiative_key generation, use_math_model source

Agree. Fully.

Title / requesting_team / requester_name / requester_email / country / product_area:

Primary flow: Intake sheets → DB → Central Backlog

Override flow: PM may edit in Backlog → Backlog → DB (Flow1 backlog_update)


initiative_key:

Never PM-authored. Backend generates in DB during intake sync / creation.

Then DB → Backlog (and optionally DB → Intake for backfill).

Other sheets (ProductOps/Optimization Center) should mostly copy via formulas, not be “entered”.


use_math_model:

Primary entry point: ProductOps/Scoring_inputs (PM sets) → DB

Backlog shows it read-only or as a “display mirror” (DB → Backlog).

If Backlog also contains it, it should be treated as read-only mirror unless we explicitly allow Backlog override (I recommend: don’t, keep the single entry point in ProductOps).



Lock: yes, we lock these source-of-truth rules.


---

2) Drop llm_notes and math_warnings from Initiative model and Central Backlog

Agree.

llm_notes: remove from Initiative DB and remove from Central Backlog.

math_warnings: remove from Initiative DB and remove from Central Backlog.

Where they live instead:

math_warnings can remain sheet-only in ProductOps/Scoring_inputs (as now) because it’s operational feedback.

LLM “notes” can be sheet-only in ProductOps/MathModels (as you said), not persisted.



Lock: yes.


---

3) Drop math_warnings from Initiative model

Agree. (Same as #2, but yes explicitly.)

Lock: yes.


---

4) ProductOps Scoring_inputs / MathModels: initiative_key is sheet-to-sheet copy, not “PM selects rows”

Agree.

In those tabs:

initiative_key is typically copied via formulas from Backlog (or other tabs).

It’s effectively read-only.


PM “select rows” applies to the action scope, not to the meaning of the initiative_key cell. So that wording was wrong.


Lock: yes — initiative_key columns are never “entered” by PM.


---

5) InitiativeMathModel.model_name should exist in DB (currently sheet-only)

Agree. Add it to InitiativeMathModel DB model.

Reason: it’s part of the approved model artifact; you’ll want it for history, filtering, and future template reuse.


Lock: yes.


---

6) model_description_free_text should exist in DB; llm_notes should be sheet-only (not DB)

Agree.

Add model_description_free_text to InitiativeMathModel.

Keep llm_notes as LLM writes → MathModels sheet only, not persisted.


Lock: yes.


---

7) New DB fields must be wired into save/sync flows depending on overwrite privilege

Agree. This becomes a non-negotiable implementation policy:

For every new DB field, we must define:

the single entry sheet/tab (if PM-owned),

the allowlist for save,

and whether backend ever overwrites it.



Lock: yes.


---

8) suggested_by_llm flow should be Backend sets → Sheet → DB

Agree (with one nuance).

Correct flow:

LLM job generates suggestion → backend writes to sheet and also knows “LLM suggested”.

Then when PM saves, DB is updated.


Whether we set it:

Directly in DB during the LLM job (preferred), and also reflect it on sheet, OR

Write only to sheet then sync back on save.



Given robustness, I recommend:

LLM job sets DB immediately + writes sheet for transparency.

Save action can keep it consistent (idempotent).


Lock: yes, it should end up true in DB when LLM suggested.


---

9) InitiativeMathModel.updated_at: why did I put NONE in the header group?

You’re right — that was wrong in the earlier header-group file.
It should map to InitiativeMathModel.updated_at.

Lock: fix it (already reflected in v3 logic; but yes, we lock the correction).


---

10) Params tab: model_name should be auto-seeded from InitiativeMathModel.model_name

Agree.

model name column in Params tab is:

read-only display helper (sheet column),

populated by backend during param seeding / sheet refresh.


It does not belong to InitiativeParam table.


Lock: yes.


---

11) Show immediate KPI + metric chain JSON on Central Backlog as read-only; entry point is ProductOps/MathModels

Agree.

Backlog columns:

Immediate KPI Key

Metric Chain JSON


Both are DB → Backlog display only.

Entry/edit surface:

ProductOps/MathModels: metric_chain_text (PM edits) → parsed into DB JSON.

For immediate KPI:

either ProductOps/Scoring_inputs (recommended single entry)

or MathModels (if you want it there too); but pick one entry point.




Lock: yes.


---

12) Should is_optimization_candidate be on OptimizationCenter/Candidates tab?

Agree with your logic: not necessary on that tab.

If a row is in OptimizationCenter/Candidates, it’s already implicitly a candidate.

Better entry point:

Central Backlog as the place PM marks initiatives as “graduated”.


OptimizationCenter/Candidates should mostly be a filtered view of Backlog.


Lock: Put is_optimization_candidate on Backlog (entry), not on OptimCenter/Candidates (view).


---

13) OptimizationConstraintSet mapping mistakes + how Constraints tab relates to DB model

Two parts here.

13.a The mistake you saw (ConstraintSet fields mapped to Candidates)

That was a mistake in earlier versions of the table.
ConstraintSet fields must map to OptimizationCenter/Constraints and OptimizationCenter/Targets, not Candidates.

Candidates fields like:

title, market, department, engineering_tokens, etc. are Initiative fields, not ConstraintSet fields.


Lock: yes, Candidate fields map to Initiative, not OptimizationConstraintSet.

13.b How we use OptimizationConstraintSet vs Constraints tab

Clean model (recommended):

Constraints tab is the PM UI for defining constraints as rows.

On save (pm.optimize_save_constraints or generic save), backend:

1. reads Constraints tab rows,


2. validates them,


3. compiles them into structured JSON blobs (floors/caps/targets/etc.),


4. persists into OptimizationConstraintSet in DB.




So:

Constraints tab = editable input surface

OptimizationConstraintSet = persisted reusable compiled constraint artifact


Targets tab either:

also compiles into OptimizationConstraintSet.targets_json, or

is stored separately later; for v1, we can keep it in the same model.


Lock: this is the intended usage.

Also: we already agreed to drop primary_kpi_key everywhere, so it should not be in that list at all.


---

14. Locked on the below structural decisions:

* Candidates tab will have two columns: north_star_contribution (single number) + strategic_kpi_contributions (summary).

* kpi_contribution_json entry point will be a new ProductOps tab, not Central Backlog.

* Backend will validate + display, not invent numbers.

---

Now to the “big question” (units + normalization): this is the critical math/product bridge: Should we normalize KPIs or use raw units for optimisation?

Practical conclusion for v1

✅ What I recommend we lock now

1. North Star objective mode: use native units (no normalization).


2. Lexicographic modes: targets can be in native units (no normalization).


3. Weighted_kpis mode: normalize each KPI contribution by a KPI scale, defaulting to Targets:

 (GLOBAL target or market target depending on objective scope)

normalized contribution = fraction-of-target




This gives us a clean, consistent story:

> “In weighted objective, weights operate on normalized progress, not raw units.”



And we can still store native units in kpi_contribution_json (good for reporting and sanity).


---

Where do KPI units get defined?

In ProductOps → Metrics_Config, per KPI row:

unit (e.g., GBP, fraction, percent, count)


This is mostly for:

validation (sanity checking)

display formatting

future tooling


It does not change solver math, but it helps humans avoid mistakes.


---

15. Should we merge the Params tab in Product Ops sheet and the newly created KPI_Contributions tab in Product Ops sheet instead of having 2 separate tabs to deal with KPIs end to end?


---

First: restating our insight 


1. Initiative → Metric chain

immediate KPI

intermediary KPIs (optional)

ends at North Star and/or Strategic KPI



2. Metric chain → Mathematical model

formula text expresses how metrics flow and transform

parameters are just the inputs to those transformations



3. Mathematical model → Params

Params tab is essentially:

> “values for variables used in the formula”





4. KPI contribution

is simply the final evaluated outputs of that same model,

but projected onto strategic KPI space (north star + strategic KPIs)




So philosophically:

> Params, metric chain, formula text, and KPI contributions are all manifestations of the same causal model.



That observation is 100% correct.


---

So why not merge Params + KPI Contributions into one tab?

Let’s analyze both options rigorously.


---

Option 1: Merge Params + KPI Contributions into a single tab

What this would mean

One unified tab that contains:

metric variables (inputs)

intermediate KPIs

final KPI outputs (contributions)

possibly units


Pros

Conceptually elegant

One place for “the model”

Strong causal coherence

Fewer tabs


Cons (this is where it breaks in practice)

This is the important part.

1. Inputs vs outputs have fundamentally different semantics

Params = assumptions / inputs / knobs

KPI contributions = results / outputs Mixing them invites accidental editing of outputs.



2. Ownership differs

Params:

PM / Analytics / Finance / Eng

often debated, revised, ranged, approved


KPI contributions:

usually owned by PM + Analytics

should be more controlled and stable

often reviewed at leadership level




3. Lifecycle differs

Params change frequently (scenario analysis)

KPI contributions should change only when model or assumptions change



4. Optimization engine boundary

Optimization should consume:

kpi_contribution_json


It should not care about raw parameters

Keeping outputs separate gives you a clean contract:

> “Optimization consumes outputs, not assumptions.”





5. Future automation

In Phase 5.1 / 6:

LLM or evaluator can recompute KPI contributions automatically


If outputs live in same table as inputs, overwrite rules get messy.




Verdict: elegant on paper, but operationally fragile.


---

Option 2: Keep Params and KPI Contributions separate (recommended)

But with one crucial clarification (this is the key)

They are separate tabs, but they are logically linked through the MathModel.

Think of it like this:

MathModels (structure)
   ↓
Params (inputs / assumptions)
   ↓
[Evaluate model]
   ↓
KPI Contributions (outputs)
   ↓
Optimization

This is exactly how real modeling systems work (Excel models, financial models, ML pipelines).


---

Where each thing belongs (clean mental model)

ProductOps → MathModels

What is the model?

formula_text

metric_chain_text

approved_by_user

structure & logic


ProductOps → Params

What assumptions do we plug into the model?

input variables

ranges

sources

approvals

units (for variables)


ProductOps → KPI_Contributions (new tab)

What does this initiative contribute to strategic KPIs?

explicitly:

{
  "gmv": 120000,
  "retention_30d": 0.01
}

validated against:

Metrics_Config (allowed keys)

units (sanity checks)


may be:

manually entered (v1)

auto-derived later (v1.1+)



Optimization Center

consumes only KPI contributions

never touches Params


---

Final verdict:

Do NOT merge Params and KPI Contributions.

Instead:

keep them as separate tabs

but treat KPI Contributions as:

> “the evaluated, strategic-facing outputs of the MathModel + Params”




We will:

validate consistency between:

metric_chain_text

Params variables

KPI Contributions keys


but not force them into one table.


This is the cleanest, most scalable architecture.


---
