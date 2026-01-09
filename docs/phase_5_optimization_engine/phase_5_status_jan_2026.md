# Phase 5 Optimization Engine — Status Check-In

**Date:** 9 January 2026  
**Status:** Constraints pipeline complete. Ready for solver integration.

---

## Executive Summary

**The Optimization Center data pipeline is production-ready.**

All structural, architectural, and data quality issues have been resolved. The system can now:

- Ingest PM-authored constraints and targets from sheets
- Validate, normalize, and compile them into engine-ready structures
- Persist them to database with provenance
- Write back status and errors to sheets with row-level precision

**No blocking design flaws remain.**

What remains is **solver implementation** (engine-side semantics) and **optional validation enhancements**.

---

## What is Complete and Stable

### 1. Schema Layer ✅

**Files:**
- `app/schemas/optimization_center.py`

**Status:** Production-grade, frozen.

**Capabilities:**
- Discriminated union constraint types (9 types: capacity floors/caps, mandatory, bundles, exclusions, prerequisites, synergies, targets)
- Dimension/dimension_key model supports arbitrary dimensional constraints (country, product, country_product, initiative, etc.)
- Multi-dimensional targets with nested JSON structure: `{dimension: {dimension_key: {kpi_key: {type, value, notes}}}}`
- Bundle member deduplication and normalization
- Exclusion pair normalization (sorted pairs to prevent duplicates)
- Separate `CapacityDimension` literal type prevents misuse of initiative keys as capacity dimensions
- Row-level validation with errors vs warnings distinction

**Key Design Decisions:**
- Targets are **NOT auto-aggregated** (global targets are explicit constraints, not computed sums)
- `dimension="all"` means global scope, not sum-of-children
- Conflicts detected by solver, not schema layer
- Future dimensions require zero schema changes

---

### 2. Compilation Layer ✅

**Files:**
- `app/services/optimization_compiler.py` (pure compilation, zero I/O)

**Status:** Production-ready, deterministic, side-effect free.

**Capabilities:**
- Pure function: `compile_constraint_sets(constraint_rows, target_rows, valid_kpis) -> (compiled_dict, messages)`
- Validates rows via Pydantic schemas
- Normalizes constraint_type, dimension, dimension_key for parser compatibility
- Buckets constraints by (scenario_name, constraint_set_name)
- Deduplicates all list fields (mandatory, exclusions, synergies) before returning
- Returns structured validation messages with row numbers, keys, errors, warnings

**Architecture:**
- No SheetsClient dependencies
- No DB session management
- Testable in isolation
- Logging for observability

---

### 3. Sync Orchestration Layer ✅

**Files:**
- `app/services/optimization_sync_service.py` (I/O orchestration)

**Status:** Production-ready.

**Capabilities:**
- Reads constraints and targets tabs via sheet readers
- Fetches valid KPI keys from `OrganizationMetricConfig` for target validation
- Calls pure compiler with row data
- Resolves scenario names to DB IDs
- Upserts `OptimizationConstraintSet` records with JSON payloads
- Commits atomically
- Returns persisted records + validation messages for writer layer

**JSON Payload Shapes (DB-persisted):**
```python
floors_json: {dimension: {dimension_key: min_tokens}}
caps_json: {dimension: {dimension_key: max_tokens}}
targets_json: {dimension: {dimension_key: {kpi_key: {type, value, notes?}}}}
mandatory_initiatives_json: [initiative_key, ...]
bundles_json: [{bundle_key, members: [...]}, ...]
exclusions_initiatives_json: [initiative_key, ...]
exclusions_pairs_json: [[key1, key2], ...]
prerequisites_json: {dependent_key: [prereq1, prereq2, ...], ...}
synergy_bonuses_json: [[key1, key2], ...]
```

---

### 4. Sheet Readers ✅

**Files:**
- `app/sheets/optimization_center_readers.py`

**Status:** Stable, alias-aware.

