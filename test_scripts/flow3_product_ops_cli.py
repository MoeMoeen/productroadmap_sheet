#!/usr/bin/env python3

# productroadmap_sheet_project/test_scripts/flow3_product_ops_cli.py

from __future__ import annotations

import argparse
import logging
import sys

from app.db.session import SessionLocal
from app.jobs.flow3_product_ops_job import (
    run_flow3_preview_inputs,
    run_flow3_sync_inputs_to_initiatives,
    run_flow3_write_scores_to_sheet,
)
from app.services.scoring_service import ScoringService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flow 3: Product Ops Scoring Inputs and Multi-Framework Support",
        epilog="""
        Examples:
        # Preview inputs from Product Ops sheet
        %(prog)s --preview --log-level DEBUG

        # Sync inputs from sheet to DB (strong sync)
        %(prog)s --sync --batch-size 100

        # Compute RICE and WSJF scores for all initiatives (side-by-side comparison)
        %(prog)s --compute-all --batch-size 100

        # Write per-framework scores back to Product Ops sheet
        %(prog)s --write-scores

        # Full pipeline (sync inputs, compute all frameworks, write scores)
        %(prog)s --sync && %(prog)s --compute-all && %(prog)s --write-scores
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--preview",
        action="store_true",
        help="Preview parsed inputs from Scoring_Inputs tab (no DB writes)",
    )
    mode.add_argument(
        "--sync",
        action="store_true",
        help="Strong sync: read Scoring_Inputs sheet → update Initiative fields in DB",
    )
    mode.add_argument(
        "--compute-all",
        action="store_true",
        help="Compute all frameworks (RICE + WSJF) for all initiatives; store per-framework scores without changing active_scoring_framework",
    )
    mode.add_argument(
        "--write-scores",
        action="store_true",
        help="Write per-framework scores from DB back to Scoring_Inputs sheet for PM review",
    )

    parser.add_argument(
        "--spreadsheet-id",
        type=str,
        default=None,
        help="Override Product Ops spreadsheet ID (default: from PRODUCT_OPS_CONFIG_FILE)",
    )
    parser.add_argument(
        "--tab-name",
        type=str,
        default=None,
        help="Override Scoring_Inputs tab name (default: from config)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Commit every N updates when running --sync or --compute-all (default: SCORING_BATCH_COMMIT_EVERY)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    """Configure JSON logging for the app"""
    from app.config import setup_json_logging
    lvl = getattr(logging, level.upper(), logging.INFO)
    setup_json_logging(log_level=lvl)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    logger = logging.getLogger("app.flow3_cli")

    if args.preview:
        try:
            rows = run_flow3_preview_inputs(spreadsheet_id=args.spreadsheet_id, tab_name=args.tab_name)
            logger.info("flow3.cli.preview", extra={"rows": len(rows)})
            return 0
        except Exception:
            logger.exception("flow3.cli.preview_error")
            return 1

    db = SessionLocal()
    try:
        if args.sync:
            # Flow 3.B: Strong sync from Product Ops sheet to DB
            # Reads Scoring_Inputs tab and updates Initiative fields (rice_reach, wsjf_job_size, etc.)
            count = run_flow3_sync_inputs_to_initiatives(
                db,
                commit_every=args.batch_size,
                spreadsheet_id=args.spreadsheet_id,
                tab_name=args.tab_name,
            )
            logger.info("flow3.cli.sync_complete", extra={"initiatives_updated": count})
            return 0

        elif args.compute_all:
            # Flow 3.C Phase 1: Compute all frameworks for all initiatives
            # Scores each initiative with both RICE and WSJF frameworks
            # Stores results in rice_*_score and wsjf_*_score fields
            # Does NOT change active_scoring_framework or active score fields
            service = ScoringService(db)
            count = service.score_all_frameworks(commit_every=args.batch_size)
            logger.info(
                "flow3.cli.compute_all_complete",
                extra={"initiatives_processed": count, "frameworks": "RICE, WSJF"},
            )
            return 0

        elif args.write_scores:
            # Flow 3.C Phase 2: Write per-framework scores back to Product Ops sheet
            # Reads per-framework scores from DB and writes to Scoring_Inputs tab
            # Enables PMs to see side-by-side comparison of RICE vs WSJF scores
            count = run_flow3_write_scores_to_sheet(
                db,
                spreadsheet_id=args.spreadsheet_id,
                tab_name=args.tab_name,
            )
            logger.info("flow3.cli.write_scores_complete", extra={"cells_updated": count})
            return 0

        else:
            logger.error("flow3.cli.no_mode_selected")
            return 1

    except KeyboardInterrupt:
        logger.warning("flow3.cli.interrupted_by_user")
        return 130
    except Exception:
        logger.exception("flow3.cli.error")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())