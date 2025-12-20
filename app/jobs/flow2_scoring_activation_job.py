"""Flow 2 Scoring Activation Job

Encapsulates batch activation logic so that CLI and other orchestrators
can invoke activation without directly depending on service layer details.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.services.scoring import ScoringFramework
from app.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)


def run_scoring_batch(
    db: Session,
    *,
    framework: Optional[ScoringFramework],
    commit_every: Optional[int] = None,
    only_missing_scores: bool = True,
) -> int:
    """Run an activation batch for the given framework.

    Args:
        db: SQLAlchemy session
        framework: scoring framework enum
        commit_every: batch commit size override (None -> settings default)
        only_missing_scores: whether to restrict to initiatives lacking active scores

    Returns:
        Number of initiatives activated.
    """
    logger.info("flow2.activation.start", extra={"framework": (framework.value if framework else "AUTO")})
    service = ScoringService(db)
    activated = service.activate_all(
        framework=framework,
        commit_every=commit_every,
        only_missing_active=only_missing_scores,
    )
    logger.info("flow2.activation.done", extra={"framework": (framework.value if framework else "AUTO"), "activated": activated})
    return activated


__all__ = ["run_scoring_batch"]
