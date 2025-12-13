# CLI Commands Cheatsheet

Copy-ready commands with brief descriptions and impacted fields. Replace placeholders like `<SPREADSHEET_ID>` and `<ORG>`. Use `--log-level DEBUG` for more detail.

| Command | What it does | Impacts (DB/Sheet fields) |
|---|---|---|
| `uv run python -m test_scripts.flow1_etl_cli --log-level INFO` | Full Flow 1: Intake → Backlog Update → Backlog Sync | DB: intake fields upsert, initiative keys; DB: apply central edits (statuses, framework, priorities); Sheet: regenerate Central Backlog rows/scores |
| `uv run python -m test_scripts.flow1_etl_cli --product-org <ORG> --log-level INFO` | Flow 1 limited to a specific org backlog target | Same as above, narrowed to `<ORG>` backlog (DB + Sheet) |
| `uv run python -m test_scripts.flow1_etl_cli --backlog-commit-every 200 --log-level INFO` | Tune batch commits during Backlog Update | DB: commit frequency only (behavioral), fields as in Backlog Update |
| `uv run python -c "from app.db.session import SessionLocal; from app.jobs.backlog_update_job import run_backlog_update; db=SessionLocal(); run_backlog_update(db); db.close()"` | Backlog Update (Sheet → DB) using default configured backlog | DB: central edits pulled into DB (e.g., `active_scoring_framework`, statuses, priorities) |
| `uv run python -c "from app.db.session import SessionLocal; from app.jobs.backlog_update_job import run_backlog_update; db=SessionLocal(); run_backlog_update(db, product_org='<'ORG'>'); db.close()"` | Backlog Update for specific product org | DB: same as above, scoped to `<ORG>` backlog |
| `uv run python -c "from app.db.session import SessionLocal; from app.jobs.backlog_update_job import run_backlog_update; db=SessionLocal(); run_backlog_update(db, spreadsheet_id='<'SPREADSHEET_ID'>', tab_name='Backlog'); db.close()"` | Backlog Update with explicit sheet/tab override | DB: same as above, targeted sheet/tab |
| `uv run python -m test_scripts.backlog_sync_cli --log-level INFO` | Backlog Sync (DB → Sheet) for all configured | Sheet: Central Backlog updated from DB (active scores, statuses, priorities) |
| `uv run python -m test_scripts.backlog_sync_cli --product-org <ORG> --log-level INFO` | Backlog Sync for specific product org | Sheet: same as above scoped to `<ORG>` |
| `uv run python -m test_scripts.backlog_sync_cli --spreadsheet-id <SPREADSHEET_ID> --tab-name Backlog --log-level INFO` | Backlog Sync with explicit overrides | Sheet: same as above targeted sheet/tab |
| `uv run python -m test_scripts.flow2_scoring_cli --all --log-level INFO` | Recompute active scores based on `active_scoring_framework` | DB: `value_score`, `effort_score` (if applicable), `overall_score` updated from per-framework fields |
| `uv run python -m test_scripts.flow3_product_ops_cli --preview --log-level INFO` | Preview Product Ops inputs (read-only) | No changes; logs show parsed inputs |
| `uv run python -m test_scripts.flow3_product_ops_cli --sync --log-level INFO` | Strong sync Product Ops inputs (Sheet → DB) | DB: initiative input fields (e.g., `rice_reach`, `wsjf_cost_of_delay`, etc.) |
| `uv run python -m test_scripts.flow3_product_ops_cli --compute-all --log-level INFO` | Compute RICE + WSJF per-framework scores (no active overwrite) | DB: `rice_*_score`, `wsjf_*_score` per-framework fields updated; active scores unchanged |
| `uv run python -m test_scripts.flow3_product_ops_cli --write-scores --log-level INFO` | Write per-framework scores back to Product Ops sheet | Product Ops Sheet: columns for `rice_*_score`, `wsjf_*_score` updated |
| `uv run python -m test_scripts.init_db` | Initialize local DB schema/data | DB: creates tables, seeds if configured |
| `uv run python -m test_scripts.run_intake_sync_once --log-level INFO` | Run one-time intake sync | DB: intake fields upsert, initiative keys backfill |
| `uv run python -m test_scripts.run_scoring_once --log-level DEBUG` | Debug scoring single pass | DB: depending on script, may recompute scores for sample set |
| `source ./productroadmap_sheet_project/.venv/bin/activate` | Activate local venv (optional when not using `uv run`) | Environment only |
| `uv run python -m test_scripts.backlog_sync_cli --log-level INFO 2>&1 | tail -20` | Run and tail logs for brevity | No changes; terminal convenience |

## Scenario Blocks (Step-by-step)

| Scenario | Steps (commands) | Resulting impacts |
|---|---|---|
| Change active framework in Central Backlog (WSJF → RICE) and propagate | 1) Sheet → DB: `uv run python -c "from app.db.session import SessionLocal; from app.jobs.backlog_update_job import run_backlog_update; db=SessionLocal(); run_backlog_update(db); db.close()"` 2) Recompute active scores: `uv run python -m test_scripts.flow2_scoring_cli --all --log-level INFO` 3) DB → Sheet: `uv run python -m test_scripts.backlog_sync_cli --log-level INFO` | DB: `active_scoring_framework=RICE`; DB: `value_score`,`overall_score` updated to RICE; Sheet: Central Backlog shows new active scores |
| After changing Product Ops inputs, reflect in Central Backlog | 1) Product Ops → DB: `uv run python -m test_scripts.flow3_product_ops_cli --sync --log-level INFO` 2) Compute per-framework: `uv run python -m test_scripts.flow3_product_ops_cli --compute-all --log-level INFO` 3) Write to Product Ops: `uv run python -m test_scripts.flow3_product_ops_cli --write-scores --log-level INFO` 4) Update active: `uv run python -m test_scripts.flow2_scoring_cli --all --log-level INFO` 5) DB → Sheet: `uv run python -m test_scripts.backlog_sync_cli --log-level INFO` | DB: inputs + per-framework scores; DB: active scores updated; Sheet: Product Ops + Central Backlog reflect latest |
