# productroadmap_sheet_project/app/api/routes/actions.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_shared_secret
from app.api.schemas.actions import (
    ActionRunRequest,
    ActionRunEnqueueResponse,
    ActionRunStatusResponse,
)
from app.db.models.action_run import ActionRun
from app.services.action_runner import enqueue_action_run


router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/run", response_model=ActionRunEnqueueResponse, dependencies=[Depends(require_shared_secret)])
def run_action(req: ActionRunRequest, db: Session = Depends(get_db)) -> ActionRunEnqueueResponse:
    """
    Enqueue an action and return run_id immediately.
    """
    try:
        ar = enqueue_action_run(db=db, payload=req.model_dump())
        return ActionRunEnqueueResponse(run_id=ar.run_id, status="queued")  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue action: {e}") from e


@router.get("/run/{run_id}", response_model=ActionRunStatusResponse, dependencies=[Depends(require_shared_secret)])
def get_run_status(run_id: str, db: Session = Depends(get_db)) -> ActionRunStatusResponse:
    """
    Get the status of a specific action run by run_id.
    """
    ar: ActionRun | None = db.query(ActionRun).filter(ActionRun.run_id == run_id).one_or_none()
    if not ar:
        raise HTTPException(status_code=404, detail="run_id not found")

    def iso(dt):
        return dt.isoformat() if dt else None

    return ActionRunStatusResponse(
        run_id=ar.run_id,  # type: ignore[arg-type]
        action=ar.action,  # type: ignore[arg-type]
        status=ar.status,  # type: ignore[arg-type]
        created_at=iso(ar.created_at) or "",
        started_at=iso(ar.started_at),
        finished_at=iso(ar.finished_at),
        result=ar.result_json,  # type: ignore[arg-type]
        error=ar.error_text,  # type: ignore[arg-type]
    )