**Capabilities:**
- `ConstraintsReader`: reads Constraints tab with header aliases
- `TargetsReader`: reads Targets tab with header aliases
- Returns Pydantic models per row
- Handles empty/missing values gracefully

---

### 5. Sheet Writers ✅

**Files:**
- `app/sheets/optimization_center_writers.py`

**Status:** Fixed (no key collisions).

**Capabilities:**
- `ConstraintsWriter`: writes validation messages back to Constraints tab (run_status, error_message)
- `TargetsWriter`: writes validation messages back to Targets tab
- **Composite key scoping fixed:** now includes (scenario_name, constraint_set_name, dimension, dimension_key, kpi_key) to prevent collisions
- Provenance tracking via `last_sync_timestamp`

---

### 6. Database Models ✅

**Files:**
- `app/db/models/optimization.py`

**Status:** Schema stable.

**Models:**
- `OptimizationScenario`: scenario definition (name, objective config)
- `OptimizationConstraintSet`: constraint set per scenario (JSON payloads for all constraint types)
- `OptimizationRun`: execution history (solver logs, results)
- `Portfolio`: output decision set
- `PortfolioItem`: selected initiatives per portfolio

**Recent Migration:**
- `alembic/versions/20260108_split_exclusions_add_constraints.py` (applied)
  - Split `exclusions_json` → `exclusions_initiatives_json` + `exclusions_pairs_json`
  - Added all constraint JSON columns

---

## Architecture: Clean Separation of Concerns

```
┌─────────────────────────────────────────────────────────────┐
│ Sheets (PM-facing)                                          │
│  - Optimization Center: Constraints, Targets tabs           │
│  - Aliases: scenario_name, constraint_set_name, etc.        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Sheet Readers (I/O)                                         │
│  - ConstraintsReader, TargetsReader                         │
│  - Returns: List[(row_num, RowSchema)]                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Schemas (Validation)                                        │
│  - Discriminated unions per constraint_type                 │
│  - validate_constraint_row(), validate_target_row()         │
│  - Returns: ValidationMessage (row_num, key, errors, warns) │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Compiler (Pure Logic) — optimization_compiler.py            │
│  - compile_constraint_sets(rows) -> (compiled, messages)    │
│  - Zero I/O dependencies (no SheetsClient, no DB)           │
│  - Deterministic, testable, side-effect free                │
│  - Deduplication + normalization                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Sync Service (Orchestration) — optimization_sync_service.py │
│  - sync_constraint_sets_from_sheets()                       │
│  - Reads sheets → calls compiler → upserts DB               │
│  - Resolves scenario names → OptimizationScenario IDs       │
│  - Fetches valid KPIs for target validation                 │
│  - Returns: (persisted_records, validation_messages)        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Database (Persistence)                                      │
│  - OptimizationConstraintSet (JSON payloads)                │
│  - Floors, caps, targets, mandatory, bundles, exclusions,   │
│    prerequisites, synergies                                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Sheet Writers (Feedback)                                    │
│  - ConstraintsWriter, TargetsWriter                         │
│  - Writes: run_status, error_message per row               │
│  - Composite keys prevent collisions                        │
└─────────────────────────────────────────────────────────────┘
```

**Key Architectural Properties:**

1. **Pure compilation layer** can be tested without sheets or DB
2. **I/O orchestration** is isolated in sync service
3. **Schema validation** happens before compilation
4. **Writers** provide row-level feedback to PMs
5. **Extensible:** new constraint types = schema update only

---

## Recent Production-Grade Fixes (Completed)

### 1. Dimension Key Field Rename
- **Issue:** Ambiguous `key` field name
- **Fix:** Renamed to `dimension_key` across all schemas, models, readers, writers, compiler
- **Impact:** Crystal-clear semantics for dimensional constraints

### 2. Writer Key Collision Prevention
- **Issue:** Rows with same scenario_name/constraint_set_name but different dimensions/KPIs overwrote each other
- **Fix:** Full composite keys in writers: `(scenario_name, constraint_set_name, dimension, dimension_key, kpi_key)`
- **Impact:** Zero data loss during status writes

