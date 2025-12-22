from __future__ import annotations

import os
from typing import Generator

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_shared_secret(x_roadmap_ai_secret: str | None = Header(default=None)) -> None:
    """
    v1 security: shared secret header from Apps Script.
    Header name: X-ROADMAP-AI-SECRET
    """
    expected = os.getenv("ROADMAP_AI_SECRET", "")
    if not expected:
        # If secret isn't configured, fail closed (recommended).
        raise HTTPException(status_code=500, detail="ROADMAP_AI_SECRET is not configured")

    if not x_roadmap_ai_secret or x_roadmap_ai_secret != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
