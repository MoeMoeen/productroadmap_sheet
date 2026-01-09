You’re in a good place structurally — your Phase 5 schema is coherent, and the migration looks aligned with what we locked. I’ll answer in three parts:

1. whether to drop `Roadmap` / `RoadmapEntry` now
2. how the tables relate (ERD-style explanation)
3. a practical “what each table is for” mental model

---

## 1) Should you remove Roadmap/RoadmapEntry and replace with Portfolio stuff?

**Don’t remove them yet.** Keep both, but change how you *use* them.

### Why keep them

* **Portfolio** is the optimizer’s *decision artifact* (“selected set + allocations + provenance”).
* **Roadmap** is the *published plan artifact* (“Q1 plan”, “H1 plan”, sequencing, locks, communication”).

Even if Portfolio contains “planned quarter” someday, Roadmap still matters because:

* humans override things after optimization
* sequencing & commitments evolve
* you’ll want multiple “published” versions from one portfolio (or from multiple runs)
* you’ll want a stable “roadmap view” for stakeholders

### What to refactor (recommended)

Right now `RoadmapEntry` duplicates Portfolio concepts (selected flags, scenario label, optimization_run_id, score_used fields). Those overlap with:

* `PortfolioItem`
* `OptimizationRun`

So instead of deleting Roadmap, **simplify RoadmapEntry** so it becomes:

> “Roadmap-specific scheduling + override metadata”

and stop treating RoadmapEntry as the optimization output record.

**Practical recommendation:**

* Make **Portfolio/PortfolioItem** the optimizer output.
* Make **Roadmap/RoadmapEntry** a *publish layer* that can be created from a Portfolio.

### Minimal refactor to avoid duplication

In `RoadmapEntry`, consider removing/avoiding (eventually):

* `is_selected` (PortfolioItem already implies selection)
* score snapshot fields (PortfolioItem can store snapshot if you want)
* optimization provenance fields (OptimizationRun already stores this)

Keep:

* `priority_rank`
* `planned_quarter`, `planned_year`
* `is_locked_in`
* `notes`
* “manual override” flags if needed

Also: change `optimization_run_id` type. In your old model it’s `String(100)`. In Phase 5 you now have `optimization_runs.id` (int). If you keep a link, it should be `ForeignKey("optimization_runs.id")`, not a string.

So: **keep Roadmap tables, but redefine their purpose.**

---

## 2) How the tables relate to each other (big picture)

Here’s the “clean graph” you now have, with relationships:

### Core entity

**Initiative**

* the canonical unit of work
* created/updated from intake + backlog + productops

### Scoring layer

**InitiativeMathModel** (0 or 1 per Initiative)

* one-to-one via `Initiative.math_model_id`
* holds formula + metadata + approval

**InitiativeParam** (0..N per Initiative)

* parameters used by frameworks (including MATH_MODEL)
* used by scoring engines

**InitiativeScore** (0..N per Initiative)

* optional history/audit snapshots per scoring run/framework

### Optimization layer

**OrganizationMetricConfig** (global registry)

* defines KPI universe: north_star vs strategic + units

**OptimizationScenario** (0..N)

* defines objective_mode, weights, capacity

**OptimizationConstraintSet** (0..N, linked to scenario via scenario_id)

* Compiled constraints + targets from sheet rows
* JSON columns: floors, caps, targets (multi-dimensional nested), mandatory, bundles, exclusions (split into initiatives + pairs), prerequisites, synergies
* Identified by (scenario_id, name) - one scenario can have multiple constraint sets (e.g., "Baseline", "Aggressive")

**OptimizationRun** (0..N per scenario)

* one solver execution record
* stores snapshots + result_json + solver metadata
* links to:

  * scenario
  * constraint set

**Portfolio** (0..N per scenario)

* persisted output artifact
* links to:

  * scenario
  * optimization_run (optional but recommended always)
* has many PortfolioItems

**PortfolioItem** (0..N per portfolio)

* join table between Portfolio and Initiative
* holds selected flag, allocated_tokens, rank, source

### Publishing layer (keep it separate from optimization outputs)

**Roadmap** (0..N)

* Published plan artifact for stakeholder communication
* Can be created from a Portfolio ("Publish" action)
* Versioned, timestamped, human-curated

**RoadmapEntry** (0..N per roadmap)

* Join between Roadmap and Initiative
* Should focus on scheduling/locks/notes/manual overrides
* NOT the optimization output record (that's PortfolioItem)
* May diverge from Portfolio due to human adjustments

**Recommended refactor:** Remove optimization provenance fields from RoadmapEntry (is_selected, score snapshots, optimization_run_id). Link to Portfolio instead if lineage tracking needed.

---

## 3) Practical mental model: what each table is “for”

### Initiative (truth)

> “What is the work? Who requested it? What is it? What are its properties?”

### InitiativeMathModel + InitiativeParam (assumptions + model)

> “How do we quantify this initiative’s impact and effort?”

### InitiativeScore (audit)

> “What did the system compute, when, with what inputs?”

### OrganizationMetricConfig (KPI registry)

> “What metrics exist, what’s north star, what’s strategic, what units?”

### OptimizationScenario (strategy switchboard)

> “For this planning cycle, what are we optimizing for and what’s the capacity?”

### OptimizationConstraintSet (rules)

> “What constraints apply: floors/caps/targets/mandatory/bundles/exclusions?”

### OptimizationRun (execution record)

> “We ran the solver at time T with inputs X; result was Y.”

### Portfolio + PortfolioItem (decision artifact)

> “Here’s the selected set + allocation + ranking that came out of a run (or manual override).”

### Roadmap + RoadmapEntry (published plan)

> “Here’s the communicated plan: sequencing, timing, locks, and human edits.”

---

## Suggested “clean” relationship direction (important for Phase 5 UX)

1. PM runs optimization → creates **OptimizationRun + Portfolio**
2. PM clicks “Publish” → creates **Roadmap + RoadmapEntry** from the chosen Portfolio
3. Roadmap can later diverge from Portfolio due to human scheduling/locks

That keeps optimizer outputs auditable and preserves reality of planning.

---

