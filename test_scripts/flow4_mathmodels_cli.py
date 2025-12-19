#!/usr/bin/env python3

# productroadmap_sheet_project/test_scripts/flow4_mathmodels_cli.py

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional

from app.config import settings
from app.db.session import SessionLocal
from app.sheets.client import get_sheets_service, SheetsClient
from app.sheets.sheet_protection import apply_all_productops_protections
from app.services.math_model_service import MathModelSyncService
from app.services.params_sync_service import ParamsSyncService
from app.llm.client import LLMClient
from app.jobs.math_model_generation_job import run_math_model_generation_job
from app.jobs.param_seeding_job import run_param_seeding_job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flow 4: MathModels and Params Sheet ↔ DB sync, plus LLM suggestions",
        epilog="""
        Examples:
        # Preview MathModels rows
        %(prog)s --preview-mathmodels --limit 10 --log-level DEBUG

        # Sync MathModels to DB
        %(prog)s --sync-mathmodels --batch-size 100

        # Generate LLM suggestions (writes to sheet)
        %(prog)s --suggest-mathmodels --limit 20

        # Force re-suggestion even if already suggested
        %(prog)s --suggest-mathmodels --force

        # Preview Params rows
        %(prog)s --preview-params --limit 10

        # Sync Params to DB
        %(prog)s --sync-params --batch-size 200
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview-mathmodels", action="store_true", help="Preview MathModels rows (no DB writes)")
    mode.add_argument("--sync-mathmodels", action="store_true", help="Sync MathModels from sheet → DB")
    mode.add_argument("--preview-params", action="store_true", help="Preview Params rows (no DB writes)")
    mode.add_argument("--sync-params", action="store_true", help="Sync Params from sheet → DB")
    mode.add_argument(
        "--suggest-mathmodels",
        action="store_true",
        help="Generate LLM suggestions for MathModels (formula, assumptions, notes) from Sheet → Sheet",
    )
    mode.add_argument(
        "--seed-params",
        action="store_true",
        help="Seed Params from approved MathModels formulas (Step 8: extract identifiers, call LLM for metadata, append-only)",
    )
    mode.add_argument(
        "--protect-sheets",
        action="store_true",
        help="Apply warning-only protections to ProductOps system columns (one-time setup)",
    )

    parser.add_argument("--spreadsheet-id", type=str, default=None, help="Override Product Ops spreadsheet ID")
    parser.add_argument("--mathmodels-tab", type=str, default=None, help="Override MathModels tab name")
    parser.add_argument("--params-tab", type=str, default=None, help="Override Params tab name")
    parser.add_argument("--limit", type=int, default=None, help="Limit row preview count")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Commit every N upserts on sync (defaults: SCORING_BATCH_COMMIT_EVERY)",
    )
    parser.add_argument("--force", action="store_true", help="Force re-suggestion even if already suggested")
    parser.add_argument("--max-llm-calls", type=int, default=10, help="Max LLM calls for --seed-params or --suggest-mathmodels")
    parser.add_argument("--dry-run", action="store_true", help="Preview param seeding without writing (for --seed-params)")
    parser.add_argument("--log-level", type=str, default="INFO", help="Log level: DEBUG, INFO, WARNING, ERROR")
    return parser.parse_args()


def configure_logging(level: str) -> None:
    """Configure JSON logging for the app"""
    from app.config import setup_json_logging
    lvl = getattr(logging, level.upper(), logging.INFO)
    setup_json_logging(log_level=lvl)


def resolve_sheet_config(
    spreadsheet_id: Optional[str], mathmodels_tab: Optional[str], params_tab: Optional[str]
) -> tuple[str, str, str, str]:
    cfg = settings.PRODUCT_OPS
    if not cfg:
        raise RuntimeError("PRODUCT_OPS not configured; set PRODUCT_OPS_CONFIG_FILE or env settings")

    sid = spreadsheet_id or cfg.spreadsheet_id
    mtab = mathmodels_tab or cfg.mathmodels_tab
    ptab = params_tab or cfg.params_tab
    scoring_tab = cfg.scoring_inputs_tab or "Scoring_Inputs"
    return sid, mtab, ptab, scoring_tab


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    logger = logging.getLogger("app.flow4_cli")

    try:
        spreadsheet_id, mathmodels_tab, params_tab, scoring_inputs_tab = resolve_sheet_config(
            args.spreadsheet_id, args.mathmodels_tab, args.params_tab
        )
    except Exception:
        logging.exception("flow4.cli.config_error")
        return 1

    service = get_sheets_service()
    client = SheetsClient(service)

    # Handle --protect-sheets (no DB needed)
    if args.protect_sheets:
        try:
            apply_all_productops_protections(
                client=client,
                spreadsheet_id=spreadsheet_id,
                math_models_tab=mathmodels_tab,
                params_tab=params_tab,
                scoring_inputs_tab=scoring_inputs_tab,
            )
            logger.info("flow4.cli.protect_sheets_complete")
            return 0
        except Exception:
            logger.exception("flow4.cli.protect_sheets_error")
            return 1

    if args.preview_mathmodels:
        try:
            svc = MathModelSyncService(client)
            rows = svc.preview_rows(spreadsheet_id, mathmodels_tab, max_rows=args.limit)
            logger.info(
                "flow4.cli.preview_mathmodels",
                extra={"rows": len(rows), "sample": rows[: min(len(rows), 3)]},
            )
            return 0
        except Exception:
            logger.exception("flow4.cli.preview_mathmodels_error")
            return 1

    if args.preview_params:
        try:
            svc = ParamsSyncService(client)
            rows = svc.preview_rows(spreadsheet_id, params_tab, max_rows=args.limit)
            logger.info(
                "flow4.cli.preview_params",
                extra={"rows": len(rows), "sample": rows[: min(len(rows), 3)]},
            )
            return 0
        except Exception:
            logger.exception("flow4.cli.preview_params_error")
            return 1

    db = SessionLocal()
    try:
        if args.sync_mathmodels:
            svc = MathModelSyncService(client)
            result = svc.sync_sheet_to_db(
                db,
                spreadsheet_id=spreadsheet_id,
                tab_name=mathmodels_tab,
                commit_every=(args.batch_size or settings.SCORING_BATCH_COMMIT_EVERY),
            )
            logger.info("flow4.cli.sync_mathmodels_complete", extra=result)
            return 0

        if args.sync_params:
            svc = ParamsSyncService(client)
            result = svc.sync_sheet_to_db(
                db,
                spreadsheet_id=spreadsheet_id,
                tab_name=params_tab,
                commit_every=(args.batch_size or settings.SCORING_BATCH_COMMIT_EVERY),
            )
            logger.info("flow4.cli.sync_params_complete", extra=result)
            return 0

        if args.suggest_mathmodels:
            try:
                if not settings.OPENAI_API_KEY:
                    logger.error("flow4.cli.openai_api_key_missing")
                    return 1

                llm = LLMClient()
                result = run_math_model_generation_job(
                    db=db,
                    sheets_client=client,
                    llm_client=llm,
                    spreadsheet_id=spreadsheet_id,
                    tab_name=mathmodels_tab,
                    max_rows=args.limit,
                    force=args.force,
                    max_llm_calls=args.max_llm_calls,
                )
                logger.info("flow4.cli.suggest_mathmodels_complete", extra=result)
                return 0
            except Exception:
                logger.exception("flow4.cli.suggest_mathmodels_error")
                return 1

        if args.seed_params:
            try:
                if not settings.OPENAI_API_KEY:
                    logger.error("flow4.cli.openai_api_key_missing")
                    return 1

                if args.dry_run:
                    logger.warning("flow4.cli.dry_run_mode (param seeding will not write to sheet)")
                    # TODO: implement dry-run preview logic in param_seeding_job
                    return 0

                llm = LLMClient()
                stats = run_param_seeding_job(
                    sheets_client=client,
                    spreadsheet_id=spreadsheet_id,
                    mathmodels_tab=mathmodels_tab,
                    params_tab=params_tab,
                    llm_client=llm,
                    max_llm_calls=args.max_llm_calls,
                    limit=args.limit,
                )
                logger.info("flow4.cli.seed_params_complete", extra=stats.summary())
                return 0
            except Exception:
                logger.exception("flow4.cli.seed_params_error")
                return 1

        logger.error("flow4.cli.no_mode_selected")
        return 1

    except KeyboardInterrupt:
        logger.warning("flow4.cli.interrupted_by_user")
        return 130
    except Exception:
        logger.exception("flow4.cli.error")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
