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
    parser = argparse.ArgumentParser(description="Flow 3: Product Ops Scoring Inputs")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true", help="Preview parsed inputs (no DB writes)")
    mode.add_argument("--sync", action="store_true", help="Strong sync sheet -> initiatives in DB")
    mode.add_argument("--compute-all", action="store_true", help="Compute all frameworks for all initiatives")
    mode.add_argument("--write-scores", action="store_true", help="Write per-framework scores back to Product Ops sheet")

    parser.add_argument(
        "--spreadsheet-id",
        type=str,
        default=None,
        help="Override Product Ops spreadsheet ID",
    )
    parser.add_argument(
        "--tab-name",
        type=str,
        default=None,
        help="Override Scoring_Inputs tab name",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Commit every N updates when running --sync or --compute-all",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (e.g. INFO, DEBUG)",
    )
    return parser.parse_args()



def configure_logging(level: str) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    logger = logging.getLogger(__name__)

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
            # Flow 3.B: Sync Product Ops sheet -> DB
            count = run_flow3_sync_inputs_to_initiatives(
                db,
                commit_every=args.batch_size,
                spreadsheet_id=args.spreadsheet_id,
                tab_name=args.tab_name,
            )
            logger.info("flow3.cli.sync", extra={"updated": count})
            return 0

        elif args.compute_all:
            # Flow 3.C Phase 1: Compute all frameworks for all initiatives
            service = ScoringService(db)
            count = service.score_all_frameworks(commit_every=args.batch_size)
            logger.info("flow3.cli.compute_all", extra={"processed": count})
            return 0

        elif args.write_scores:
            # Flow 3.C Phase 2: Write per-framework scores back to Product Ops sheet
            count = run_flow3_write_scores_to_sheet(
                db,
                spreadsheet_id=args.spreadsheet_id,
                tab_name=args.tab_name,
            )
            logger.info("flow3.cli.write_scores", extra={"updated": count})
            return 0

        else:
            logger.error("flow3.cli.no_mode")
            return 1

    except KeyboardInterrupt:
        logger.warning("flow3.cli.interrupted")
        return 130 # interrupted
    except Exception:
        logger.exception("flow3.cli.error")
        return 1 # error
    finally:
        db.close()



if __name__ == "__main__":
    sys.exit(main())

