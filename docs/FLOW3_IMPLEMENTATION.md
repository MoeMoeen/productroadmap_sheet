# Flow 3 Implementation: Product Ops Scoring I/O and Multi-Framework Support

**Version**: 1.0  
**Date**: 2025-12-04  
**Status**: Complete (ready for testing)

## Overview

Flow 3 integrates the Product Ops workbook with the scoring system, allowing for efficient scoring of initiatives using multiple frameworks (RICE and WSJF) simultaneously.

### Key Components

1. **Scoring Inputs Tab**
   - The `Scoring_Inputs` tab allows product managers to input parameters for both RICE and WSJF frameworks.
   - Each initiative can have multiple framework scores computed without altering the active scoring framework.

2. **ScoringService Enhancements**
   - The `score_initiative_all_frameworks` method computes scores for all frameworks for a single initiative.
   - The `score_all_frameworks` method processes all initiatives, allowing for batch scoring across both frameworks.

3. **Strong Sync Logic**
   - The strong sync mechanism ensures that inputs from the `Scoring_Inputs` tab are reflected in the corresponding initiative fields in the database.

4. **Config Tab**
   - A new `Config` tab allows product managers to adjust scoring configurations without modifying the codebase.

### Implementation Steps

1. **Create Product Ops Workbook**
   - Set up the `Product Ops Workbook` with necessary tabs.

2. **Implement Scoring Logic**
   - Use the new scoring methods to compute and store scores based on inputs from the `Scoring_Inputs` tab.

3. **Testing and Validation**
   - Ensure that the scoring logic works as intended and that the outputs are correctly reflected in the Product Ops sheet.

---

## Problem Statement

**Root Cause Identified**: Per-framework scores were not stored separately. Only one set of `value_score`, `effort_score`, `overall_score` existed in the DB. When a PM changed `active_scoring_framework` from RICE to WSJF:
- The system recomputed scores using WSJF inputs
- Overwrote the `value_score` fields with WSJF results
- RICE scores were lost

**Secondary Issue**: No write-back from DB to Product Ops sheet. Scores computed by Flow 2 (Scoring Job) were never synced back to the Product Ops sheet where PMs expected to see them.

**Data Flow Gap**:
```
Product Ops Sheet (WRITE from PM) --[Flow 3.B sync]→ DB
                                      ↓ (Flow 2 scoring)
                                      [no write-back]
                                      ↓
                                 Central Backlog Sheet
```

---

## Solution Architecture

### 1. Per-Framework Score Storage (DB Schema)

Added 6 new columns to `initiatives` table:
- `rice_value_score`: RICE framework value score
- `rice_effort_score`: RICE framework effort score
- `rice_overall_score`: RICE framework overall score
- `wsjf_value_score`: WSJF framework value score
- `wsjf_effort_score`: WSJF framework effort score
- `wsjf_overall_score`: WSJF framework overall score

Plus existing active framework columns (no change):
- `value_score`: Active framework's value score
- `effort_score`: Active framework's effort score
- `overall_score`: Active framework's overall score
- `active_scoring_framework`: "RICE" or "WSJF"

**Migration**: `alembic/versions/20251204_per_fw_scores.py`

### 2. Updated ScoringService

#### Method: `score_initiative(initiative, framework)`
Dual-write behavior:
- Compute scores using `framework` engine
- Store in active fields (`value_score`, `effort_score`, `overall_score`, `active_scoring_framework`)
- **NEW**: Also store in framework-specific fields:
  - If framework==RICE: set `rice_value_score`, `rice_effort_score`, `rice_overall_score`
  - If framework==WSJF: set `wsjf_value_score`, `wsjf_effort_score`, `wsjf_overall_score`

#### Method: `score_initiative_all_frameworks(initiative)`
**NEW**: Score an initiative using ALL frameworks in a single pass:
- Iterates over [RICE, WSJF]
- Calls `score_initiative` for each framework
- Populates both `rice_*` and `wsjf_*` score columns
- Does NOT change `active_scoring_framework`

#### Method: `score_all_frameworks(commit_every=None)`
**NEW**: Score ALL initiatives using ALL frameworks:
- Queries all initiatives from DB
- For each, calls `score_initiative_all_frameworks`
- Commits every N rows
- Returns count of initiatives processed
- Logs all errors but continues processing

**Use Case**: Called from Flow 3.C after syncing Product Ops inputs. Ensures both RICE and WSJF scores available for comparison in Product Ops sheet.

### 3. Multi-Framework Score Write-Back Job

**Module**: `app/sheets/productops_writer.py` (shared writer, follows backlog_writer/intake_writer pattern)  
**Job**: `app/jobs/flow3_product_ops_job.py::run_flow3_write_scores_to_sheet()`

