#!/usr/bin/env python3
#productroadmap_sheet_project/test_scripts/flow1_cli.py
"""CLI entrypoint for Flow 1 full sync.

Usage examples:
    python -m flow1_cli --allow-status-override --backlog-commit-every 200
    python -m flow1_cli --product-org core

Flags:
    --allow-status-override    Allow intake status override globally.
    --backlog-commit-every N   Batch commit size for backlog update phase.
    --product-org ORG          Restrict backlog update/sync to a specific product org.
    --log-level LEVEL          Logging level (INFO, DEBUG, WARNING, ERROR).

Exit codes:
    0 on success, non-zero on unexpected exception.
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.db.session import SessionLocal
from app.jobs.flow1_full_sync_job import run_flow1_full_sync


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Flow 1 full sync orchestration.")
    parser.add_argument(
        "--allow-status-override",
        action="store_true",
        help="Allow status override globally for intake sync phase.",
    )
    parser.add_argument(
        "--backlog-commit-every",
        type=int,
        default=None,
        help="Batch commit frequency for backlog update phase.",
    )
    parser.add_argument(
        "--product-org",
        type=str,
        default=None,
        help="Target a specific product org backlog sheet (if configured).",
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
    logger = logging.getLogger("app.flow1_cli")
    logger.info("flow1.cli.start")

    db = SessionLocal()
    try:
        run_flow1_full_sync(
            db=db,
            allow_status_override_global=args.allow_status_override,
            backlog_commit_every=args.backlog_commit_every,
            product_org=args.product_org,
        )
    except KeyboardInterrupt:
        logging.getLogger(__name__).warning("flow1.cli.interrupted")
        return 130
    except Exception:
        logging.getLogger(__name__).exception("flow1.cli.error")
        return 1
    finally:
        db.close()
    logging.getLogger(__name__).info("flow1.cli.done")
    return 0


if __name__ == "__main__":
    sys.exit(main()) # what does sys.exit do here? It exits the program with the return code from main(), indicating success or failure.
