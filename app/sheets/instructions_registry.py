# productroadmap_sheet_project/app/sheets/instructions_registry.py
"""Registry of per-tab instruction copy for system-managed instruction rows.

This keeps the UI text in-source (per sheet type + tab) so we can render
instructions deterministically onto sheets without manual edits.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


logger = logging.getLogger("app.sheets.instructions_registry")


def _normalize_tab_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


@dataclass(frozen=True)
class TabInstructions:
    tab_name: str  # Exact Google Sheet tab name
    title: str     # Display title inside the instructions text
    lines: Tuple[str, ...]  # Brief overview of the tab's purpose
    steps: Tuple[str, ...] = ()  # Step-by-step walkthrough for PMs
    actions: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()


SheetType = str
TabName = str

# Registry key = (sheet_type, tab_name_lower)
INSTRUCTIONS_REGISTRY: Dict[Tuple[SheetType, TabName], TabInstructions] = {
    # ──────────────────────────────────────────────────────────────────────────
    # OPTIMIZATION CENTER SHEET
    # ──────────────────────────────────────────────────────────────────────────
    ("optimization_center", "settings"): TabInstructions(
        tab_name="Settings",
        title="Settings",
        lines=(
            "Key-value configuration that menu actions read on each run.",
            "No Save required — changes take effect immediately.",
        ),
        steps=(
            "1. Set 'current_scenario_name' to match a scenario row in Scenario_Config (e.g., 'Q2_2026_Plan').",
            "2. Set 'current_constraint_set_name' to match a set in Constraints/Targets (e.g., 'Baseline').",
            "3. Changes take effect immediately — no Save needed.",
            "4. Menu actions (Populate, Optimize, Explain) will read these values.",
            "5. To switch scenarios: update values here → run Populate Candidates on Candidates tab.",
            "6. Optionally run 'Refresh Instructions' from menu to update instruction rows across all tabs.",
        ),
        actions=("pm.refresh_sheet_instructions",),
    ),
    ("optimization_center", "candidates"): TabInstructions(
        tab_name="Candidates",
        title="Candidates",
        lines=(
            "Initiatives eligible for consideration for optimization.",
            "Core data (initiative_key, title, country, department, lifecycle_status) references Central Backlog via formula — read-only.",
            "PM editable: is_selected_for_run, category, program_key, engineering_tokens, deadline_date, notes.",
            "Constraint columns (is_mandatory, bundle_key, etc.) are DERIVED from Constraints tab — read-only.",
            "KPI contribution columns (J-K) are display-only — populated by 'Populate Candidates' from DB; entry surface is ProductOps/KPI_Contributions.",
        ),
        steps=(
            "1. Verify Settings tab has correct scenario_name and constraint_set_name.",
            "2. Run 'Populate Candidates' from menu — pulls KPI contributions + constraint data into read-only columns.",
            "3. Review formula columns (auto-populated, read-only): initiative_key (A), title (C), country (D), department (E), lifecycle_status (U), active_scoring_framework (R), active_overall_score (S).",
            "4. Review KPI contributions (J-K) — populated by 'Populate Candidates' from Initiative.kpi_contribution_json:",
            "   - north_star_contribution (J): extracted from kpi_contribution_json where kpi_level='north_star'.",
            "   - strategic_kpi_contributions (K): JSON of all kpi_level='strategic' contributions.",
            "   - To update: edit ProductOps/KPI_Contributions tab → Save → re-run 'Populate Candidates' here.",
            "5. Review constraint columns (L-Q) — is_mandatory, bundle_key, prerequisite_keys, exclusion_keys, synergy_group_keys — read-only, populated by 'Populate Candidates'.",
            "6. Fill PM editable fields: is_selected_for_run (B), category (F), program_key (G), engineering_tokens (H), deadline_date (I), notes (V).",
            "7. Run 'Save' from menu to persist PM edits (engineering_tokens, deadline_date) to DB.",
            "8. Mark 'is_selected_for_run' = TRUE for initiatives to include in optimization.",
            "9. Run 'Optimize Selected' (marked rows only) or 'Optimize All' (entire scenario) from menu.",
            "10. After run: check Results tab for selected portfolio, Gaps_and_Alerts for unmet targets.",
            "11. Optionally run 'Explain Selection' from menu for AI-powered analysis of selections.",
        ),
        actions=(
            "pm.populate_candidates",
            "pm.save_optimization",
            "pm.optimize_run_selected_candidates",
            "pm.optimize_run_all_candidates",
            "pm.explain_selection",
        ),
        warnings=(
            "Formula columns A, C-E, R-U are read-only — do not edit.",
            "Constraint columns L-Q are populated by 'Populate Candidates' — do not edit directly; edit in Constraints tab.",
            "KPI contributions (J-K) are populated by 'Populate Candidates' — do not edit directly; edit in ProductOps/KPI_Contributions tab.",
        ),
    ),
    ("optimization_center", "scenario_config"): TabInstructions(
        tab_name="Scenario_Config",
        title="Scenario_Config",
        lines=(
            "Define optimization scenario parameters: capacity, objective mode, weights.",
            "Each row = one scenario. scenario_name must match Settings tab.",
        ),
        steps=(
            "1. Create a new row with 'scenario_name' (e.g., 'Q2_2026_Plan'). PM input → DB.",
            "2. Set 'period_key' if using time-bounded capacity (e.g., '2026-Q2'). PM input → DB.",
            "3. Set 'capacity_total_tokens' — total engineering capacity (story points / person-days). PM input → DB.",
            "4. Set 'objective_mode': 'north_star', 'weighted_kpis', or 'lexicographic'. PM input → DB.",
            "5. For 'weighted_kpis': set 'objective_weights_json' = {\"north_star_gmv\": 0.6, \"user_nps\": 0.4}. PM input → DB.",
            "6. Add 'notes' for documentation. PM input → DB.",
            "7. Run 'Save' from menu to persist scenario to DB.",
            "8. Update Settings tab: set 'current_scenario_name' to match this scenario.",
            "9. Go to Candidates tab → run 'Populate Candidates' → then run optimization.",
        ),
        actions=("pm.save_optimization",),
        warnings=(
            "objective_weights_json keys must match kpi_key values in ProductOps/Metrics_Config.",
            "For north_star mode: exactly one metric must have kpi_level='north_star' and is_active=TRUE in Metrics_Config.",
        ),
    ),
    ("optimization_center", "constraints"): TabInstructions(
        tab_name="Constraints",
        title="Constraints",
        lines=(
            "AUTHORITATIVE entry surface for all optimization constraints.",
            "Scope: rows must specify scenario_name + constraint_set_name.",
            "Types: mandatory, bundle, exclusion, prerequisite, capacity_floor, capacity_cap.",
        ),
        steps=(
            "1. Create constraint rows scoped to your scenario_name + constraint_set_name (must match Settings tab).",
            "2. Set 'constraint_type' and fill relevant columns based on type:",
            "   - MANDATORY: constraint_type='mandatory', dimension='initiative', dimension_key='INIT-XXX'.",
            "   - BUNDLE: constraint_type='bundle', dimension_key='BUNDLE-NAME', bundle_member_keys='INIT-1,INIT-2,INIT-3'.",
            "   - EXCLUSION: constraint_type='exclusion_initiative' or 'exclusion_pair' with initiative keys.",
            "   - PREREQUISITE: constraint_type='prerequisite', dimension_key='DEPENDENT-INIT', prereq_member_keys='REQUIRED-INIT'.",
            "   - CAPACITY_FLOOR: constraint_type='capacity_floor', dimension='country'/'department', dimension_key='UK', min_tokens=200.",
            "   - CAPACITY_CAP: constraint_type='capacity_cap', dimension='department', dimension_key='Platform', max_tokens=400.",
            "3. Add 'notes' for documentation. PM input → DB.",
            "4. Optionally run 'Save' from menu to validate and persist constraints to DB immediately.",
            "5. Go to Candidates tab → run 'Populate Candidates' to pull constraint data into Candidates columns (L-Q).",
            "6. Note: Optimization auto-syncs — when you run 'Optimize Selected/All' from Candidates, backend reads Constraints + Targets tabs and syncs to DB before solver runs (no manual Save required).",
        ),
        actions=("pm.save_optimization",),
        warnings=(
            "Initiative keys must exist in Candidates. Invalid keys cause validation errors on run.",
            "Conflicting constraints (e.g., mandatory + exclusion) will cause infeasible solver results.",
            "After editing constraints: run 'Populate Candidates' on Candidates tab to refresh derived columns.",
        ),
    ),
    ("optimization_center", "targets"): TabInstructions(
        tab_name="Targets",
        title="Targets",
        lines=(
            "Define KPI targets (floors and goals) for the solver to enforce or optimize toward.",
            "constraint_set_name → formula from Constraints (read-only). scenario_name → formula from Scenario_Config (read-only).",
            "Targets can be global or per-dimension (country, product, etc.).",
            "Supports both INCREMENTAL targets (default) and ABSOLUTE targets (when baseline_value provided).",
        ),
        steps=(
            "1. Review formula columns (auto-populated, read-only): constraint_set_name (A), scenario_name (B).",
            "2. Create target rows with PM input fields:",
            "   - 'dimension' (C): 'all' for global, or 'country'/'product' for dimensional. PM input → DB.",
            "   - 'dimension_key' (D): 'all' for global, or specific key like 'UK', 'Payments'. PM input → DB.",
            "   - 'kpi_key' (E): must match a metric in ProductOps/Metrics_Config. PM input → DB.",
            "   - 'baseline_value' (H): OPTIONAL current KPI value. If provided, target_value is absolute. PM input → DB.",
            "   - 'target_value' (G): numeric threshold (see baseline logic below). PM input → DB.",
            "   - 'floor_or_goal' (F): 'floor' = hard minimum, 'goal' = optimization target. PM input → DB.",
            "3. Add 'notes' (I) for documentation. PM input → DB.",
            "4. BASELINE LOGIC — two modes:",
            "   - WITHOUT baseline_value: target_value is INCREMENTAL (e.g., 'need +50k revenue from initiatives').",
            "   - WITH baseline_value: target_value is ABSOLUTE (e.g., 'Q2 revenue = 100k'). Solver computes gap = target - baseline.",
            "5. EXAMPLE:",
            "   - Row A: kpi=revenue, baseline=50000, target=100000, floor_or_goal=floor → requires +50k delta from initiatives.",
            "   - Row B: kpi=diners, baseline=(empty), target=10000, floor_or_goal=floor → requires +10k delta (incremental).",
            "6. Optionally run 'Save' from menu to validate and persist targets to DB immediately.",
            "7. Note: Optimization auto-syncs — when you run 'Optimize Selected/All' from Candidates, backend reads Constraints + Targets tabs and syncs to DB before solver runs (no manual Save required).",
            "8. Go to Candidates tab → run optimization.",
            "9. After run: check Gaps_and_Alerts tab to see if targets were met or missed.",
        ),
        actions=("pm.save_optimization",),
        warnings=(
            "Columns A-B are formula references — do not edit directly.",
            "Floor targets are hard constraints — unsatisfiable floors cause infeasible results.",
            "Use 'goal' for aspirational targets the solver should maximize but not require.",
            "When using baseline_value, ensure it reflects the CURRENT state at the start of the planning period.",
            "Normalization (weighted_kpis mode): uses gap (target - baseline) as scale when baseline provided.",
        ),
    ),
    ("optimization_center", "runs"): TabInstructions(
        tab_name="Runs",
        title="Runs",
        lines=(
            "System audit log of optimization runs. ALL columns are Backend writes → Sheet.",
            "Each row = one optimization execution. Entirely read-only.",
        ),
        steps=(
            "1. This tab is entirely system-generated — no PM input or actions available here.",
            "2. After running optimization from Candidates tab, review run history here.",
            "3. Check 'optimization_db_status': 'completed' = success, 'failed' = errors.",
            "4. Review run metrics: 'selected_count', 'capacity_used', 'total_objective_raw'.",
            "5. Use 'run_id' to filter Results and Gaps_and_Alerts tabs for that specific run.",
            "6. Compare runs across different scenarios or constraint sets.",
            "7. To trigger new runs: go to Candidates tab → run 'Optimize Selected' or 'Optimize All'.",
        ),
        warnings=(
            "ALL columns are Backend writes → Sheet. Do not edit any rows.",
            "To trigger new runs: use menu actions from Candidates tab.",
        ),
    ),
    ("optimization_center", "results"): TabInstructions(
        tab_name="Results",
        title="Results",
        lines=(
            "System output showing which initiatives were selected per run.",
            "All columns are Backend writes → Sheet, except 'notes' (PM input → DB).",
        ),
        steps=(
            "1. This tab is system-generated after each optimization run — review results here.",
            "2. Filter by 'run_id' to see one run's selections.",
            "3. Review system-generated columns (read-only): initiative_key, selected, allocated_tokens, objective_contribution, north_star_gain, country, department, etc.",
            "4. Optionally add 'notes' (P) — only PM-editable field. PM input → DB.",
            "5. Run 'Save' from menu if you added notes.",
            "6. Compare runs to see how constraint changes affect the selected portfolio.",
            "7. Export this tab to stakeholders as your recommended roadmap.",
            "8. To change selections: go to Constraints tab → edit → Save → go to Candidates tab → run 'Populate Candidates' → re-run optimization.",
        ),
        actions=("pm.save_optimization",),
        warnings=(
            "All columns except 'notes' are Backend writes → Sheet — do not edit.",
            "To change selections: adjust constraints in Constraints tab → re-run optimization.",
        ),
    ),
    ("optimization_center", "gaps_and_alerts"): TabInstructions(
        tab_name="Gaps_and_Alerts",
        title="Gaps & Alerts",
        lines=(
            "System diagnostics showing unmet targets or cap violations.",
            "ALL columns are Backend writes → Sheet. Entirely read-only.",
        ),
        steps=(
            "1. This tab is system-generated after each optimization run — check for gaps here.",
            "2. Filter by 'run_id' to see gaps for a specific run.",
            "3. Review: 'dimension', 'dimension_key' to identify which constraint/target missed.",
            "4. Common fixes: relax constraints in Constraints tab, add higher-scoring initiatives, increase capacity in Scenario_Config.",
            "5. Go to Candidates tab → run 'Explain Selection' from menu for AI-powered analysis.",
            "6. After adjustments: go to Candidates tab → run 'Populate Candidates' → re-run optimization.",
        ),
        actions=("pm.explain_selection",),
        warnings=(
            "ALL columns are Backend writes → Sheet. Do not edit any rows.",
            "To fix gaps: edit Constraints/Targets/Scenario_Config → re-run optimization from Candidates tab.",
        ),
    ),

    # ──────────────────────────────────────────────────────────────────────────
    # PRODUCT OPS SHEET
    # ──────────────────────────────────────────────────────────────────────────
    ("product_ops", "scoring_inputs"): TabInstructions(
        tab_name="Scoring_Inputs",
        title="Scoring_Inputs",
        lines=(
            "Primary scoring surface. First populate candidate initiatives, then fill framework inputs, run scoring, and compare results.",
            "initiative_key (A) is system-managed and appended from DB by 'Populate Initiatives' — read-only.",
            "Framework inputs (RICE: M-P, WSJF: Q-T) = PM input → DB.",
            "Score columns (F-L, U-Z) = Backend writes — read-only.",
        ),
        steps=(
            "1. If this tab is empty or missing initiatives, run 'Populate Initiatives' from this tab. It appends active optimization candidates from DB.",
            "2. Review system-managed initiative_key column (A). Do not edit it manually.",
            "3. Set 'active_scoring_framework' (C): 'RICE', 'WSJF', or 'MATH_MODEL'. PM input → DB.",
            "4. Set 'use_math_model' (D) = TRUE if using math model scoring. PM input → DB.",
            "5. Fill RICE inputs (M-P): rice_reach, rice_impact, rice_confidence, rice_effort. PM input → DB.",
            "6. Fill WSJF inputs (Q-T): wsjf_business_value, wsjf_time_criticality, wsjf_risk_reduction, wsjf_job_size. PM input → DB.",
            "7. Select rows → run 'Save selected rows' from menu to persist inputs to DB.",
            "8. Run 'Score selected initiatives' from menu — backend computes all frameworks, writes to score columns.",
            "9. Review score columns (read-only): active score columns (F-H), math_*_score (I-K), rice_*_score (U-W), wsjf_*_score (X-Z).",
            "10. Optionally run 'Switch scoring framework' from menu to change which framework's scores are active.",
            "11. For Math Model scoring: first complete MathModels tab → Params tab workflow, then return here and run 'Score selected initiatives'.",
            "12. KPI CONTRIBUTIONS: When scoring with MATH_MODEL framework, 'Score selected initiatives' also computes KPI contributions:",
            "    - Each model's computed_score is aggregated by target_kpi_key into kpi_contribution_computed_json.",
            "    - Results are written to KPI_Contributions tab automatically after scoring completes.",
            "    - Only MATH_MODEL scoring triggers this — RICE/WSJF do not produce KPI contributions.",
        ),
        actions=("pm.populate_initiatives", "pm.save_selected", "pm.score_selected", "pm.switch_framework"),
        warnings=(
            "Column A (initiative_key) is system-managed — do not edit.",
            "Only initiatives marked 'Is Optimization Candidate' = TRUE in Central Backlog are eligible for 'Populate Initiatives'.",
            "Score columns (F-L, U-Z) are Backend writes — do not edit.",
            "For Math Model: complete MathModels → Params workflow first, then return here to score.",
            "KPI contributions only computed for MATH_MODEL framework — RICE/WSJF scoring does not populate KPI_Contributions.",
        ),
    ),
    ("product_ops", "mathmodels"): TabInstructions(
        tab_name="MathModels",
        title="MathModels",
        lines=(
            "Define custom math formulas for initiative-level scoring.",
            "initiative_key (A) identifies the initiative being modeled. Use an existing keyed row or copy the key from Scoring_Inputs/Central Backlog.",
            "PM inputs: model_name, target_kpi_key, metric_chain_text, formula_text, assumptions_text, approved_by_user.",
            "LLM columns (I, M-N) = LLM writes — read-only (PM may copy approved suggestions).",
            "computed_score = Backend writes — auto-populated after 'Score selected initiatives' runs on Scoring_Inputs.",
        ),
        steps=(
            "1. Start with the correct initiative_key in column A. Reuse an existing keyed row or copy the key from Scoring_Inputs/Central Backlog.",
            "2. Create model row with PM inputs:",
            "   - 'model_name' (C): unique name for this model. PM input → DB.",
            "   - 'target KPI key' (B): which KPI this formula impacts (must match Metrics_Config). PM input → DB.",
            "   - 'metric_chain_text' (F): impact pathway description using arrows, e.g., 'signup → activation → revenue'. PM input → DB.",
            "   - 'immediate KPI key' (G): optional immediate metric. PM input → DB.",
            "   - 'is_primary' (E): TRUE if this is the representative model for the initiative (only 1 per initiative).",
            "3. OPTION A — Manual formula: Write formula in 'formula_text' (J), e.g., 'reach * conversion_rate * aov'. PM input → DB.",
            "4. OPTION B — LLM suggestion: Run 'Suggest math model (LLM)' from menu.",
            "5. Review LLM columns (read-only): 'llm_suggested_formula_text' (M), 'llm_suggested_metric_chain_text' (I), 'llm_notes' (N).",
            "6. If LLM suggestion is good: copy to 'formula_text' (J), 'metric_chain_text' (F), 'assumptions_text' (O). PM input → DB.",
            "7. Set 'approved_by_user' (L) = TRUE to approve formula. PM input → DB.",
            "8. Select rows → run 'Save selected rows' from menu to persist to DB.",
            "9. Run 'Seed math params' from menu — extracts variables from formula → creates rows in Params tab.",
            "10. Go to Params tab → fill parameter values → Save → return to Scoring_Inputs → run 'Score selected initiatives'.",
            "11. COMPUTED SCORE WRITEBACK: After 'Score selected initiatives' runs with MATH_MODEL framework:",
            "    - Backend computes each model's score using formula_text + param values.",
            "    - 'computed_score' column is auto-populated for each model row (Backend writes → Sheet).",
            "    - Multiple models per initiative allowed — each gets its own computed_score.",
            "    - If active_scoring_framework='MATH_MODEL', the primary model's score is copied into the active score columns on Scoring_Inputs.",
        ),
        actions=("pm.suggest_math_model_llm", "pm.seed_math_params", "pm.save_selected"),
        warnings=(
            "Column A (initiative_key) must reference a real initiative key from Scoring_Inputs or Central Backlog.",
            "LLM columns I, M-N are LLM writes — do not edit (copy suggestions to PM columns).",
            "computed_score column is Backend writes — do not edit (auto-populated after scoring).",
            "approved_by_user must be TRUE before running 'Seed math params'.",
            "Only one model per initiative should have is_primary=TRUE — system enforces uniqueness.",
        ),
    ),
    ("product_ops", "params"): TabInstructions(
        tab_name="Params",
        title="Params",
        lines=(
            "Parameter values for math model formulas.",
            "initiative_key → auto-seeded by backend OR PM copies via formula. param_name → Backend seeded / PM edits → DB.",
            "value → PM input → DB. is_auto_seeded → Backend sets.",
        ),
        steps=(
            "1. After running 'Seed math params' from MathModels tab, rows appear here for each formula variable.",
            "2. Review auto-seeded columns (read-only where indicated):",
            "   - 'initiative_key' (A): auto-seeded by backend or PM copies via formula.",
            "   - 'framework' (B): set by backend to 'MATH_MODEL' for auto-seeded rows.",
            "   - 'model name' (C): set by backend to match MathModels.model_name (read-only).",
            "   - 'param_name' (D): variable name from formula (Backend seeded).",
            "   - 'is_auto_seeded' (G): TRUE if auto-seeded (Backend sets, read-only).",
            "3. Fill PM input fields:",
            "   - 'value' (E): numeric value for this parameter. PM input → DB. REQUIRED.",
            "   - 'approved' (F): TRUE to approve param. PM input → DB.",
            "   - 'param_display' (H), 'description' (I), 'unit' (J): documentation. PM input → DB.",
            "   - 'min' (K), 'max' (L): optional validation bounds. PM input → DB.",
            "   - 'source' (M), 'notes' (N): optional documentation. PM input → DB.",
            "4. Select rows → run 'Save selected rows' from menu to persist to DB.",
            "5. Go to Scoring_Inputs tab → run 'Score selected initiatives' to compute formula with your values.",
        ),
        actions=("pm.save_selected",),
        warnings=(
            "param_name must match variable names in your formula exactly.",
            "Missing or null 'value' causes formula evaluation to fail or use defaults.",
            "is_auto_seeded and model name are Backend-set — do not edit.",
        ),
    ),
    ("product_ops", "metrics_config"): TabInstructions(
        tab_name="Metrics_Config",
        title="Metrics_Config",
        lines=(
            "Define organization KPIs: north_star, strategic metrics.",
            "All config columns → PM input → DB. Status columns (run_status, updated_source, updated_at) → Backend writes.",
        ),
        steps=(
            "1. Create rows for your org's KPIs (one row per metric). PM inputs:",
            "   - 'kpi_key' (A): unique identifier (e.g., 'north_star_gmv', 'user_nps'). PM input → DB.",
            "   - 'kpi_name' (B): human-readable name. PM input → DB.",
            "   - 'kpi_level' (C): 'north_star' (exactly one required) or 'strategic'. PM input → DB.",
            "   - 'unit' (D): e.g., '$', '%', 'count'. PM input → DB.",
            "   - 'description' (E): explanation of the KPI. PM input → DB.",
            "   - 'is_active' (F): TRUE to include in scoring/optimization. PM input → DB.",
            "   - 'notes' (G): optional documentation. PM input → DB.",
            "2. Select rows → run 'Save Selected' from menu to persist to DB.",
            "3. Review status columns (read-only): run_status (H), updated_source (I), updated_at (J).",
            "4. KPI keys are referenced by: MathModels.target_kpi_key, Optimization/Targets.kpi_key, Scenario_Config.objective_weights_json.",
            "5. For optimization: north_star mode requires exactly one KPI with kpi_level='north_star' and is_active=TRUE.",
        ),
        actions=("pm.save_selected",),
        warnings=(
            "Exactly one KPI must have kpi_level='north_star' and is_active=TRUE for north_star optimization mode.",
            "kpi_key values are referenced by other tabs — changing them requires updating all references.",
            "Status columns (H-J) are Backend writes — do not edit.",
        ),
    ),
    ("product_ops", "kpi_contributions"): TabInstructions(
        tab_name="KPI_Contributions",
        title="KPI_Contributions",
        lines=(
            "AUTHORITATIVE entry surface for per-initiative KPI contributions.",
            "initiative_key (A) = system-managed (backend syncs) — do not edit.",
            "PM edits: kpi_contribution_json (B). System displays: kpi_contribution_computed_json (C), kpi_contribution_source (D).",
            "Values entered here flow to Optimization/Candidates tab (north_star_contribution, strategic_kpi_contributions).",
        ),
        steps=(
            "1. HOW THIS TAB GETS POPULATED: Run 'Score selected initiatives' on Scoring_Inputs tab with MATH_MODEL framework.",
            "   - Scoring computes each math model's computed_score.",
            "   - Scores are aggregated by target_kpi_key into kpi_contribution_computed_json.",
            "   - Backend writes results to this tab automatically after scoring completes.",
            "   - Note: Only MATH_MODEL scoring produces KPI contributions — RICE/WSJF do not.",
            "2. Review system-managed column (read-only): initiative_key (A) — always updated by backend.",
            "3. Review system-computed columns (read-only):",
            "   - 'kpi_contribution_computed_json' (C): computed from math models after scoring.",
            "   - 'kpi_contribution_source' (D): 'computed' (system) or 'pm_override' (manual).",
            "4. To override system values: edit 'kpi_contribution_json' (B) — JSON of {kpi_key: value}. PM input → DB.",
            "   Example: {\"north_star_gmv\": 50000, \"user_nps\": 8.5}",
            "5. Add 'notes' (E) for documentation. Sheet-only.",
            "6. Select rows → run 'Save selected rows' from menu to persist to DB.",
            "7. PM override sets source='pm_override' — blocks future system updates to that row.",
            "8. To re-enable system updates: clear kpi_contribution_json (B) or set source='computed' → Save.",
            "9. After saving: contributions appear in Optimization/Candidates tab (J-K, display-only there).",
        ),
        actions=("pm.save_selected",),
        warnings=(
            "Column A (initiative_key) is system-managed — do not edit.",
            "kpi_key values in JSON must match Metrics_Config exactly. Invalid keys are dropped.",
            "PM edits to kpi_contribution_json (B) set source='pm_override' — blocks system updates.",
            "This is the ENTRY SURFACE for KPI contributions — Optimization/Candidates tab shows read-only view.",
            "KPI contributions only computed when scoring with MATH_MODEL framework on Scoring_Inputs tab.",
        ),
    ),
    ("product_ops", "config"): TabInstructions(
        tab_name="Config",
        title="Config",
        lines=(
            "Sheet-level configuration (reserved for future use).",
            "Currently unused — configuration is managed via backend settings.",
        ),
        steps=(
            "1. This tab is reserved for future PM-editable configuration.",
            "2. No actions required at this time.",
            "3. Sheet-wide settings are currently managed via backend configuration.",
        ),
    ),
    # ──────────────────────────────────────────────────────────────────────────
    # CENTRAL BACKLOG SHEET
    # ──────────────────────────────────────────────────────────────────────────
    ("central_backlog", "backlog"): TabInstructions(
        tab_name="Backlog",
        title="Central Backlog",
        lines=(
            "Single source of truth for all initiatives across departments.",
            "Consolidated from intake sheets → DB → this sheet via pm.backlog_sync.",
            "BIDIRECTIONAL: PM edits flow to DB via pm.save_selected; backend writes refresh via pm.backlog_sync.",
            "Archived initiatives are included by default during sync; callers may explicitly exclude them when needed.",
            "PMs can freely add formula/helper columns and reorder columns — backend matches by header name.",
        ),
        steps=(
            "1. Run 'Sync intake → backlog' from Roadmap AI menu to sync all intake sheets → DB → this sheet.",
            "2. Review initiative data: core fields, scores, dependencies, candidacy status, and Intake Source if that column exists.",
            "3. Edit PM-owned fields directly: Title, Department, Country, Product Area, Lifecycle Status, etc.",
            "4. Edit strategic fields: Hypothesis, Problem Statement, LLM Summary, Strategic Priority Coefficient.",
            "5. Set 'Active Scoring Framework' to choose which framework's scores display (RICE, WSJF, MATH_MODEL).",
            "6. Toggle 'Use Math Model' for initiatives that should use formula-based scoring.",
            "7. Adjust 'Strategic Priority Coefficient' to up/down-weight initiatives (default=1.0).",
            "8. Mark 'Is Optimization Candidate' = TRUE for initiatives eligible for portfolio optimization.",
            "9. Set 'Candidate Period Key' to group initiatives into planning periods (e.g., 'Q2_2026').",
            "10. Select rows → run 'Save selected rows' from Roadmap AI menu to persist PM edits to DB.",
            "11. Run 'Switch scoring framework' to activate a different scoring framework's scores.",
            "DATA FLOWS:",
            "- 'Sync intake → backlog' (pm.backlog_sync): intake sheets → DB → this sheet. Backend-owned columns are refreshed from DB; helper/formula columns you add are preserved.",
            "- 'Save selected rows' (pm.save_selected): Sheet → DB. Syncs PM-editable fields to DB.",
            "- 'Switch scoring framework' (pm.switch_framework): Writes active score columns only.",
        ),
        actions=(
            "pm.backlog_sync",
            "pm.save_selected",
            "pm.switch_framework",
        ),
        warnings=(
            "'Initiative Key' is system-generated — do not edit.",
            "Score columns (Value Score, Effort Score, Overall Score) are computed by backend — do not edit directly.",
            "'Updated At' and 'Updated Source' are system-managed provenance — do not edit.",
            "'Intake Source', 'Is Archived', 'Archived At', and 'Archived Reason' are display/provenance fields written from DB — do not edit.",
            "'Immediate KPI Key' is written by pm.backlog_sync from DB — entry surface is ProductOps/MathModels.",
            "'Metric Chain JSON (Primary)' is written by pm.backlog_sync from DB (primary MathModel) — entry surface is ProductOps/MathModels.",
            "Formula columns (e.g., engineering_tokens, deadline_date, is_mandatory) are PM-managed — backend ignores them.",
            "Column order doesn't matter — backend matches by header name, not position.",
            "PM edits NOT persisted until you run 'Save selected rows' — pm.backlog_sync may overwrite unsaved edits.",
        ),
    ),
}


def get_tab_instructions(sheet_type: str, tab_name: str) -> Optional[TabInstructions]:
    key = (_normalize_tab_key(sheet_type), _normalize_tab_key(tab_name))
    return INSTRUCTIONS_REGISTRY.get(key)


def validate_registry(strict: Optional[bool] = None) -> None:
    """Dev-time guard to catch typos/alias mismatches early.

    strict=None → decide based on ENV (default strict for dev/test, soft for prod).
    """
    if strict is None:
        env = "dev"
        try:
            from app.config import settings  # local import to avoid cycles
            env = (settings.ENV or "dev").strip().lower()
        except Exception:
            pass
        strict = env in {"dev", "test", "ci", "local"}

    errors = []
    for (stype, tab_key), ins in INSTRUCTIONS_REGISTRY.items():
        tn = (ins.tab_name or "").strip()
        if not tn:
            errors.append(f"TabInstructions missing tab_name for sheet_type={stype}, key={tab_key}")
            continue
        norm_tn = _normalize_tab_key(tn)
        if tab_key != norm_tn:
            errors.append(
                f"Registry key tab '{tab_key}' does not match tab_name '{ins.tab_name}' (norm='{norm_tn}') for sheet_type={stype}"
            )

    if errors:
        msg = "; ".join(errors)
        if strict:
            raise ValueError(msg)
        logger.error("instructions_registry.validation_failed", extra={"errors": errors})


# Run validation at import time to avoid silent skips in refresh actions.
validate_registry()
