# KPI Contributions Complete Flow Analysis

#TODO: agent as pm

## FULL FLOW: Compute → Persist → Sheet Writeback

### Phase 1: COMPUTATION (Math Models → DB)
**File:** `app/services/product_ops/kpi_contribution_adapter.py`

1. **Function:** `compute_kpi_contributions(initiative: Initiative) -> Dict[str, float]`
   - Reads initiative's `active_math_models` (JSON field)
   - For each active math model:
     - Gets model from DB via `ScoringMathModel` table
     - Applies formula to initiative attributes
     - Produces KPI contribution value
   - Returns: `{"north_star_gmv": 100.0, "conversion_rate": 5.0, ...}`

2. **Persistence to DB:**
   - **Location:** `app/services/product_ops/scoring_service.py` → `score_initiatives()`
   - **Flow:**
     - Calls `compute_and_persist_kpi_contributions_for_batch()`
     - For each initiative:
       - Computes KPI contributions via `compute_kpi_contributions()`
       - Writes to `initiative.kpi_contribution_json` (JSON column)
       - Sets `initiative.kpi_contribution_computed_json` (backup of system computation)
       - Sets `initiative.kpi_contribution_source` = "math_model_derived"
       - Sets `initiative.updated_source` = provenance token
     - Commits to DB in batches

3. **Trigger:**
   - **Action:** `pm.score_selected` (Flow 2)
   - **Entry:** `app/services/action_runner.py` → `_action_pm_score_selected()`

---

### Phase 2: WRITEBACK TO PRODUCTOPS SHEET (DB → KPI_Contributions Tab)
**File:** `app/sheets/kpi_contributions_writer.py`

1. **Function:** `write_kpi_contributions_to_sheet()`
   - **Called by:** `_action_pm_score_selected()` step 3.5
   - **Triggered:** After scoring completes, writes KPI contributions to ProductOps sheet
   
2. **Columns Written:**
   - `initiative_key` (system)
   - `kpi_contribution_json` (PM can edit, preserved if exists)
   - `kpi_contribution_computed_json` (system-generated, always overwritten)
   - `kpi_contribution_source` ("math_model_derived" or "pm_override")
   - `run_status` (system)
   - `updated_source` (provenance token)
   - `updated_at` (timestamp)
   - `notes` (PM-editable, preserved)

3. **Upsert Logic:**
   - Reads existing sheet rows
   - For each initiative in DB:
     - If row exists: Update system columns, preserve PM columns
     - If new: Create new row with all columns
   - Batch writes to sheet

4. **Location in Code:**
   ```python
   # app/services/action_runner.py line ~836-855
   if cfg and hasattr(cfg, "kpi_contributions_tab"):
       kpi_tab = cfg.kpi_contributions_tab
       if kpi_tab:
           from app.sheets.kpi_contributions_writer import write_kpi_contributions_to_sheet
           kpi_contributions_written = write_kpi_contributions_to_sheet(
               db=db,
               client=client,
               spreadsheet_id=product_ops_config.sheet_id,
               tab_name=kpi_tab,
               initiative_keys=selected_keys,
           )
   ```

---

### Phase 3: OPTIMIZATION CENTER CANDIDATES TAB POPULATION (DB → Candidates Tab)
**File:** `app/sheets/optimization_candidates_writer.py`

1. **Function:** `populate_candidates_from_db()`
   - **Purpose:** Populates Candidates tab with initiative data + KPI contributions
   - **Trigger:** Manual action or optimization setup

2. **KPI Contribution Columns:**
   
   **A. `north_star_contribution` (single value):**
   - **Source:** `initiative.kpi_contribution_json` from DB
   - **Logic:**
     - Reads `kpi_contribution_json` (dict)
     - Queries `OrganizationMetricConfig` to find KPIs with `kpi_level='north_star'`
     - Extracts the one north_star KPI's contribution value
     - **Code:** Lines 214-243 of `optimization_candidates_writer.py`
     ```python
     north_star_kpis = []
     for kpi_key, contrib_val in kpi_json.items():
         kpi_level = kpi_level_map.get(kpi_key)  # from OrganizationMetricConfig
         if kpi_level == "north_star":
             north_star_kpis.append((kpi_key, contrib_val))
     
     if len(north_star_kpis) == 1:
         north_star_contrib = north_star_kpis[0][1]
     ```
   
   **B. `strategic_kpi_contributions` (JSON string):**
   - **Source:** `initiative.kpi_contribution_json` from DB
   - **Logic:**
     - Reads `kpi_contribution_json` (dict)
     - Queries `OrganizationMetricConfig` to find KPIs with `kpi_level='strategic'`
     - Extracts all strategic KPIs into a dict
     - Serializes to JSON string
     - **Code:** Lines 246-252
     ```python
     strategic_kpi_contribs = {}
     for kpi_key, contrib_val in strategic_kpis:
         strategic_kpi_contribs[kpi_key] = contrib_val
     
     strategic_kpi_json_str = json.dumps(strategic_kpi_contribs) if strategic_kpi_contribs else ""
     ```