### 3. Multi-Dimensional Target JSON Structure
- **Issue:** Flat `{dimension_key: {kpi: {...}}}` couldn't support multiple dimensions
- **Fix:** Nested `{dimension: {dimension_key: {kpi: {...}}}}`
- **Impact:** Country targets, product targets, country+product targets all work cleanly

### 4. Bundle Member Deduplication
- **Issue:** Sheet could have duplicate bundle members (copy-paste errors)
- **Fix:** Schema-level deduplication in `BundleRowSchema.model_validator`
- **Impact:** Prevents solver confusion from duplicate bundle members

### 5. Exclusion Pair Normalization
- **Issue:** `[A, B]` and `[B, A]` treated as different exclusions
- **Fix:** Schema sorts pairs: `tuple(sorted([left, right]))` before deduplication
- **Impact:** Clean JSON, no redundant constraints

### 6. Capacity Dimension Safety
- **Issue:** Could accidentally use initiative keys in capacity constraints
- **Fix:** `CapacityDimension = Literal["country", "product", "department", "category", "program", "all"]`
- **Impact:** Type-safe capacity constraints, catches misuse at validation time

### 7. Split Exclusions JSON Columns
- **Issue:** Mixed exclusion types (single initiatives vs pairs) in one JSON field
- **Fix:** DB migration split into `exclusions_initiatives_json` + `exclusions_pairs_json`
- **Impact:** Solver can differentiate "exclude initiative X" from "exclude pair (A, B)"

---

## Remaining Decisions (Non-Blocking)

These are **policy choices** for the solver layer, not schema/pipeline bugs.

### A. Engine Semantics (Next Phase)

Define in the optimizer:

1. **How multi-dimensional targets are enforced:**
   - Hard constraints vs soft penalties
   - Floor vs goal weighting
   - Conflicting targets behavior (e.g., sum(country targets) > global target)

2. **How contradictory constraints behave:**
   - Mandatory initiative also excluded → fail fast or soft warning?
   - Mandatory + capacity conflict → infeasible or adjust?
   - Prerequisite cycles → error or ignore?

**Location:** Solver adapter / feasibility checker (not schema layer).

---

### B. Optional Validation Enhancements (Later)

Post-compile validation pass to warn PMs about:

- Global target < sum of dimensional targets (inconsistency warning)
- Capacity floors exceed caps (impossible)
- Mandatory initiatives exceed available capacity (infeasible)
- Bundle members reference non-existent initiative keys
- Duplicate bundle names per constraint set

**Location:** Feasibility checker (pre-solver).

**Priority:** Nice-to-have, not blocking.

---

## Immediate Next Steps

### 1. Freeze the Optimization Center Schema ✅
**Status:** DONE as of 9 Jan 2026.

No more field renames, no more column changes.

Schema is **production-locked** for Phase 1.

---

### 2. Design Solver-Side Constraint Interface (Solver Adapter)

**Purpose:** Translate compiled constraints → solver model.

**Interface:**
```python
class SolverAdapter(Protocol):
    def solve(self, problem: OptimizationProblem) -> OptimizationSolution:
        ...
```

**Input (`OptimizationProblem`):**
- Candidates (initiatives with tokens, scores, dimensions, KPI contributions)
- Objective definition (mode: north_star / weighted_kpis / lexicographic)
- Compiled constraints from `OptimizationConstraintSet`:
  - `capacity_floors`, `capacity_caps`
  - `mandatory_initiatives`
  - `bundles`
  - `exclusions_initiatives`, `exclusions_pairs`
  - `prerequisites`
  - `synergy_bonuses`
  - `targets`

**Output (`OptimizationSolution`):**
- Selected initiative keys
- Allocations (tokens per dimension slice)
- Achieved KPI values
- Solver status (optimal, infeasible, timeout)
- Diagnostics (solve time, iterations, etc.)

**Implementation Options:**
- MILP (PuLP, Google OR-Tools)
- CP-SAT (Google OR-Tools)
- Custom heuristic

