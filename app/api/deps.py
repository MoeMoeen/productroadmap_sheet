# productroadmap_sheet_project/app/api/deps.py

from __future__ import annotations

from typing import Generator

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
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
    expected = getattr(settings, "ROADMAP_AI_SECRET", None)

    if not expected:
        raise HTTPException(status_code=500, detail="Shared secret is not configured")
    if not x_roadmap_ai_secret or x_roadmap_ai_secret != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