3. **Column Ownership:**
   - **FORMULA COLUMNS (skip):** initiative_key, title, country, department
   - **PM INPUT COLUMNS (preserve for existing):** engineering_tokens, deadline_date, category, program_key, is_selected_for_run
   - **DB-DERIVED COLUMNS (always write):** 
     - ✅ `north_star_contribution`
     - ✅ `strategic_kpi_contributions`
   - **CONSTRAINT-DERIVED (always write):** is_mandatory, bundle_key, exclusion_keys, etc.
   - **STATUS COLUMNS (always write):** run_status, updated_source, updated_at

4. **Sheet Write Logic:**
   - For NEW initiatives: Write all columns (seed PM inputs from DB)
   - For EXISTING initiatives: Skip PM input columns, only update derived columns
   - **Code:** Lines 273-283
   ```python
   # DB-DERIVED COLUMNS - write always
   row_dict["north_star_contribution"] = north_star_contrib or ""
   row_dict["strategic_kpi_contributions"] = strategic_kpi_json_str
   ```

---

### Phase 4: OPTIMIZATION CENTER CANDIDATES TAB SYNC (Sheet → DB)
**File:** `app/services/optimization/optimization_sync_service.py`

1. **Function:** `sync_candidates_from_sheet()`
   - **Purpose:** Syncs PM edits from Candidates tab BACK to DB
   - **Direction:** Sheet → DB (REVERSE of populate)

2. **Fields Synced:**
   - ✅ `engineering_tokens`
   - ✅ `deadline_date`
   - ✅ `category`
   - ✅ `program_key`
   
   **NOT synced (sheet-only):**
   - ❌ `is_selected_for_run` (ephemeral selection state)
   - ❌ `notes` (sheet-only commentary)
   - ❌ `north_star_contribution` (derived, not persisted to DB)
   - ❌ `strategic_kpi_contributions` (derived, not persisted to DB)

3. **Important:** 
   - This function does NOT sync KPI contributions back to DB
   - KPI contributions flow one-way: DB → Sheet
   - PM cannot override KPI contributions via Candidates tab
   - To override KPIs, PM must edit KPI_Contributions tab in ProductOps sheet

4. **Code:** Lines 239-350 of `optimization_sync_service.py`
   ```python
   # Update DB-backed fields only
   if row.engineering_tokens is not None:
       setattr(initiative, "engineering_tokens", float(row.engineering_tokens))
   
   if row.deadline_date is not None:
       setattr(initiative, "deadline_date", datetime.fromisoformat(row.deadline_date).date())
   
   # ... category, program_key
   
   # KPI contributions are NOT synced here - they're derived from DB
   ```

---

## SUMMARY: Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. COMPUTATION (Math Models)                                    │
│    compute_kpi_contributions() → kpi_contribution_json (DB)     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. PRODUCTOPS SHEET WRITEBACK                                   │
│    write_kpi_contributions_to_sheet()                           │
│    → KPI_Contributions tab (initiative_key, kpi_contribution_json)│
└─────────────────────────────────────────────────────────────────┘
                             
                             
┌─────────────────────────────────────────────────────────────────┐
│ 3. OPTIMIZATION CENTER POPULATE                                 │
│    populate_candidates_from_db()                                │
│    DB: kpi_contribution_json (dict)                             │
│    ↓                                                             │
│    Sheet: north_star_contribution (float)                       │
│           strategic_kpi_contributions (JSON string)             │
└─────────────────────────────────────────────────────────────────┘
                             
                             
┌─────────────────────────────────────────────────────────────────┐
│ 4. OPTIMIZATION CENTER SYNC (PM Edits Back to DB)               │
│    sync_candidates_from_sheet()                                 │
│    Sheet → DB: engineering_tokens, deadline_date, category      │
│    NOT SYNCED: KPI contributions (derived from DB, read-only)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## KEY INSIGHTS FOR DEBUGGING

1. **KPI Contributions Source of Truth:** DB `initiative.kpi_contribution_json`
   
2. **KPI Contributions Flow Direction:** 
   - **Compute:** Math Models → DB
   - **ProductOps:** DB → KPI_Contributions tab (writeback)
   - **Optimization Candidates:** DB → Candidates tab (populate)
   - **Sync:** Candidates tab → DB (but NOT for KPI contributions)

3. **Critical Fields:**
   - `initiative.kpi_contribution_json` - Active contributions (can be PM override)
   - `initiative.kpi_contribution_computed_json` - System computation backup
   - `initiative.kpi_contribution_source` - "math_model_derived" or "pm_override"

4. **Sheet Column Derivation:**
   - `north_star_contribution`: Extracted from `kpi_contribution_json` by querying `OrganizationMetricConfig` for `kpi_level='north_star'`
   - `strategic_kpi_contributions`: JSON string of all strategic-level KPIs from `kpi_contribution_json`

5. **Why KPI Contributions Might Be Zero/Missing:**
   - ❌ Math models not active (`active_math_models` is empty/null)
   - ❌ Scoring not run (`pm.score_selected` action not triggered)
   - ❌ `kpi_contribution_json` is null/empty in DB
   - ❌ `OrganizationMetricConfig` missing KPI definitions
   - ❌ KPI keys don't match between math model output and OrganizationMetricConfig
   - ❌ `kpi_level` not set correctly (must be 'north_star' or 'strategic')
