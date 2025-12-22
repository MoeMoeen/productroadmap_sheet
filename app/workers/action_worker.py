from __future__ import annotations

import logging
import time
from typing import Optional

from app.config import setup_json_logging, settings
from app.db.session import SessionLocal
from app.services.action_runner import execute_next_queued_run


logger = logging.getLogger("app.workers.action_worker")


def run_worker_loop(
    poll_interval_seconds: float = 1.0,
    idle_sleep_seconds: float = 2.0,
    max_runs: Optional[int] = None,
) -> int:
    """
    Continuously execute queued ActionRuns.

    - poll_interval_seconds: how often we try to fetch a queued run (tight loop cadence)
    - idle_sleep_seconds: sleep time when no jobs are queued (reduces DB load)
    - max_runs: if set, execute at most N runs then exit (useful for local testing)
    """
    setup_json_logging(log_level=getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO))

    executed = 0
    logger.info(
        "action_worker.start",
        extra={"poll_interval": poll_interval_seconds, "idle_sleep": idle_sleep_seconds},
    )

    while True:
        if max_runs is not None and executed >= max_runs:
            logger.info("action_worker.stop_max_runs", extra={"executed": executed})
            return executed

        db = SessionLocal()
        try:
            run = execute_next_queued_run(db)
        except Exception:
            # If something unexpected happens at the worker level, log and keep going
            logger.exception("action_worker.loop_error")
            run = None
        finally:
            db.close()

        if run is None:
            # No queued runs: sleep longer (idle)
            time.sleep(idle_sleep_seconds)
        else:
            executed += 1
            # Small sleep to avoid hammering if queue is huge; tune later
            time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    # v1 defaults: run forever
    run_worker_loop()
