#!/usr/bin/env python3
"""
CLI entrypoint for Flow 2 scoring.

Usage examples:
    # Auto (per-initiative) selection
    uv run python -m test_scripts.flow2_scoring_cli --only-missing
    # Force a single framework for all initiatives
    uv run python -m test_scripts.flow2_scoring_cli --framework RICE --all

Flags:
    --framework NAME      Override framework for all (RICE, WSJF, MATH_MODEL). Omit for AUTO (per-initiative).
    --batch-size N        Commit every N initiatives (default: settings.SCORING_BATCH_COMMIT_EVERY)
    --all                 Score all initiatives (even if already scored)
    --only-missing        Only score initiatives missing scores or with a different framework (default)
    --log-level LEVEL     Logging level (INFO, DEBUG, etc.)
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.db.session import SessionLocal
from app.services.scoring import ScoringFramework
from app.jobs.flow2_scoring_job import run_scoring_batch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Flow 2 scoring batch.")
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
        help="Score all initiatives, even if already scored with this framework.",
    )
    group.add_argument(
        "--only-missing",
        action="store_true",
        help="Only score initiatives missing scores or using a different framework (default).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (e.g. INFO, DEBUG).",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    logger = logging.getLogger(__name__)
    logger.info("scoring.cli.start")

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
        scored = run_scoring_batch(
            db=db,
            framework=framework,
            commit_every=args.batch_size,
            only_missing_scores=only_missing,
        )
        logger.info(
            "scoring.cli.done",
            extra={"framework": (framework.value if framework else "AUTO"), "scored": scored},
        )
        return 0
    except KeyboardInterrupt:
        logger.warning("scoring.cli.interrupted")
        return 130
    except Exception:
        logger.exception("scoring.cli.error")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