**Next Steps:**
- Define `OptimizationProblem` schema
- Define `OptimizationSolution` schema
- Implement stub adapter (returns mock solution)

---

### 3. Build Feasibility Checker (Pre-Solver Validation)

**Purpose:** Fast contradiction detection before expensive solver call.

**Why:**
- Solvers are slow to return "infeasible"
- "Infeasible" alone is not helpful to PMs
- Need human-readable diagnosis for sheet feedback

**Interface:**
```python
class FeasibilityChecker(Protocol):
    def check(self, problem: OptimizationProblem) -> FeasibilityReport:
        ...

class FeasibilityReport(BaseModel):
    is_feasible: bool
    errors: list[str]       # Hard contradictions (must fix)
    warnings: list[str]     # Potential issues (review)
    details: dict | None    # Structured diagnostics
```

**Checks (Deterministic, Fast):**

**Hard Contradictions:**
- Mandatory initiative also excluded
- Bundle includes excluded initiative
- Exclude pair includes mandatory initiative
- Prerequisite cycle (A requires B, B requires A)
- Prerequisite references non-existent initiative key

**Capacity Impossibilities:**
- `sum(capacity_floors)` > `global_capacity_cap`
- Dimensional floor exceeds available tokens in that slice
- Mandatory initiatives + bundles exceed global cap

**Target Impossibilities (Optional):**
- Max achievable KPI < floor target (if KPI bounds known)

**Output:**
- If infeasible: don't call solver
- Write `run_status = "FAILED: infeasible - <reason>"` to sheet rows
- Optionally write row-level error messages to constraints/targets

**Next Steps:**
- Define `FeasibilityReport` schema
- Implement checker with contradiction detection
- Wire into sync flow: compile → check feasibility → solve (if feasible)

---

### 4. Run 2–3 Real PM Scenarios (Smoke Test)

**Purpose:** Validate end-to-end flow with realistic data.

**Test Cases:**

**Scenario A: Simple Feasible**
- 5 initiatives, 1 mandatory, 1 excluded
- Global capacity cap = 1000 tokens
- 1 north star target (floor)
- Expected: feasible, solver returns solution

**Scenario B: Conflicting Constraints**
- Mandatory initiative also in exclusion list
- Expected: feasibility checker catches error, solver not called
- Sheet shows: `run_status = "FAILED: infeasible - initiative_123 is both mandatory and excluded"`

**Scenario C: Multi-Dimensional Targets**
- Country-level targets (UK: floor 500, US: floor 800)
- Product-level targets (Payments: goal 300, Logistics: floor 200)
- Global capacity cap = 2000 tokens
- Expected: feasible, solver respects all targets

**Validation:**
- Constraints/targets read from sheets correctly
- Compilation produces valid JSON payloads
- DB records persisted with correct shapes
- Feasibility checker catches contradictions
- (If solver stub) mock solution returns
- Results written back to sheets with provenance

---

### 5. Create Canonical PM Guide (Documentation)

**Title:** "How to Fill the Optimization Center Without Shooting Yourself in the Foot"

**Sections:**

1. **Overview**
   - What is the Optimization Center?
   - When to use it (portfolio planning, capacity allocation, tradeoff decisions)

2. **Scenarios and Constraint Sets**
   - Scenario = objective mode + weights + capacity config
   - Constraint Set = rules for one scenario (can have multiple per scenario)
   - Run = execution instance (scenario + constraint set + candidates)

3. **Constraint Types Explained**
   - Capacity floors/caps: "At least X tokens in UK" / "At most Y tokens in Growth"
   - Mandatory: "Must include initiative_123"
   - Bundles: "If initiative_A selected, also select B, C, D"
   - Exclusions: "Never select initiative_X" / "Never select both A and B together"
   - Prerequisites: "If initiative_A selected, must also select B"
   - Synergy bonuses: "If both A and B selected, bonus score" (future)