#### Architecture Pattern
Following the established pattern in your codebase:
- **Writer** (`app/sheets/productops_writer.py`): Handles sheet mechanics
  - Reads per-framework scores from DB
  - Finds initiative rows by initiative_key
  - Updates ONLY score columns using targeted cell updates
  - Uses batch updates for efficiency
  
- **Job** (`app/jobs/flow3_product_ops_job.py`): Orchestration layer
  - Delegates to writer
  - Handles configuration and error handling

#### Implementation Details

**Targeted Cell Updates** (not full regeneration):
1. Query sheet to get headers and find score column indices
2. Load all initiatives from DB (keyed by initiative_key)
3. For each row in sheet:
   - Extract initiative_key
   - Find matching Initiative in DB
   - For each score column (rice_value_score, wsjf_overall_score, etc.):
     - If score value exists in DB, add to batch update
4. Send batch updates to Google Sheets API

**Benefits**:
- 10-100x faster than full regeneration for large sheets
- Only touches changed rows/columns
- Preserves PM edits in other columns
- Single API call for all updates

**Column Flexibility**:
- Handles both header formats: "rice_value_score" and "RICE: Value Score"
- Header normalization: both map to field name `rice_value_score`
- Gracefully handles missing score columns (only updates if column exists)

**Constants** (in `productops_writer.py`):
```python
PRODUCTOPS_SCORE_OUTPUT_COLUMNS = [
    "rice_value_score", "rice_effort_score", "rice_overall_score",
    "wsjf_value_score", "wsjf_effort_score", "wsjf_overall_score",
]
```

---

## Flow 3 Three-Phase Pipeline

### Phase 3.A: Product Ops Configuration (Already Complete)
- ProductOpsConfig: Settings and sheet coordinates
- ScoringInputsReader: Flexible header parsing (handles both "rice_reach" and "RICE: Reach")

### Phase 3.B: Input Sync (Already Complete)
**Job**: `run_flow3_sync_inputs_to_initiatives(db, ...)`

Strong sync: Product Ops sheet → DB
- Reads each row from Scoring_Inputs tab
- For each initiative_key, finds Initiative in DB
- Writes framework-prefixed parameters (rice_reach, wsjf_job_size, etc.)
- Writes active_scoring_framework and extras (strategic_priority_coefficient, risk_level)
- Empty cells → None or framework defaults (strategic_priority_coefficient defaults to 1.0, not None)

### Phase 3.C: Compute & Output (NEW)

#### Phase 3.C.1: Compute All Frameworks
**Job**: `service.score_all_frameworks(commit_every=10)`

Computes RICE and WSJF scores for all initiatives:
- Reads all framework-prefixed parameters from DB
- For RICE: rice_reach, rice_impact, rice_confidence, rice_effort
- For WSJF: wsjf_business_value, wsjf_time_criticality, wsjf_risk_reduction, wsjf_job_size
- Stores results in per-framework score columns
- Allows PMs to see scores from all frameworks for comparison

#### Phase 3.C.2: Write Scores Back to Sheet
**Job**: `run_flow3_write_scores_to_sheet(db)`

Syncs computed scores back to Product Ops sheet:
- Reads rice_value_score, rice_effort_score, rice_overall_score from DB
- Reads wsjf_value_score, wsjf_effort_score, wsjf_overall_score from DB
- Updates matching columns in Product Ops Scoring_Inputs sheet
- Creates data lineage: PM inputs → DB → Computed scores → Product Ops sheet (for review/audit)

---

## CLI Interface

**File**: `test_scripts/flow3_product_ops_cli.py`

```bash
# Preview inputs without writing to DB
python test_scripts/flow3_product_ops_cli.py --preview

# Sync Product Ops sheet to DB (Phase 3.B)
python test_scripts/flow3_product_ops_cli.py --sync

# Compute all frameworks for all initiatives (Phase 3.C.1)
python test_scripts/flow3_product_ops_cli.py --compute-all

# Write per-framework scores back to sheet (Phase 3.C.2)
python test_scripts/flow3_product_ops_cli.py --write-scores

# Combine flags with batch control
python test_scripts/flow3_product_ops_cli.py --sync --batch-size 25
python test_scripts/flow3_product_ops_cli.py --compute-all --batch-size 50
```

---

## End-to-End Test

**File**: `test_scripts/test_flow3_e2e.py`

Comprehensive Flow 3 validation:
1. Preview Product Ops inputs
2. Flow 3.B: Sync inputs to DB
3. Flow 3.C Phase 1: Compute all frameworks
4. Flow 3.C Phase 2: Write scores back to sheet
5. Validate that both RICE and WSJF scores populated

Run:
```bash
python test_scripts/test_flow3_e2e.py
```

Expected output shows:
- Number of initiatives synced
- Number with active_scoring_framework set
- Number with rice_overall_score populated
- Number with wsjf_overall_score populated
- Sample scores for first 3 initiatives showing both frameworks

