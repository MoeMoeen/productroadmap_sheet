You're right — I'll stop iterating and just give you the content to paste. Plan: provide a concise, PM-ready cheatsheet covering all 4 jobs with what it does, before/after checklists, and quick tips.

**PM Jobs Cheatsheet — Roadmap AI (Phase 4.5 V2)**

**Overview**
- Run jobs from the Roadmap AI menu in Sheets.
- Selection-based unless noted; works on the rows you select.
- Status column shows OK/FAILED/SKIPPED; check it after each run.

**Job #1: See Latest Intake (pm.backlog_sync)**
- What: Sync department intake → DB → refresh Central Backlog.
- Use when: Start of week, before scoring, after teams submit.
- Before:
  - None — operates on all initiatives (no selection).
- After:
  - Check Central Backlog for new/updated rows.
  - Review Status for sync issues.
  - Confirm initiative_keys present.
- Notes:
  - Safe to run repeatedly (idempotent).
  - Typical runtime: 10–30s.

**Job #2: Score Selected Initiatives (pm.score_selected)**
- What: Sync inputs → compute RICE/WSJF/Math Model → write scores → Status.
- Use when: After editing scoring inputs, formulas, or params.
- Before:
  - Select rows with valid initiative_keys.
  - Fill required inputs:
    - RICE: reach, impact, confidence, effort.
    - WSJF: business_value, time_criticality, risk_reduction, job_size.
    - Math Model: use_math_model=TRUE, approved formula, params filled.
- After:
  - Check Status column for OK/errors.
  - Verify scores in rice_*, wsjf_*, math_*.
  - Review math_warnings if applicable.
- Notes:
  - Blank keys are skipped.
  - Typical runtime: 5–15s.

**Job #3: Switch Framework (pm.switch_framework)**
- What: Copy selected framework’s scores → active columns (value/effort/overall). Local-only.
- Use when: Compare frameworks; change which scores drive decisions.
- Before:
  - Select rows with valid initiative_keys.
  - Ensure target framework scores already computed.
  - Set active_scoring_framework (RICE/WSJF/MATH_MODEL).
- After:
  - Check active score columns updated.
  - Confirm Status shows OK; Updated Source refreshed.
- Notes:
  - No recompute; fast.
  - Does not affect other sheets until you sync.
  - Typical runtime: 3–10s.

**Job #4: Save Selected (pm.save_selected) — Tab-Aware**
- What: Persist edits from the current tab to DB. Same button, different meaning per tab:
  - Scoring_Inputs: saves scoring inputs.
  - MathModels: saves formulas/approval.
  - Params: saves parameter values.
  - Central Backlog: saves editable backlog fields.
- Use when: After making edits in any ProductOps tab.
- Before:
  - Select rows with valid initiative_keys.
  - Edit input fields only (not computed/output).
- After:
  - Check Status column for OK/errors.
  - Verify changes persisted.
  - If Params changed, re-run Score Selected to update scores.
- Notes:
  - Tab-aware routing; blank keys skipped.
  - Typical runtime: 5–15s.

**Job #5: Suggest Math Model (pm.suggest_math_model_llm)**
**What**: LLM suggests a formula and notes; writes only to `llm_suggested_formula_text` and `llm_notes` on MathModels (no DB writes). It never overwrites `formula_text`, `assumptions_text`, or `approved_by_user`.
- Use when: Initiative needs a math model draft; PM wants a starting point.
- Before:
  - Select rows on MathModels tab (blank keys skipped).
  - Ensure formula_text is empty (existing formulas are skipped).
  - Provide context: either initiative fields (problem_statement, expected_impact_description, impact_metric) or a custom `model_prompt_to_llm`. If neither exists, the job skips with an insufficient context status.
- After:
  - Review/edit suggestions in MathModels.
  - Set approved_by_user = TRUE before seeding params.
- Notes:
  - LLM call limit via options.max_llm_calls.
  - Status: OK suggested / SKIPPED existing formula / SKIPPED insufficient context / FAILED error.

**Job #6: Seed Math Params (pm.seed_math_params)**
- What: Validates approved formulas, extracts identifiers, seeds Params rows with LLM metadata (values empty).
- Use when: Math model formula is approved and ready for params.
- Before:
  - MathModels rows have formula_text and approved_by_user = TRUE.
  - Selection contains those initiatives.
- After:
  - New param rows appear on Params tab (fill values manually).
  - Then run pm.save_selected (Params) → pm.score_selected.
- Notes:
  - Sheet-only; DB persistence happens via pm.save_selected.
  - Status: OK seeded / SKIPPED not approved or missing formula / FAILED error.

**Status Column Legend**
- OK: success.
- FAILED: missing key — add initiative_key.
- FAILED: missing required field — fill inputs & save/score again.
- SKIPPED: no key — selection had blank/invalid keys.
- FAILED: sync/compute/write error — fix inputs or retry.

**Best Practices**
- Always select rows (except Backlog Sync).
- Save before scoring: Save Selected → Score Selected.
- One tab at a time; don’t switch mid-operation.
- Start with small batches (1–2 rows) to verify.
- Use Updated Source to confirm freshness.
- If Switch Framework didn’t update: compute scores first, then switch.
- For math models: Suggest → approve → Seed Params → fill values → Save (Params) → Score.

**Two-Step Math Model Workflow (summary)**
- **Suggest**: Run `pm.suggest_math_model_llm` on rows with empty `formula_text`. LLM writes to `llm_suggested_formula_text` + `llm_notes` and sets `suggested_by_llm`.
- **Approve & Seed**: Copy/edit into `formula_text` + `assumptions_text`, set `approved_by_user = TRUE`, then run `pm.seed_math_params` to create Params rows.

