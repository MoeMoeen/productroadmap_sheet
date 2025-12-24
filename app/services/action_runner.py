# productroadmap_sheet_project/app/services/action_runner.py
""" 
Action runner service for enqueuing and executing sheet-triggered actions.
"""

from __future__ import annotations

import logging
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.action_run import ActionRun
from app.services.scoring import ScoringFramework
from app.services.scoring_service import ScoringService

from app.jobs.backlog_sync_job import run_all_backlog_sync
from app.jobs.flow1_full_sync_job import run_flow1_full_sync
from app.jobs.flow3_product_ops_job import run_flow3_write_scores_to_sheet, run_flow3_sync_inputs_to_initiatives
from app.jobs.flow2_scoring_activation_job import run_scoring_batch
from app.jobs.sync_intake_job import run_sync_all_intake_sheets

from app.sheets.client import SheetsClient, get_sheets_service
from app.services.math_model_service import MathModelSyncService
from app.services.params_sync_service import ParamsSyncService

from app.jobs.math_model_generation_job import run_math_model_generation_job
from app.jobs.param_seeding_job import run_param_seeding_job
from app.llm.client import LLMClient


logger = logging.getLogger("app.services.action_runner")


# ----------------------------
# Status constants (v1)
# ----------------------------
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class ActionContext:
    """Convenience wrapper around payload and resolved runtime dependencies."""
    payload: Dict[str, Any]
    sheets_client: SheetsClient
    llm_client: Optional[LLMClient]


