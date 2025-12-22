# productroadmap_sheet_project/app/main.py

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import setup_json_logging, settings
from app.api.routes.actions import router as actions_router


def create_app() -> FastAPI:
    setup_json_logging(log_level=getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO))

    app = FastAPI(
        title="PRODUCT ROADMAP SHEET - Action API",
        version="0.1.0",
    )

    app.include_router(actions_router)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
