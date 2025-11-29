"""Flow 2 Scoring Job

Encapsulates batch scoring logic so that CLI and other orchestrators
can invoke scoring without directly depending on service layer details.
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
    """Run a scoring batch for the given framework.

    Args:
        db: SQLAlchemy session
        framework: scoring framework enum
        commit_every: batch commit size override (None -> settings default)
        only_missing_scores: whether to restrict to initiatives lacking current scores

    Returns:
        Number of initiatives scored.
    """
    logger.info("flow2.scoring.start", extra={"framework": (framework.value if framework else "AUTO")})
    service = ScoringService(db)
    scored = service.score_all(
        framework=framework,
        commit_every=commit_every,
        only_missing_scores=only_missing_scores,
    )
    logger.info("flow2.scoring.done", extra={"framework": (framework.value if framework else "AUTO"), "scored": scored})
    return scored


__all__ = ["run_scoring_batch"]