ActionFn = Callable[[Session, ActionContext], Dict[str, Any]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_run_id() -> str:
    # Example: run_20251221T120102Z_a1b2c3d4
    ts = _now().strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    return f"run_{ts}_{short}"


def enqueue_action_run(db: Session, payload: Dict[str, Any]) -> ActionRun:
    """Create an ActionRun row with status=queued and return the ORM object."""
    run_id = _make_run_id()
    action = str(payload.get("action") or "").strip()
    if not action:
        raise ValueError("payload.action is required")
    
    # Validate action exists in registry to prevent poison jobs
    if action not in _ACTION_REGISTRY:
        raise ValueError(f"Unknown action: {action}. Valid actions: {', '.join(sorted(_ACTION_REGISTRY.keys()))}")

    requested_by = payload.get("requested_by") or {}
    sheet_ctx = payload.get("sheet_context") or {}
    scope = payload.get("scope") or {}

    ar = ActionRun(
        run_id=run_id,
        action=action,
        status=STATUS_QUEUED,
        payload_json=payload,
        requested_by_email=(requested_by.get("user_email") if isinstance(requested_by, dict) else None),
        requested_by_ui=(requested_by.get("ui") if isinstance(requested_by, dict) else None),
        spreadsheet_id=(sheet_ctx.get("spreadsheet_id") if isinstance(sheet_ctx, dict) else None),
        tab_name=(sheet_ctx.get("tab") if isinstance(sheet_ctx, dict) else None),
        scope_type=(scope.get("type") if isinstance(scope, dict) else None),
        scope_summary=_build_scope_summary(scope),
        created_at=_now(),
    )
    db.add(ar)
    db.commit()
    db.refresh(ar)

    logger.info(
        "action_run.enqueued",
        extra={"run_id": ar.run_id, "action": ar.action, "status": ar.status},
    )
    return ar


def _build_scope_summary(scope: Any) -> Optional[str]:
    """Short human-friendly text for Control tab."""
    if not isinstance(scope, dict):
        return None
    t = scope.get("type")
    if t == "initiative_keys":
        keys = scope.get("initiative_keys") or []
        if isinstance(keys, list):
            return f"{len(keys)} initiatives"
    if t == "all":
        return "all"
    if t == "filter":
        pred = scope.get("predicate") or {}
        if isinstance(pred, dict):
            return f"filter: {pred.get('column')} {pred.get('op')} {pred.get('value')}"
        return "filter"
    if t == "selection":
        return "selection"
    return str(t) if t else None


def _extract_summary(action: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract standardized summary from action-specific result for UI display.
    
    Returns a normalized dict with common fields:
    - total: total items processed/considered
    - success: items successfully processed
    - skipped: items skipped
    - failed: items failed (if applicable)
    """
    summary = {
        "total": 0,
        "success": 0,
        "skipped": 0,
        "failed": 0,
    }
    
    # Flow 3 actions
    if action == "flow3.compute_all_frameworks":
        summary["total"] = result.get("processed", 0)
        summary["success"] = result.get("processed", 0)
    
    elif action == "flow3.write_scores":
        summary["total"] = result.get("updated_initiatives", 0)
        summary["success"] = result.get("updated_initiatives", 0)
    
    elif action == "flow3.sync_inputs":
        summary["total"] = result.get("updated", 0)
        summary["success"] = result.get("updated", 0)
    
    # Flow 2 actions
    elif action == "flow2.activate":
        summary["total"] = result.get("activated", 0)
        summary["success"] = result.get("activated", 0)
    
    # Flow 1 actions
    elif action == "flow1.backlog_sync":
        # Boolean flag, treat as single-unit task for UX clarity
        synced = bool(result.get("synced"))
        summary["total"] = 1
        summary["success"] = 1 if synced else 0
        summary["failed"] = 0 if synced else 1
    
    elif action == "flow1.full_sync":
        # Count completed substeps
        substeps = result.get("substeps", [])
        summary["total"] = 3  # Expected substeps
        summary["success"] = len(substeps)
        # Check for partial failure
        if not result.get("backlog_update_completed", True):
            summary["failed"] = 1
    
    # Flow 4 actions
    elif action == "flow4.suggest_mathmodels":
        # Stats from run_math_model_generation_job
        summary["total"] = result.get("rows", 0)
        summary["success"] = result.get("suggested", 0)
        summary["skipped"] = (
            result.get("skipped_approved", 0)
            + result.get("skipped_no_desc", 0)
            + result.get("skipped_has_suggestion", 0)
            + result.get("skipped_missing_initiative", 0)
        )
    
    elif action == "flow4.seed_params":
        summary["total"] = result.get("rows_scanned_mathmodelstab", 0)
        summary["success"] = result.get("seeded_params_paramsstab", 0)
        summary["skipped"] = (
            result.get("skipped_row_mathmodeltab_no_missing", 0) +
            result.get("skipped_row_mathmodeltab_unapproved", 0) +
            result.get("skipped_row_mathmodeltab_no_identifiers", 0) +
            result.get("skipped_row_mathmodeltab_invalid_formula", 0)
        )
    
    elif action == "flow4.sync_mathmodels":
        # Stats from MathModelSyncService.sync_sheet_to_db
        summary["total"] = result.get("row_count", 0)
        summary["success"] = result.get("updated", 0)
        summary["skipped"] = result.get("skipped_no_initiative", 0) + result.get("skipped_no_formula", 0)

    elif action == "flow4.sync_params":
        # Stats from ParamsSyncService.sync_sheet_to_db
        summary["total"] = result.get("row_count", 0)
        summary["success"] = result.get("upserts", 0)
        summary["skipped"] = result.get("skipped_no_initiative", 0) + result.get("skipped_no_name", 0)
    
    # Flow 0 actions
    elif action == "flow0.intake_sync":
        # Boolean flag, treat as single-unit task for UX clarity
        synced = bool(result.get("synced"))
        summary["total"] = 1
        summary["success"] = 1 if synced else 0
        summary["failed"] = 0 if synced else 1
    
    return summary


# ----------------------------
# Claim + execute
# ----------------------------

def execute_next_queued_run(db: Session) -> Optional[ActionRun]:
    """
    Atomically claim one queued ActionRun, execute it, update status/result.

    Returns the ActionRun if one was executed; None if no queued runs.
    """
    run = _claim_one_queued(db)
    if not run:
        return None

    logger.info("action_run.start", extra={"run_id": run.run_id, "action": run.action})

    try:
        ctx = _build_action_context(run.payload_json)  # type: ignore[arg-type]
        fn = _resolve_action(run.action)  # type: ignore[arg-type]
        result = fn(db, ctx)
        
        # Wrap result with normalized summary for UI consistency
        summary = _extract_summary(run.action, result)  # type: ignore[arg-type]
        wrapped_result = {
            "raw": result,
            "summary": summary,
        }

        run.status = STATUS_SUCCESS  # type: ignore[assignment]
        run.result_json = wrapped_result  # type: ignore[assignment]
        run.error_text = None  # type: ignore[assignment]
        run.finished_at = _now()  # type: ignore[assignment]

        db.commit()
        logger.info("action_run.success", extra={"run_id": run.run_id, "action": run.action})
        return run

    except Exception:
        # record failure; do not re-raise to keep worker alive
        try:
            db.rollback()
        except Exception:
            pass

        # re-load the run row and mark failed
        run = db.query(ActionRun).filter(ActionRun.id == run.id).one()
        run.status = STATUS_FAILED  # type: ignore[assignment]
        
        # Store full traceback (truncated) for debugging
        error_msg = traceback.format_exc()
        if len(error_msg) > 5000:
            error_msg = error_msg[:5000] + "... (truncated)"
        run.error_text = error_msg  # type: ignore[assignment]
        
        run.finished_at = _now()  # type: ignore[assignment]
        db.commit()

        logger.exception("action_run.failed", extra={"run_id": run.run_id, "action": run.action})
        return run


def _claim_one_queued(db: Session) -> Optional[ActionRun]:
    """
    Claim one queued action run.

    Uses SELECT ... FOR UPDATE SKIP LOCKED when available to prevent double execution
    under concurrent workers. Falls back to plain select for SQLite/dev environments.
    """
    try:
        # Try Postgres-style locking first
        stmt = (
            select(ActionRun)
            .where(ActionRun.status == STATUS_QUEUED)
            .order_by(ActionRun.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        run = db.execute(stmt).scalars().first()
    except Exception:
        # Fallback for SQLite or other DBs without SKIP LOCKED support
        logger.warning("FOR UPDATE SKIP LOCKED not supported, falling back to plain select (single-worker mode)")
        stmt = (
            select(ActionRun)
            .where(ActionRun.status == STATUS_QUEUED)
            .order_by(ActionRun.created_at.asc())
            .limit(1)
        )
        run = db.execute(stmt).scalars().first()
    
    if not run:
        return None

    run.status = STATUS_RUNNING  # type: ignore[assignment]
    run.started_at = _now()  # type: ignore[assignment]
    db.commit()
    db.refresh(run)
    return run


def _build_action_context(payload: Dict[str, Any]) -> ActionContext:
    """Build execution context with lazy dependency resolution.
    
    Note: Creates a new SheetsClient per action run. This is fine for v1 single-worker
    mode, but could be optimized with client pooling for multi-worker deployments.
    """
    service = get_sheets_service()
    sheets_client = SheetsClient(service)

    action = str(payload.get("action") or "")
    llm_client: Optional[LLMClient] = None
    
    # Only instantiate LLM when needed
    if any(action.startswith(prefix) for prefix in ["flow4.suggest_mathmodels", "flow4.seed_params"]):
        llm_client = LLMClient()

    return ActionContext(payload=payload, sheets_client=sheets_client, llm_client=llm_client)


# ----------------------------
# Action registry + implementations
# ----------------------------

def _resolve_action(action: str) -> ActionFn:
    action = action.strip()
    if action not in _ACTION_REGISTRY:
        raise ValueError(f"Unknown action: {action}")
    return _ACTION_REGISTRY[action]


# ---------- Flow 3 actions ----------

def _action_flow3_compute_all(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    options = (ctx.payload.get("options") or {}) if isinstance(ctx.payload.get("options"), dict) else {}
    commit_every = options.get("commit_every")

    service = ScoringService(db)
    processed = service.compute_all_frameworks(commit_every=commit_every)
    return {"processed": processed}


def _action_flow3_write_scores(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}

    # Prefer explicit sheet_context, fallback to settings.PRODUCT_OPS
    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    tab = sheet_ctx.get("tab") or (settings.PRODUCT_OPS.scoring_inputs_tab if settings.PRODUCT_OPS else "Scoring_Inputs")

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    updated = run_flow3_write_scores_to_sheet(db, spreadsheet_id=spreadsheet_id, tab_name=tab)
    return {"updated_initiatives": updated}


def _action_flow3_sync_inputs(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = (ctx.payload.get("options") or {}) if isinstance(ctx.payload.get("options"), dict) else {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}

    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    tab = sheet_ctx.get("tab") or (settings.PRODUCT_OPS.scoring_inputs_tab if settings.PRODUCT_OPS else "Scoring_Inputs")
    commit_every = options.get("commit_every")

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    updated = run_flow3_sync_inputs_to_initiatives(db, spreadsheet_id=spreadsheet_id, tab_name=tab, commit_every=commit_every)
    return {"updated": updated}


# ---------- Flow 2 actions ----------

def _action_flow2_activate(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    options = (ctx.payload.get("options") or {}) if isinstance(ctx.payload.get("options"), dict) else {}
    fw_raw = options.get("framework")  # optional: "RICE"/"WSJF"/"MATH_MODEL"
    batch_size = options.get("commit_every")
    only_missing = bool(options.get("only_missing", True))

    fw: Optional[ScoringFramework] = None
    if fw_raw:
        fw = ScoringFramework(str(fw_raw).upper())

    activated = run_scoring_batch(
        db=db,
        framework=fw,
        commit_every=batch_size,
        only_missing_scores=only_missing,
    )
    return {"activated": activated, "framework": (fw.value if fw else "AUTO")}


# ---------- Flow 1 actions ----------

def _action_flow1_backlog_sync(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    # v1: run all configured backlog sync targets (DB → sheet only)
    run_all_backlog_sync(db)
    return {"synced": True}


def _action_flow1_full_sync(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    # Full Flow 1 cycle: intake sync → backlog update → backlog sync
    options = (ctx.payload.get("options") or {}) if isinstance(ctx.payload.get("options"), dict) else {}
    allow_status_override = bool(options.get("allow_status_override_global", False))
    backlog_commit_every = options.get("backlog_commit_every")
    product_org = options.get("product_org")

    result = run_flow1_full_sync(
        db=db,
        allow_status_override_global=allow_status_override,
        backlog_commit_every=backlog_commit_every,
        product_org=product_org,
    )
    
    return {
        "completed": True,
        "intake_sync_completed": result["intake_sync_completed"],
        "backlog_update_completed": result["backlog_update_completed"],
        "backlog_update_error": result["backlog_update_error"],
        "backlog_sync_completed": result["backlog_sync_completed"],
        "substeps": result["substeps"],
    }


# ---------- Flow 4 actions ----------

def _action_flow4_suggest_mathmodels(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    assert ctx.llm_client is not None, "LLM client required for this action"

    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}

    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    tab = sheet_ctx.get("tab") or (settings.PRODUCT_OPS.mathmodels_tab if settings.PRODUCT_OPS else "MathModels")

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    max_rows = options.get("limit")
    force = bool(options.get("force", False))
    max_llm_calls = int(options.get("max_llm_calls", 10))

    stats = run_math_model_generation_job(
        db=db,
        sheets_client=ctx.sheets_client,
        llm_client=ctx.llm_client,
        spreadsheet_id=spreadsheet_id,
        tab_name=tab,
        max_rows=max_rows,
        force=force,
        max_llm_calls=max_llm_calls,
    )
    return stats


def _action_flow4_seed_params(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    assert ctx.llm_client is not None, "LLM client required for this action"

    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}

    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    mathmodels_tab = options.get("mathmodels_tab") or (settings.PRODUCT_OPS.mathmodels_tab if settings.PRODUCT_OPS else "MathModels")
    params_tab = options.get("params_tab") or (settings.PRODUCT_OPS.params_tab if settings.PRODUCT_OPS else "Params")
    max_llm_calls = int(options.get("max_llm_calls", 10))
    limit = options.get("limit")

    stats = run_param_seeding_job(
        sheets_client=ctx.sheets_client,
        spreadsheet_id=spreadsheet_id,
        mathmodels_tab=str(mathmodels_tab),
        params_tab=str(params_tab),
        llm_client=ctx.llm_client,
        max_llm_calls=max_llm_calls,
        limit=limit,
    )
    
    return stats.summary()


def _action_flow4_sync_mathmodels(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}

    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    tab = sheet_ctx.get("tab") or (settings.PRODUCT_OPS.mathmodels_tab if settings.PRODUCT_OPS else "MathModels")
    commit_every = int(options.get("commit_every", settings.SCORING_BATCH_COMMIT_EVERY))

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    svc = MathModelSyncService(ctx.sheets_client)
    return svc.sync_sheet_to_db(db, spreadsheet_id=str(spreadsheet_id), tab_name=str(tab), commit_every=commit_every)


def _action_flow4_sync_params(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}

    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    tab = sheet_ctx.get("tab") or (settings.PRODUCT_OPS.params_tab if settings.PRODUCT_OPS else "Params")
    commit_every = int(options.get("commit_every", settings.SCORING_BATCH_COMMIT_EVERY))

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    svc = ParamsSyncService(ctx.sheets_client)
    return svc.sync_sheet_to_db(db, spreadsheet_id=str(spreadsheet_id), tab_name=str(tab), commit_every=commit_every)


# ---------- Flow 0 actions ----------

def _action_flow0_intake_sync(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    options = (ctx.payload.get("options") or {}) if isinstance(ctx.payload.get("options"), dict) else {}
    allow_status_override = bool(options.get("allow_status_override_global", False))

    run_sync_all_intake_sheets(db=db, allow_status_override_global=allow_status_override)
    return {"synced": True}


# ----------------------------
# Action registry (module-level constant)
# ----------------------------

_ACTION_REGISTRY: Dict[str, ActionFn] = {
    # Flow 3
    "flow3.compute_all_frameworks": _action_flow3_compute_all,
    "flow3.write_scores": _action_flow3_write_scores,
    "flow3.sync_inputs": _action_flow3_sync_inputs,

    # Flow 2
    "flow2.activate": _action_flow2_activate,

    # Flow 1
    "flow1.backlog_sync": _action_flow1_backlog_sync,
    "flow1.full_sync": _action_flow1_full_sync,

    # Flow 4
    "flow4.suggest_mathmodels": _action_flow4_suggest_mathmodels,
    "flow4.seed_params": _action_flow4_seed_params,
    "flow4.sync_mathmodels": _action_flow4_sync_mathmodels,
    "flow4.sync_params": _action_flow4_sync_params,

    # Flow 0
    "flow0.intake_sync": _action_flow0_intake_sync,
}
