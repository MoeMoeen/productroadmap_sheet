# Provenance Tokens

Simple, consistent tokens to mark who last wrote where across all flows and sheets. Use them in two places:
- **DB**: `Initiative.updated_source` (last writer of the initiative row in DB), plus `Initiative.scoring_updated_source` / `scoring_updated_at` for scoring/activation operations only.
- **Sheets**: each tab's "Updated Source" column = last writer of that tab's rows.

## Key distinction: "READ" tokens mean "sheet → DB sync" (not just reading)

When we say `flow3.productopssheet_read_inputs`, it means the ProductOps sheet was **read and values were synced into the DB**. This is the sheet-to-DB direction of data movement.

## Canonical tokens (enum `Provenance`)
- `flow0.intake_sync` — Intake sheet → DB
- `flow1.backlogsheet_read` — Central Backlog sheet → DB (sheet row changes synced to DB)
- `flow1.backlogsheet_write` — DB → Central Backlog sheet (DB initiatives written to sheet)
- `flow2.activate` — Flow 2 activation (per-framework scores → active fields)
- `flow3.productopssheet_read_inputs` — ProductOps sheet → DB (inputs synced)
- `flow3.compute_all_frameworks` — Flow 3 compute (per-framework scores)
- `flow3.productopssheet_write_scores` — DB → ProductOps sheet (score write-back)
- `flow4.sync_mathmodels` — MathModels sheet → DB
- `flow4.sync_params` — Params sheet → DB
- `flow4.suggest_mathmodels` — Sheet → Sheet (LLM suggestions)
- `flow4.seed_params` — DB → Sheet (seed params)
- `flow4.protect_sheets` — Sheet protection step

## Guidelines
- Store only the token string in DB/sheets (no run_id suffix in stored values). Put run_id/git_sha/user/timestamps in JSON logs only.
- DB general provenance: set `Initiative.updated_source` to one of the tokens whenever you update a row.
- DB scoring provenance: set both `Initiative.scoring_updated_source` and `Initiative.scoring_updated_at` **only during** compute or activation operations. This separates scoring lineage from general DB edits.
- Sheet provenance: set the tab's "Updated Source" cell to the appropriate token when you write that tab.