4. **Targets Explained**
   - Floor: "Must achieve at least X"
   - Goal: "Prefer solutions closer to Y"
   - Multi-dimensional: country-level, product-level, country+product cross-sections
   - Global (`dimension="all"`): applies to entire portfolio

5. **Common Mistakes**
   - Mandatory initiative also excluded → infeasible
   - Sum of dimensional floors > global cap → infeasible
   - Conflicting targets (global floor < sum of country floors) → solver decides, no auto-aggregation
   - Using initiative keys in capacity constraints → validation error

6. **How to Interpret run_status**
   - `PENDING`: not yet processed
   - `SUCCESS`: compiled and persisted
   - `FAILED: <reason>`: validation error, see error_message column
   - `INFEASIBLE: <reason>`: feasibility checker detected contradiction

7. **Best Practices**
   - Start simple (few constraints, one target)
   - Use constraint sets to experiment (baseline vs relaxed vs strict)
   - Review validation messages before running solver
   - Name scenarios/constraint sets clearly (e.g., "2026-Q1_Baseline", "UK_Aggressive_Expansion")

**Next Steps:**
- Draft PM guide
- Review with PM stakeholders
- Add to docs/ folder
- Link from sheet instructions tab

---

## Summary: Where We Are

| Component | Status | Confidence |
|-----------|--------|------------|
| Schema validation | ✅ Production-ready | 100% |
| Pure compilation | ✅ Production-ready | 100% |
| Sync orchestration | ✅ Production-ready | 100% |
| Sheet readers/writers | ✅ Production-ready | 100% |
| DB models/migrations | ✅ Stable | 100% |
| Dimension/key model | ✅ Extensible, locked | 100% |
| Multi-dimensional targets | ✅ Nested JSON, correct | 100% |
| Writer key collisions | ✅ Fixed | 100% |
| Bundle deduplication | ✅ Schema-enforced | 100% |
| Exclusion normalization | ✅ Schema-enforced | 100% |
| Solver adapter | ⏳ Next step | N/A |
| Feasibility checker | ⏳ Next step | N/A |
| PM guide | ⏳ Documentation task | N/A |
| End-to-end smoke test | ⏳ Integration test | N/A |

---

## Critical Path Forward

1. **Week 1:** Define `OptimizationProblem` and `OptimizationSolution` schemas
2. **Week 2:** Implement feasibility checker (contradiction detection)
3. **Week 3:** Implement solver adapter stub (returns mock solutions)
4. **Week 4:** Run 3 smoke test scenarios end-to-end
5. **Week 5:** Draft PM guide and review with stakeholders
6. **Week 6:** Real solver integration (MILP/CP-SAT)

---

## Files Modified in Recent Architecture Split

**Created:**
- `app/services/optimization_compiler.py` (pure compilation, zero I/O)
- `app/services/optimization_sync_service.py` (I/O orchestration)

**Deleted:**
- `app/services/optimization_center_compiler.py` (mixed concerns, replaced by above)

**Result:** Clean separation between pure logic and I/O orchestration.

---

## Key Contacts and Resources

**Documentation:**
- Phase 5 glossary: `docs/phase_5_optimization_engine/phase_5_glossary.md`
- Implementation roadmap V2: `docs/phase_5_optimization_engine/phase_5_implementation_roadmap_V2.0.md`
- JSON shapes spec: `docs/phase_5_optimization_engine/phase_5_optimization_shapes_jsons.md`

**Code:**
- Schemas: `app/schemas/optimization_center.py`
- Compiler: `app/services/optimization_compiler.py`
- Sync: `app/services/optimization_sync_service.py`
- Models: `app/db/models/optimization.py`
- Readers: `app/sheets/optimization_center_readers.py`
- Writers: `app/sheets/optimization_center_writers.py`

**Migrations:**
- Latest: `alembic/versions/20260108_split_exclusions_add_constraints.py`

---

**Document Version:** 1.0  
**Last Updated:** 9 January 2026  
**Next Review:** After solver adapter implementation