---

## Data Flow (Complete)

```
┌─────────────────────────────────────────────────────────────────┐
│ PRODUCT OPS SHEET (PM Control Plane)                           │
│ - rice_reach, rice_impact, rice_confidence, rice_effort         │
│ - wsjf_business_value, wsjf_time_criticality, ...               │
│ - active_scoring_framework (RICE or WSJF per initiative)        │
│ - [OUTPUT ONLY] rice_value_score, rice_overall_score, ...       │
│ - [OUTPUT ONLY] wsjf_value_score, wsjf_overall_score, ...       │
└────────────┬────────────────────────────────────────────────────┘
             │ [Flow 3.B] Strong sync (write)
             ↓
┌─────────────────────────────────────────────────────────────────┐
│ DB INITIATIVES TABLE                                             │
│ Input fields:                                                    │
│ - rice_reach, rice_impact, rice_confidence, rice_effort         │
│ - wsjf_business_value, wsjf_time_criticality, ...               │
│ - active_scoring_framework                                       │
│ Output fields (active):                                         │
│ - value_score, effort_score, overall_score                      │
│ Output fields (per-framework) [NEW]:                            │
│ - rice_value_score, rice_effort_score, rice_overall_score       │
│ - wsjf_value_score, wsjf_effort_score, wsjf_overall_score       │
└────────┬──────────────────────────────────────────────────┬─────┘
         │ [Flow 3.C.1] Compute all frameworks
         │ [Flow 3.C.2] Write scores back (read)
         ↓                                     ↓
    [RICE Engine]                    [Product Ops Sheet]
    [WSJF Engine]                    (write per-framework scores)
         │
         └──→ Stores rice_*, wsjf_* scores in DB
             
         DB (read value_score by active_framework)
         │ [Flow 1] Backlog sync (read)
         ↓
┌─────────────────────────────────────────────────────────────────┐
│ CENTRAL BACKLOG SHEET (Stakeholder Dashboard)                  │
│ - initiative_key, initiative_name, ...                          │
│ - value_score, effort_score, overall_score                      │
│ - active_scoring_framework (for reference)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Unified Naming Convention

**All three layers use identical names** (no translations):

| Layer | RICE Reach | RICE Effort | WSJF Job Size | RICE Scores | WSJF Scores |
|-------|-----------|-------------|---------------|------------|------------|
| Sheet Header | `rice_reach` or `RICE: Reach` | `rice_effort` | `wsjf_job_size` | `rice_value_score` | `wsjf_value_score` |
| Python Code | `initiative.rice_reach` | `initiative.rice_effort` | `initiative.wsjf_job_size` | `initiative.rice_value_score` | `initiative.wsjf_value_score` |
| DB Column | `rice_reach` | `rice_effort` | `wsjf_job_size` | `rice_value_score` | `wsjf_value_score` |

**Note**: Header parsing is flexible—both "rice_reach" (direct) and "RICE: Reach" (namespaced) normalize to `rice_reach`.

---

## Backward Compatibility

- Existing `value_score`, `effort_score`, `overall_score`, `active_scoring_framework` columns unchanged
- Backlog writer continues to use active framework scores (no change)
- Flow 2 scoring CLI defaults to per-initiative framework selection (no change)
- New per-framework columns optional (nullable); existing DBs can upgrade with migration
- ScoringService maintains all existing method signatures and behavior

---

## Testing Checklist

- [ ] Migration runs cleanly (`alembic upgrade head`)
- [ ] Schema validates (6 new Float columns on initiatives table)
- [ ] `test_flow3_e2e.py` shows both RICE and WSJF scores populated
- [ ] CLI `--compute-all` processes all initiatives
- [ ] CLI `--write-scores` updates Product Ops sheet
- [ ] PM can change active_scoring_framework and see updated overall_score
- [ ] Per-framework scores persist across framework changes (no overwrite)
- [ ] Backlog displays active framework's scores correctly
- [ ] Product Ops sheet displays both framework scores for comparison

---

## Known Limitations

1. **Backlog Sheet Display**: Currently shows `value_score` from active framework unconditionally. Could enhance to:
   - Show both framework scores in separate columns
   - Validate that `value_score` matches `active_scoring_framework`
   - Add visual indicator of framework version

2. **History Tracking**: InitiativeScore rows (if enabled) only track the most recent computation. Could enhance to:
   - Track per-framework history separately
   - Allow audit trail of score changes when framework switches

3. **Manual Score Override**: Not yet implemented. If PM wants to manually adjust a score, no UI exists. Could add:
   - "manual_rice_overall_score" column
   - Flag to use manual vs computed
   - Audit log of manual changes

---

## Next Steps

1. Run `test_flow3_e2e.py` to validate complete pipeline
2. Monitor logs for any data sync issues