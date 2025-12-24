Absolutely. Below are copy-paste Swagger request bodies you can use for POST /actions/run to test the whole loop (enqueue → worker executes → poll status).

Assumptions:

Your API is running and worker is running.

You’ll add the header in Swagger: X-ROADMAP-AI-SECRET: <your secret>

After each POST, copy the returned run_id, then call GET /actions/run/{run_id} repeatedly until status is success/failed.



---

0) Health check (optional)

GET /health


---

1) Flow 1 — Backlog sync (DB → Central Backlog)

Good “first smoke test” (no LLM, usually fast).

{
  "action": "flow1.backlog_sync",
  "scope": { "type": "all" },
  "sheet_context": {},
  "options": {},
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

2) Flow 0 — Intake sync (Intake sheets → DB)

Also a good early test (may take longer depending on sheet count).

{
  "action": "flow0.intake_sync",
  "scope": { "type": "all" },
  "sheet_context": {},
  "options": {
    "allow_status_override_global": false
  },
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

3) Flow 1 — Full sync (Intake → backlog update → backlog sync)

Only run this if you already fixed flow1.full_sync return shape (or you kept it as simple boolean result).

{
  "action": "flow1.full_sync",
  "scope": { "type": "all" },
  "sheet_context": {},
  "options": {
    "allow_status_override_global": false,
    "backlog_commit_every": 200,
    "product_org": null
  },
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

4) Flow 3 — Compute all frameworks (DB compute)

This will compute per-framework scores for all initiatives.

{
  "action": "flow3.compute_all_frameworks",
  "scope": { "type": "all" },
  "sheet_context": {},
  "options": {
    "commit_every": 100
  },
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

5) Flow 3 — Write scores to ProductOps Scoring_Inputs (DB → ProductOps)

If you don’t pass sheet_context, it falls back to settings.PRODUCT_OPS.

A) With explicit sheet_context (recommended)

{
  "action": "flow3.write_scores",
  "scope": { "type": "all" },
  "sheet_context": {
    "spreadsheet_id": "YOUR_PRODUCTOPS_SPREADSHEET_ID",
    "tab": "Scoring_Inputs"
  },
  "options": {},
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}

B) Without sheet_context (uses settings.PRODUCT_OPS)

{
  "action": "flow3.write_scores",
  "scope": { "type": "all" },
  "sheet_context": {},
  "options": {},
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

6) Flow 2 — Activate (AUTO)

Activates whatever each initiative has in active_scoring_framework (or default framework if set).

{
  "action": "flow2.activate",
  "scope": { "type": "all" },
  "sheet_context": {},
  "options": {
    "only_missing": true,
    "commit_every": 100
  },
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}

7) Flow 2 — Activate (force a framework for all)

Example: force MATH_MODEL everywhere.

{
  "action": "flow2.activate",
  "scope": { "type": "all" },
  "sheet_context": {},
  "options": {
    "framework": "MATH_MODEL",
    "only_missing": false,
    "commit_every": 100
  },
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

8) Flow 4 — Sync MathModels (Sheet → DB)

Reads MathModels tab and upserts into DB.

{
  "action": "flow4.sync_mathmodels",
  "scope": { "type": "all" },
  "sheet_context": {
    "spreadsheet_id": "YOUR_PRODUCTOPS_SPREADSHEET_ID",
    "tab": "MathModels"
  },
  "options": {
    "commit_every": 100
  },
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

9) Flow 4 — Sync Params (Sheet → DB)

{
  "action": "flow4.sync_params",
  "scope": { "type": "all" },
  "sheet_context": {
    "spreadsheet_id": "YOUR_PRODUCTOPS_SPREADSHEET_ID",
    "tab": "Params"
  },
  "options": {
    "commit_every": 200
  },
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

10) Flow 4 — Suggest MathModels (LLM, Sheet → Sheet)

Use with caution; it will call OpenAI. Make sure OPENAI_API_KEY is set.

{
  "action": "flow4.suggest_mathmodels",
  "scope": { "type": "all" },
  "sheet_context": {
    "spreadsheet_id": "YOUR_PRODUCTOPS_SPREADSHEET_ID",
    "tab": "MathModels"
  },
  "options": {
    "limit": 20,
    "force": false,
    "max_llm_calls": 3
  },
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

11) Flow 4 — Seed Params (LLM metadata, MathModels → Params)

Also uses OpenAI.

{
  "action": "flow4.seed_params",
  "scope": { "type": "all" },
  "sheet_context": {
    "spreadsheet_id": "YOUR_PRODUCTOPS_SPREADSHEET_ID",
    "tab": "MathModels"
  },
  "options": {
    "mathmodels_tab": "MathModels",
    "params_tab": "Params",
    "limit": 20,
    "max_llm_calls": 3
  },
  "requested_by": { "ui": "swagger", "user_email": "test@example.com" }
}


---

How to verify the worker actually executed

1. POST /actions/run → you get run_id


2. GET /actions/run/{run_id} every 1–2 seconds:

should go: queued → running → success/failed



3. On success, check:

result_json is present (and your raw/summary wrapper if you enabled it)



4. On failure, check:

error_text has traceback (truncated)





---

Suggested test order (fast → risky)

1. flow1.backlog_sync


2. flow0.intake_sync


3. flow3.compute_all_frameworks


4. flow2.activate


5. flow3.write_scores


6. flow4.sync_mathmodels


7. flow4.sync_params


8. flow4.suggest_mathmodels (LLM)


9. flow4.seed_params (LLM)



If you paste one run_id response + the subsequent GET response, I can help you interpret the result and spot any mismatches immediately.