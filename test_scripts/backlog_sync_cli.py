#!/usr/bin/env python3

# productroadmap_sheet_project/test_scripts/backlog_sync_cli.py

"""
CLI entrypoint for Backlog Sync (DB -> Central Backlog Sheet).

Usage examples:
    # Sync all configured backlog sheets
    uv run python -m test_scripts.backlog_sync_cli --log-level INFO

    # Sync specific backlog by product org
    uv run python -m test_scripts.backlog_sync_cli --product-org global --log-level INFO

    # Sync specific spreadsheet/tab override
    uv run python -m test_scripts.backlog_sync_cli --spreadsheet-id 1abc... --tab-name Backlog

Flags:
    --spreadsheet-id ID   Override target backlog spreadsheet ID
    --tab-name NAME       Override target backlog tab name
    --product-org ORG     Target specific product org backlog
    --all                 Sync all configured backlog sheets (default if no overrides)
    --log-level LEVEL     Logging level (INFO, DEBUG, etc.)
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.db.session import SessionLocal
from app.jobs.backlog_sync_job import run_backlog_sync, run_all_backlog_sync


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync DB initiatives to central backlog sheet(s).")
    parser.add_argument(
        "--spreadsheet-id",
        type=str,
        default=None,
        help="Target backlog spreadsheet ID override.",
    )
    parser.add_argument(
        "--tab-name",
        type=str,
        default=None,
        help="Target backlog tab name override.",
    )
    parser.add_argument(
        "--product-org",
        type=str,
        default=None,
        help="Target specific product org backlog.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Sync all configured backlog sheets (default if no overrides).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (e.g. INFO, DEBUG).",
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
    logger = logging.getLogger("app.backlog_sync_cli")
    logger = logging.getLogger(__name__)
    logger.info("backlog_sync.cli.start")

    db = SessionLocal()
    try:
        # If any specific override or product_org, use run_backlog_sync
        if args.spreadsheet_id or args.tab_name or args.product_org:
            run_backlog_sync(
                db=db,
                spreadsheet_id=args.spreadsheet_id,
                tab_name=args.tab_name,
                product_org=args.product_org,
            )
        else:
            # Default: sync all configured backlog sheets
            run_all_backlog_sync(db=db)
        
        logger.info("backlog_sync.cli.done")
        return 0
    except KeyboardInterrupt:
        logger.warning("backlog_sync.cli.interrupted")
        return 130
    except Exception:
        logger.exception("backlog_sync.cli.error")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
