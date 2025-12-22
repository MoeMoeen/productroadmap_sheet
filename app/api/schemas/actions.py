# productroadmap_sheet_project/app/api/schemas/actions.py

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class ActionRunRequest(BaseModel):
    action: str = Field(..., min_length=1)

    scope: Dict[str, Any] = Field(default_factory=dict)
    sheet_context: Dict[str, Any] = Field(default_factory=dict)
    options: Dict[str, Any] = Field(default_factory=dict)
    requested_by: Dict[str, Any] = Field(default_factory=dict)


class ActionRunEnqueueResponse(BaseModel):
    run_id: str
    status: Literal["queued"]


class ActionRunStatusResponse(BaseModel):
    run_id: str
    action: str
    status: Literal["queued", "running", "success", "failed"]

    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
