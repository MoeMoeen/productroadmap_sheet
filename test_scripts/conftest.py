# Ensure test database schema is up-to-date before tests run
from __future__ import annotations

import logging
import pytest
from sqlalchemy import text

from app.db.session import engine
from app.db.base import Base
from app.db import models  # side-effect: register all models

logger = logging.getLogger(__name__)


def _add_missing_initiatives_columns(conn) -> None:
    """No-op: columns now handled by Alembic migrations.
    This function kept for compatibility but does nothing.
    """
    pass


@pytest.fixture(scope="session", autouse=True)
def ensure_schema() -> None:
    """Create all ORM tables and add missing columns for tests.
    This is a test-only bootstrap; production should use Alembic migrations.
    """
    try:
        # Create tables from ORM models
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            _add_missing_initiatives_columns(conn)
        logger.info("test-bootstrap: schema ensured")
    except Exception:
        logger.exception("test-bootstrap: schema ensure failed")
        # Let tests surface the failure
        raise
