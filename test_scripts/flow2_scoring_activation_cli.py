#!/usr/bin/env python3
# productroadmap_sheet_project/test_scripts/flow2_scoring_activation_cli.py
"""
CLI entrypoint for Flow 2 activation.

Usage examples:
    # Auto (per-initiative) selection
    uv run python -m test_scripts.flow2_scoring_activation_cli --only-missing
    # Force a single framework for all initiatives
    uv run python -m test_scripts.flow2_scoring_activation_cli --framework RICE --all

Flags:
    --framework NAME      Override framework for all (RICE, WSJF, MATH_MODEL). Omit for AUTO (per-initiative).
    --batch-size N        Commit every N initiatives (default: settings.SCORING_BATCH_COMMIT_EVERY)
    --all                 Activate all initiatives (even if already activated)
    --only-missing        Only activate initiatives missing active scores or using a different framework (default)
    --log-level LEVEL     Logging level (INFO, DEBUG, etc.)
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.db.session import SessionLocal
from app.services.product_ops.scoring import ScoringFramework
from app.jobs.flow2_scoring_activation_job import run_scoring_batch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Activate chosen scoring framework scores (Flow 2).")
    parser.add_argument(
        "--framework",
        type=str,
        default=None,
        help="Override framework for all (RICE, WSJF, MATH_MODEL). Omit for AUTO (per-initiative).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Commit every N initiatives (defaults to SCORING_BATCH_COMMIT_EVERY).",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all",
        action="store_true",
        help="Activate all initiatives, even if already activated with this framework.",
    )
    group.add_argument(
        "--only-missing",
        action="store_true",
        help="Only activate initiatives missing active scores or using a different framework (default).",
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
    logger = logging.getLogger("app.flow2_scoring_activation_cli")
    logger.info("activation.cli.start")

    framework = None
    if args.framework:
        try:
            framework = ScoringFramework(args.framework.upper())
        except ValueError:
            logger.error("Unknown framework: %s", args.framework)
            return 1

    only_missing = not args.all  # default to only_missing if neither flag is passed

    db = SessionLocal()
    try:
        activated = run_scoring_batch(
            db=db,
            framework=framework,
            commit_every=args.batch_size,
            only_missing_scores=only_missing,
        )
        logger.info(
            "activation.cli.done",
            extra={"framework": (framework.value if framework else "AUTO"), "activated": activated},
        )
        return 0
    except KeyboardInterrupt:
        logger.warning("activation.cli.interrupted")
        return 130
    except Exception:
        logger.exception("activation.cli.error")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
