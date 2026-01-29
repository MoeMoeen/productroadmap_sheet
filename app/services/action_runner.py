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
from typing import Any, Callable, Dict, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.action_run import ActionRun
from app.services.product_ops.scoring import ScoringFramework
from app.services.product_ops.scoring_service import ScoringService

from app.jobs.backlog_sync_job import run_all_backlog_sync
from app.jobs.backlog_update_job import run_backlog_update
from app.jobs.flow1_full_sync_job import run_flow1_full_sync
from app.jobs.flow3_product_ops_job import run_flow3_write_scores_to_sheet, run_flow3_sync_inputs_to_initiatives
from app.jobs.flow2_scoring_activation_job import run_scoring_batch
from app.jobs.sync_intake_job import run_sync_all_intake_sheets

from app.sheets.client import SheetsClient, get_sheets_service
from app.services.product_ops.math_model_service import MathModelSyncService
from app.services.product_ops.metrics_config_sync_service import MetricsConfigSyncService
from app.services.product_ops.params_sync_service import ParamsSyncService
from app.services.product_ops.kpi_contributions_sync_service import KPIContributionsSyncService

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
    """Short human-friendly text for UI display (action runs table, Apps Script response)."""
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
    
    # PM jobs
    elif action == "pm.backlog_sync":
        # Reuses flow1.full_sync summary
        substeps = result.get("substeps", [])
        summary["total"] = 3  # Expected substeps
        summary["success"] = len(substeps)
        # Check for partial failure
        if not result.get("backlog_update_completed", True):
            summary["failed"] = 1
    
    elif action == "pm.score_selected":
        selected_count = result.get("selected_count", 0)
        skipped = result.get("skipped_no_key", 0)
        failed = result.get("failed_count", 0)
        summary["total"] = selected_count + skipped
        summary["success"] = selected_count - failed
        summary["skipped"] = skipped
        summary["failed"] = failed
    
    elif action == "pm.switch_framework":
        selected_count = result.get("selected_count", 0)
        skipped = result.get("skipped_no_key", 0)
        failed = result.get("failed_count", 0)
        summary["total"] = selected_count + skipped
        summary["success"] = selected_count - failed
        summary["skipped"] = skipped
        summary["failed"] = failed

    elif action == "pm.save_selected":
        selected_count = result.get("selected_count", 0)
        skipped = result.get("skipped_no_key", 0)
        failed = result.get("failed_count", 0)
        saved = result.get("saved_count", 0)
        summary["total"] = selected_count + skipped
        summary["success"] = saved
        summary["skipped"] = skipped
        summary["failed"] = failed

    elif action == "pm.suggest_math_model_llm":
        selected_count = result.get("selected_count", 0)
        skipped_no_key = result.get("skipped_no_key", 0)
        ok_count = result.get("ok_count", 0)
        skipped_count = result.get("skipped_count", 0)
        failed_count = result.get("failed_count", 0)
        # Total = all keys (valid + invalid); Success = OK (suggested); Skipped = blank keys + logic skips; Failed = FAILED statuses
        summary["total"] = selected_count + skipped_no_key
        summary["success"] = ok_count
        summary["skipped"] = skipped_no_key + skipped_count
        summary["failed"] = failed_count

    elif action == "pm.seed_math_params":
        selected_count = result.get("selected_count", 0)
        skipped_no_key = result.get("skipped_no_key", 0)
        ok_count = result.get("ok_count", 0)
        skipped_count = result.get("skipped_count", 0)
        failed_count = result.get("failed_count", 0)
        # Total = all keys (valid + invalid); Success = OK statuses; Skipped = blank keys + logic skips; Failed = FAILED statuses
        summary["total"] = selected_count + skipped_no_key
        summary["success"] = ok_count
        summary["skipped"] = skipped_no_key + skipped_count
        summary["failed"] = failed_count
    
    # PM optimization jobs (Flow 5)
    elif action == "pm.optimize_run_selected_candidates":
        input_count = result.get("input_candidates_count", 0)
        selected = result.get("selected_initiatives_count", 0)
        opt_status = result.get("optimization_status", "unknown")
        # Total = candidates considered; Success = initiatives selected by solver; Failed = 1 if optimization failed
        summary["total"] = input_count
        summary["success"] = selected if opt_status in {"success", "infeasible"} else 0
        summary["failed"] = 1 if opt_status == "failed" else 0
    
    elif action == "pm.optimize_run_all_candidates":
        input_count = result.get("input_candidates_count", 0)
        selected = result.get("selected_initiatives_count", 0)
        opt_status = result.get("optimization_status", "unknown")
        # Total = all candidates in scenario; Success = initiatives selected by solver; Failed = 1 if optimization failed
        summary["total"] = input_count
        summary["success"] = selected if opt_status in {"success", "infeasible"} else 0
        summary["failed"] = 1 if opt_status == "failed" else 0
    
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
    # Use exact equality for PM jobs (safer), startswith for Flow 4 (multiple variants)
    if action in {"pm.seed_math_params", "pm.suggest_math_model_llm"} or any(action.startswith(prefix) for prefix in ["flow4.suggest_mathmodels", "flow4.seed_params"]):
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


# ---------- PM Jobs ----------

def _action_pm_backlog_sync(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    """PM Job #1: Sync intake to backlog.
    
    Thin wrapper around flow1.full_sync (which includes flow0.intake_sync + backlog update + backlog sync).
    Reuses the Flow1 action implementation directly; returns structured result with pm_job metadata.
    
    Single ActionRun, server-side orchestration, no nested enqueues.
    """
    result = _action_flow1_full_sync(db, ctx)
    
    # Wrap with PM job metadata
    result["pm_job"] = "pm.backlog_sync"
    return result


def _action_pm_score_selected(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    """PM Job #2: Score selected initiatives.

    Orchestrates selection-scoped Flow 3: sync inputs → compute all frameworks → write scores.
    Writes per-row Status messages on the Scoring_Inputs tab.
    """
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    scope = ctx.payload.get("scope") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}
    if not isinstance(scope, dict):
        scope = {}

    cfg = settings.PRODUCT_OPS
    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (cfg.spreadsheet_id if cfg else None)
    tab = sheet_ctx.get("tab") or (cfg.scoring_inputs_tab if cfg else "Scoring_Inputs")
    commit_every = int(options.get("commit_every", settings.SCORING_BATCH_COMMIT_EVERY))

    keys = scope.get("initiative_keys") or []
    if not isinstance(keys, list):
        keys = []
    # sanitize: skip blanks, dedupe
    keys = [k for k in keys if isinstance(k, str) and k.strip()]
    keys = list(dict.fromkeys(keys))
    original_keys = scope.get("initiative_keys")
    skipped_no_key = (len(original_keys) - len(keys)) if isinstance(original_keys, list) else 0

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    # Early bail if no selected keys
    if not keys:
        logger.info("pm.score_selected.no_keys_selected", extra={"skipped_no_key": skipped_no_key})
        return {
            "pm_job": "pm.score_selected",
            "selected_count": 0,
            "updated_inputs": 0,
            "computed": 0,
            "written": 0,
            "skipped_no_key": skipped_no_key,
            "failed_count": 0,
            "substeps": [
                {"step": "flow3.sync_inputs", "status": "skipped", "reason": "no keys selected"},
                {"step": "flow3.compute_selected", "status": "skipped", "reason": "no keys selected"},
                {"step": "flow3.write_scores", "status": "skipped", "reason": "no keys selected"},
                {"step": "status_write", "status": "skipped", "reason": "no keys selected"},
            ],
        }

    # 1) Sync inputs for selected keys
    status_by_key: Dict[str, Optional[str]] = {k: None for k in keys}  # Initialize all keys; update as we go
    try:
        updated_inputs = run_flow3_sync_inputs_to_initiatives(
            db=db,
            commit_every=commit_every,
            spreadsheet_id=str(spreadsheet_id),
            tab_name=str(tab),
            initiative_keys=keys,
        )
    except Exception as e:
        logger.exception("pm.score_selected.sync_inputs_failed")
        for k in keys:
            status_by_key[k] = "FAILED: sync failed"
        # Best-effort status write before returning
        try:
            from app.sheets.productops_writer import write_status_to_sheet
            write_status_to_sheet(
                ctx.sheets_client,
                str(spreadsheet_id),
                str(tab),
                {k: v for k, v in status_by_key.items() if v is not None},
            )
        except Exception:
            logger.warning("pm.score_selected.status_write_failed_on_sync_error")
        return {
            "pm_job": "pm.score_selected",
            "selected_count": len(keys),
            "updated_inputs": 0,
            "computed": 0,
            "written": 0,
            "skipped_no_key": skipped_no_key,
            "failed_count": len(keys),
            "substeps": [
                {"step": "flow3.sync_inputs", "status": "failed", "error": str(e)[:50]},
            ],
        }

    # 2) Compute all frameworks for selected keys
    svc = ScoringService(db)
    try:
        computed = svc.compute_for_initiatives(keys, commit_every=commit_every)
    except Exception as e:
        logger.exception("pm.score_selected.compute_failed")
        for k in keys:
            status_by_key[k] = "FAILED: compute failed"
        # Best-effort status write before returning
        try:
            from app.sheets.productops_writer import write_status_to_sheet
            write_status_to_sheet(
                ctx.sheets_client,
                str(spreadsheet_id),
                str(tab),
                {k: v for k, v in status_by_key.items() if v is not None},
            )
        except Exception:
            logger.warning("pm.score_selected.status_write_failed_on_compute_error")
        return {
            "pm_job": "pm.score_selected",
            "selected_count": len(keys),
            "updated_inputs": updated_inputs,
            "computed": 0,
            "written": 0,
            "skipped_no_key": skipped_no_key,
            "failed_count": len(keys),
            "substeps": [
                {"step": "flow3.sync_inputs", "status": "ok", "count": updated_inputs},
                {"step": "flow3.compute_selected", "status": "failed", "error": str(e)[:50]},
            ],
        }

    # 3) Write scores back to sheet for selected keys
    try:
        written = run_flow3_write_scores_to_sheet(
            db=db,
            spreadsheet_id=str(spreadsheet_id),
            tab_name=str(tab),
            initiative_keys=keys,
            warnings_by_key=svc.latest_math_warnings or None,
        )
    except Exception as e:
        logger.exception("pm.score_selected.write_scores_failed")
        for k in keys:
            status_by_key[k] = "FAILED: write failed"
        # Best-effort status write before returning
        try:
            from app.sheets.productops_writer import write_status_to_sheet
            write_status_to_sheet(
                ctx.sheets_client,
                str(spreadsheet_id),
                str(tab),
                {k: v for k, v in status_by_key.items() if v is not None},
            )
        except Exception:
            logger.warning("pm.score_selected.status_write_failed_on_write_error")
        return {
            "pm_job": "pm.score_selected",
            "selected_count": len(keys),
            "updated_inputs": updated_inputs,
            "computed": computed,
            "written": 0,
            "kpi_contributions_written": 0,
            "skipped_no_key": skipped_no_key,
            "failed_count": len(keys),
            "substeps": [
                {"step": "flow3.sync_inputs", "status": "ok", "count": updated_inputs},
                {"step": "flow3.compute_selected", "status": "ok", "count": computed},
                {"step": "flow3.write_scores", "status": "failed", "error": str(e)[:50]},
            ],
        }

    # 3.5) Write KPI contributions back to KPI_Contributions tab (if exists)
    kpi_contributions_written = 0
    if cfg and hasattr(cfg, "kpi_contributions_tab"):
        kpi_tab = cfg.kpi_contributions_tab
        try:
            from app.sheets.kpi_contributions_writer import write_kpi_contributions_to_sheet
            kpi_contributions_written = write_kpi_contributions_to_sheet(
                db=db,
                client=ctx.sheets_client,
                spreadsheet_id=str(spreadsheet_id),
                tab_name=str(kpi_tab),
                initiative_keys=keys,
            )
            logger.info(
                "pm.score_selected.kpi_contributions_written",
                extra={"count": kpi_contributions_written, "tab": kpi_tab},
            )
        except Exception as e:
            logger.warning(
                "pm.score_selected.write_kpi_contributions_failed",
                extra={"error": str(e)[:200], "tab": kpi_tab},
            )
            # Non-fatal: continue with status write

    # All steps succeeded; mark all keys as OK
    for k in keys:
        status_by_key[k] = "OK"

    # 4) Per-row Status write (best-effort)
    try:
        from app.sheets.productops_writer import write_status_to_sheet
        write_status_to_sheet(
            ctx.sheets_client,
            str(spreadsheet_id),
            str(tab),
            {k: v for k, v in status_by_key.items() if v is not None},
        )
    except Exception:
        logger.warning("pm.score_selected.status_write_failed")

    return {
        "pm_job": "pm.score_selected",
        "selected_count": len(keys),
        "updated_inputs": updated_inputs,
        "computed": computed,
        "written": written,
        "kpi_contributions_written": kpi_contributions_written,
        "skipped_no_key": skipped_no_key,
        "failed_count": 0,
        "substeps": [
            {"step": "flow3.sync_inputs", "status": "ok", "count": updated_inputs},
            {"step": "flow3.compute_selected", "status": "ok", "count": computed},
            {"step": "flow3.write_scores", "status": "ok", "count": written},
            {"step": "flow3.write_kpi_contributions", "status": "ok", "count": kpi_contributions_written},
            {"step": "status_write", "status": "ok"},
        ],
    }


def _action_pm_suggest_math_model_llm(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    """PM Job #4a: Suggest math model formulas via LLM.

    For selected initiatives without approved math models:
    - Reads initiative context (description, KPIs, etc.)
    - Calls LLM to suggest: formula_text, assumptions_text, model_name, model_description
    - Writes suggestions back to MathModels tab (sheet only, does not set approved_by_user)
    - PM reviews/edits, then sets approved_by_user = TRUE to trigger pm.seed_math_params

    Does not seed params (that's pm.seed_math_params).
    Does not compute scores.
    
    Workflow:
      1. PM selects initiatives on MathModels tab
      2. Runs pm.suggest_math_model_llm → LLM generates formula + assumptions suggestions
      3. PM reviews/edits/approves (sets approved_by_user = TRUE)
      4. Runs pm.seed_math_params → Parameters seeded with LLM metadata
      5. PM fills param values on Params tab
      6. Runs pm.save_selected → Persists to DB
      7. Runs pm.score_selected → Computes math model scores
    """
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    scope = ctx.payload.get("scope") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}
    if not isinstance(scope, dict):
        scope = {}

    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    mathmodels_tab = settings.PRODUCT_OPS.mathmodels_tab if settings.PRODUCT_OPS else "MathModels"
    max_llm_calls = int(options.get("max_llm_calls", 10))

    keys = scope.get("initiative_keys") or []
    if not isinstance(keys, list):
        keys = []
    keys = [k for k in keys if isinstance(k, str) and k.strip()]
    keys = list(dict.fromkeys(keys))
    original_keys = scope.get("initiative_keys")
    skipped_no_key = (len(original_keys) - len(keys)) if isinstance(original_keys, list) else 0

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    # Early bail if no selected keys
    if not keys:
        logger.info("pm.suggest_math_model_llm.no_keys_selected", extra={"skipped_no_key": skipped_no_key})
        return {
            "pm_job": "pm.suggest_math_model_llm",
            "selected_count": 0,
            "suggested_models": 0,
            "skipped_no_key": skipped_no_key,
            "ok_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "substeps": [
                {"step": "model_suggestion", "status": "skipped", "reason": "no keys selected"},
            ],
        }

    from app.sheets.math_models_reader import MathModelsReader
    from app.sheets.math_models_writer import MathModelsWriter
    from app.llm.scoring_assistant import suggest_math_model_for_initiative
    from app.db.models.initiative import Initiative
    
    status_by_key: Dict[str, Optional[str]] = {k: None for k in keys}
    suggestions_to_write = []

    try:
        math_reader = MathModelsReader(ctx.sheets_client)
        math_writer = MathModelsWriter(ctx.sheets_client)
        assert ctx.llm_client is not None, "LLM client required for pm.suggest_math_model_llm"
        llm_client = ctx.llm_client


        # Read MathModels for selected keys
        all_math_rows = math_reader.get_rows_for_sheet(spreadsheet_id=str(spreadsheet_id), tab_name=mathmodels_tab)
        selected_math_rows = [(row_num, row) for row_num, row in all_math_rows if row.initiative_key in keys]
        found_keys = {row.initiative_key for _, row in selected_math_rows}
        missing_in_sheet = [k for k in keys if k not in found_keys]
        for k in missing_in_sheet:
            status_by_key[k] = "SKIPPED: Not found in MathModels tab"

        models_suggested = 0
        llm_calls = 0

        for row_number, math_row in selected_math_rows:
            key = math_row.initiative_key

            # Skip if already has a formula (already suggested or manually filled)
            if math_row.formula_text and math_row.formula_text.strip():
                status_by_key[key] = "SKIPPED: Formula already exists"
                continue

            # Check LLM limit
            if llm_calls >= max_llm_calls:
                status_by_key[key] = "SKIPPED: LLM call limit reached"
                continue

            # Fetch initiative from DB for context
            initiative = db.query(Initiative).filter(Initiative.initiative_key == key).one_or_none()
            if not initiative:
                status_by_key[key] = "SKIPPED: Initiative not found in DB"
                continue
            
            # Guard: check if we have sufficient context for LLM
            # If initiative lacks key fields AND PM didn't provide custom prompt, skip
            has_problem_context = bool(
                (initiative.problem_statement and initiative.problem_statement.strip())
                or (initiative.hypothesis and initiative.hypothesis.strip())
                or (initiative.llm_summary and initiative.llm_summary.strip())
                or (initiative.title and initiative.title.strip())
            )
            has_custom_prompt = bool(math_row.model_prompt_to_llm and math_row.model_prompt_to_llm.strip())
            
            if not has_problem_context and not has_custom_prompt:
                status_by_key[key] = "SKIPPED: Insufficient context (add model_prompt_to_llm or fill initiative fields)"
                continue

            # Call LLM to suggest model
            try:
                suggestion = suggest_math_model_for_initiative(initiative, math_row, llm_client)
                llm_calls += 1
                
                # Queue for batch write (LLM-owned columns only; assumptions_text is user-owned)
                suggestions_to_write.append({
                    "row_number": row_number,
                    "llm_suggested_formula_text": suggestion.llm_suggested_formula_text,
                    "llm_notes": suggestion.llm_notes,
                    "llm_suggested_metric_chain_text": suggestion.llm_suggested_metric_chain_text,
                })
                
                status_by_key[key] = "OK: Suggested formula (review and approve before seeding params)"
                models_suggested += 1

            except Exception as exc:
                logger.exception(f"pm.suggest_math_model_llm.llm_failed for {key}")
                status_by_key[key] = f"FAILED: LLM error: {str(exc)[:50]}"
                continue
        
        # Batch write all suggestions
        if suggestions_to_write:
            math_writer.write_suggestions_batch(
                spreadsheet_id=str(spreadsheet_id),
                tab_name=mathmodels_tab,
                suggestions=suggestions_to_write,
            )

    except Exception as e:
        logger.exception("pm.suggest_math_model_llm.failed")
        for k in keys:
            if status_by_key[k] is None:
                status_by_key[k] = f"FAILED: {str(e)[:50]}"
        # Best-effort status write
        try:
            from app.sheets.productops_writer import write_status_to_sheet
            write_status_to_sheet(ctx.sheets_client, str(spreadsheet_id), mathmodels_tab, {k: v for k, v in status_by_key.items() if v is not None})
        except Exception:
            logger.warning("pm.suggest_math_model_llm.status_write_failed_on_error")
        return {
            "pm_job": "pm.suggest_math_model_llm",
            "selected_count": len(keys),
            "suggested_models": 0,
            "skipped_no_key": skipped_no_key,
            "ok_count": 0,
            "skipped_count": 0,
            "failed_count": len(keys),
            "substeps": [{"step": "model_suggestion", "status": "failed", "error": str(e)[:50]}],
        }

    # Write status to MathModels tab
    try:
        from app.sheets.productops_writer import write_status_to_sheet
        write_status_to_sheet(ctx.sheets_client, str(spreadsheet_id), mathmodels_tab, {k: v for k, v in status_by_key.items() if v is not None})
    except Exception:
        logger.warning("pm.suggest_math_model_llm.status_write_failed")

    # Count statuses by prefix
    ok_count = sum(1 for v in status_by_key.values() if v and v.startswith("OK"))
    skipped_count = sum(1 for v in status_by_key.values() if v and v.startswith("SKIPPED"))
    failed_count = sum(1 for v in status_by_key.values() if v and v.startswith("FAILED"))

    return {
        "pm_job": "pm.suggest_math_model_llm",
        "selected_count": len(keys),
        "suggested_models": models_suggested,
        "skipped_no_key": skipped_no_key,
        "ok_count": ok_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "substeps": [
            {"step": "model_suggestion", "status": "ok", "suggested": models_suggested, "llm_calls": llm_calls},
        ],
    }


def _action_pm_seed_math_params(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    """PM Job #5: Seed math model parameters from approved formulas.

    For selected initiatives with approved math models:
    - Parses formula → extracts required params
    - Seeds missing params in Params tab (sheet only) with LLM metadata
    - Stops (does not compute scores)

    PM must then fill param values and run pm.score_selected to compute scores.
    """
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    scope = ctx.payload.get("scope") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}
    if not isinstance(scope, dict):
        scope = {}

    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    mathmodels_tab = settings.PRODUCT_OPS.mathmodels_tab if settings.PRODUCT_OPS else "MathModels"
    params_tab = settings.PRODUCT_OPS.params_tab if settings.PRODUCT_OPS else "Params"
    max_llm_calls = int(options.get("max_llm_calls", 10))

    keys = scope.get("initiative_keys") or []
    if not isinstance(keys, list):
        keys = []
    keys = [k for k in keys if isinstance(k, str) and k.strip()]
    keys = list(dict.fromkeys(keys))
    original_keys = scope.get("initiative_keys")
    skipped_no_key = (len(original_keys) - len(keys)) if isinstance(original_keys, list) else 0

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    # Early bail if no selected keys
    if not keys:
        logger.info("pm.seed_math_params.no_keys_selected", extra={"skipped_no_key": skipped_no_key})
        return {
            "pm_job": "pm.seed_math_params",
            "selected_count": 0,
            "models_processed": 0,
            "params_seeded": 0,
            "skipped_no_key": skipped_no_key,
            "failed_count": 0,
            "substeps": [
                {"step": "param_seeding", "status": "skipped", "reason": "no keys selected"},
            ],
        }

    # Import param seeding logic
    from app.sheets.math_models_reader import MathModelsReader
    from app.sheets.params_reader import ParamsReader
    from app.sheets.params_writer import ParamsWriter
    from app.utils.safe_eval import extract_identifiers, validate_formula

    status_by_key: Dict[str, Optional[str]] = {k: None for k in keys}

    try:
        math_reader = MathModelsReader(ctx.sheets_client)
        params_reader = ParamsReader(ctx.sheets_client)
        params_writer = ParamsWriter(ctx.sheets_client)
        assert ctx.llm_client is not None, "LLM client required for pm.build_math_model"
        llm_client = ctx.llm_client

        # Read MathModels for selected keys only
        all_math_rows = math_reader.get_rows_for_sheet(spreadsheet_id=str(spreadsheet_id), tab_name=mathmodels_tab)
        selected_math_rows = [(row_num, row) for row_num, row in all_math_rows if row.initiative_key in keys]
        found_keys = {row.initiative_key for _, row in selected_math_rows}
        missing_in_sheet = [k for k in keys if k not in found_keys]
        for k in missing_in_sheet:
            status_by_key[k] = "SKIPPED: Not found in MathModels tab"

        # Read existing params
        existing_params_rows = params_reader.get_rows_for_sheet(spreadsheet_id=str(spreadsheet_id), tab_name=params_tab)
        existing_keys: Set[tuple[str, str, str]] = {
            (row.initiative_key, row.framework or "MATH_MODEL", row.param_name)
            for _, row in existing_params_rows
        }

        models_processed = 0
        params_seeded = 0
        llm_calls = 0

        for row_number, math_row in selected_math_rows:
            key = math_row.initiative_key

            # Skip unapproved
            if not math_row.approved_by_user:
                status_by_key[key] = "SKIPPED: Math model not approved"
                continue

            # Skip if no formula
            if not math_row.formula_text:
                status_by_key[key] = "SKIPPED: No formula"
                continue

            # Validate formula
            errors = validate_formula(math_row.formula_text)
            # validate_formula contract: returns list[str]; empty list means valid
            if errors:
                status_by_key[key] = f"FAILED: Invalid formula: {errors[0][:50]}"
                continue

            # Extract identifiers
            try:
                identifiers = extract_identifiers(math_row.formula_text)
            except Exception as exc:
                status_by_key[key] = f"FAILED: Cannot parse formula: {str(exc)[:50]}"
                continue

            if not identifiers:
                status_by_key[key] = "SKIPPED: No parameters needed"
                continue

            # Find missing identifiers
            missing_identifiers = sorted(
                {ident for ident in identifiers if (key, "MATH_MODEL", ident) not in existing_keys}
            )

            if not missing_identifiers:
                status_by_key[key] = "OK: All parameters already seeded"
                models_processed += 1
                continue

            # Check LLM limit
            if llm_calls >= max_llm_calls:
                status_by_key[key] = "SKIPPED: LLM call limit reached"
                continue

            # Call LLM for metadata
            try:
                from app.llm.scoring_assistant import suggest_param_metadata_for_model
                suggestion = suggest_param_metadata_for_model(
                    initiative_key=key,
                    identifiers=missing_identifiers,
                    formula_text=math_row.formula_text,
                    llm=llm_client,
                )
                llm_calls += 1
            except Exception as exc:
                logger.exception(f"pm.build_math_model.llm_failed for {key}")
                status_by_key[key] = f"FAILED: LLM error: {str(exc)[:50]}"
                continue

            # Build params to append
            params_to_append = []
            seen_keys = set()
            for param_sugg in suggestion.params:
                if param_sugg.key not in missing_identifiers:
                    continue
                if param_sugg.key in seen_keys:
                    continue
                seen_keys.add(param_sugg.key)

                notes = f"LLM example: {param_sugg.example_value}" if param_sugg.example_value else ""
                params_to_append.append({
                    "initiative_key": key,
                    "param_name": param_sugg.key,
                    "param_display": param_sugg.name or param_sugg.key,
                    "description": param_sugg.description or "",
                    "unit": param_sugg.unit or "",
                    "source": param_sugg.source_hint or "ai_suggested",
                    "value": "",  # Empty: PM fills this
                    "approved": False,
                    "is_auto_seeded": True,
                    "framework": "MATH_MODEL",
                    "notes": notes,
                })

            if params_to_append:
                params_writer.append_new_params(
                    spreadsheet_id=str(spreadsheet_id),
                    tab_name=params_tab,
                    params=params_to_append,
                )
                params_seeded += len(params_to_append)
                # Update cache so duplicate identifiers in same run don't get seeded twice
                for p in params_to_append:
                    existing_keys.add((key, "MATH_MODEL", p["param_name"]))
                status_by_key[key] = f"OK: Seeded {len(params_to_append)} params; fill values in Params tab"
                models_processed += 1
            else:
                status_by_key[key] = "OK: All parameters already seeded"
                models_processed += 1

    except Exception as e:
        logger.exception("pm.seed_math_params.failed")
        for k in keys:
            if status_by_key[k] is None:
                status_by_key[k] = f"FAILED: {str(e)[:50]}"
        # Best-effort status write
        try:
            from app.sheets.productops_writer import write_status_to_sheet
            write_status_to_sheet(ctx.sheets_client, str(spreadsheet_id), mathmodels_tab, {k: v for k, v in status_by_key.items() if v is not None})
        except Exception:
            logger.warning("pm.seed_math_params.status_write_failed_on_error")
        return {
            "pm_job": "pm.seed_math_params",
            "selected_count": len(keys),
            "models_processed": 0,
            "params_seeded": 0,
            "skipped_no_key": skipped_no_key,
            "failed_count": len(keys),
            "substeps": [{"step": "param_seeding", "status": "failed", "error": str(e)[:50]}],
        }

    # Write status to MathModels tab
    try:
        from app.sheets.productops_writer import write_status_to_sheet
        write_status_to_sheet(ctx.sheets_client, str(spreadsheet_id), mathmodels_tab, {k: v for k, v in status_by_key.items() if v is not None})
    except Exception:
        logger.warning("pm.seed_math_params.status_write_failed")

    # Count statuses by prefix for accurate summary
    ok_count = sum(1 for v in status_by_key.values() if v and v.startswith("OK"))
    skipped_count = sum(1 for v in status_by_key.values() if v and v.startswith("SKIPPED"))
    failed_count = sum(1 for v in status_by_key.values() if v and v.startswith("FAILED"))

    return {
        "pm_job": "pm.seed_math_params",
        "selected_count": len(keys),
        "models_processed": models_processed,
        "params_seeded": params_seeded,
        "skipped_no_key": skipped_no_key,
        "ok_count": ok_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "substeps": [
            {"step": "param_seeding", "status": "ok", "models": models_processed, "params": params_seeded, "llm_calls": llm_calls},
        ],
    }


def _action_pm_switch_framework(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    """PM Job #3: Switch active scoring framework for selected initiatives.

    Local-only update: changes only the current sheet (Scoring_Inputs or Central_Backlog).
    No cross-sheet propagation. Branches based on sheet_context.tab.

    Orchestration (Branch A — Scoring_Inputs):
      1. Sync inputs from sheet to DB (ensures DB has latest active_scoring_framework)
      2. Activate chosen framework for selected initiatives (best-effort compute on missing)
      3. Write updated scores back to Scoring_Inputs
      4. Per-row status write

    Orchestration (Branch B — Central_Backlog):
      1. Save selected rows from Backlog into DB
      2. Activate chosen framework for selected initiatives
      3. Sync Central_Backlog view from DB
      4. Per-row status write (optional if Backlog has Status column)
    """
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    scope = ctx.payload.get("scope") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}
    if not isinstance(scope, dict):
        scope = {}

    cfg = settings.PRODUCT_OPS

    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (cfg.spreadsheet_id if cfg else None)
    tab = sheet_ctx.get("tab") or (cfg.scoring_inputs_tab if cfg else "Scoring_Inputs")
    commit_every = int(options.get("commit_every", settings.SCORING_BATCH_COMMIT_EVERY))

    keys = scope.get("initiative_keys") or []
    if not isinstance(keys, list):
        keys = []
    # Sanitize: skip blanks, dedupe
    keys = [k for k in keys if isinstance(k, str) and k.strip()]
    keys = list(dict.fromkeys(keys))
    original_keys = scope.get("initiative_keys")
    skipped_no_key = (len(original_keys) - len(keys)) if isinstance(original_keys, list) else 0

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    # Early bail if no selected keys
    if not keys:
        logger.info("pm.switch_framework.no_keys_selected", extra={"skipped_no_key": skipped_no_key})
        return {
            "pm_job": "pm.switch_framework",
            "tab": tab,
            "selected_count": 0,
            "activated": 0,
            "written": 0,
            "skipped_no_key": skipped_no_key,
            "substeps": [
                {"step": "sync_or_backlog_update", "status": "skipped", "reason": "no keys selected"},
                {"step": "activate_framework", "status": "skipped", "reason": "no keys selected"},
                {"step": "write_or_sync_view", "status": "skipped", "reason": "no keys selected"},
            ],
        }

    status_by_key: Dict[str, Optional[str]] = {k: None for k in keys}

    # Detect branch based on tab
    is_backlog_tab = "backlog" in str(tab).lower()

    if is_backlog_tab:
        # ========== BRANCH B: Central_Backlog ==========

        # Step B1: Save selected rows from Backlog into DB
        try:
            run_backlog_update(db, initiative_keys=keys, product_org=options.get("product_org"))
        except Exception as e:
            logger.exception("pm.switch_framework.backlog_update_failed")
            for k in keys:
                status_by_key[k] = "FAILED: backlog update failed"
            return {
                "pm_job": "pm.switch_framework",
                "tab": tab,
                "selected_count": len(keys),
                "activated": 0,
                "written": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys),
                "substeps": [
                    {"step": "sync_or_backlog_update", "status": "failed", "error": str(e)[:50]},
                ],
            }

        # Step B2: Activate for selected initiatives
        svc = ScoringService(db)
        try:
            activated = svc.activate_for_initiatives(keys, commit_every=commit_every)
        except Exception as e:
            logger.exception("pm.switch_framework.activate_failed")
            for k in keys:
                status_by_key[k] = "FAILED: activate failed"
            return {
                "pm_job": "pm.switch_framework",
                "tab": tab,
                "selected_count": len(keys),
                "activated": 0,
                "written": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys),
                "substeps": [
                    {"step": "sync_or_backlog_update", "status": "ok"},
                    {"step": "activate_framework", "status": "failed", "error": str(e)[:50]},
                ],
            }

        # Step B3: Sync Central_Backlog view from DB (full sync v1)
        try:
            run_all_backlog_sync(db)
        except Exception as e:
            logger.exception("pm.switch_framework.backlog_sync_failed")
            for k in keys:
                status_by_key[k] = "FAILED: backlog sync failed"
            return {
                "pm_job": "pm.switch_framework",
                "tab": tab,
                "selected_count": len(keys),
                "activated": activated,
                "written": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys),
                "substeps": [
                    {"step": "sync_or_backlog_update", "status": "ok"},
                    {"step": "activate_framework", "status": "ok", "count": activated},
                    {"step": "write_or_sync_view", "status": "failed", "error": str(e)[:50]},
                ],
            }

        # All steps succeeded
        for k in keys:
            status_by_key[k] = "OK"

        # Step B4: Status write (best-effort, optional)
        try:
            # Only attempt if Backlog sheet has Status column (we don't know for sure, so skip for now)
            pass
        except Exception:
            logger.warning("pm.switch_framework.status_write_failed")

        return {
            "pm_job": "pm.switch_framework",
            "tab": tab,
            "selected_count": len(keys),
            "activated": activated,
            "written": 1,  # Backlog full sync counts as 1 write operation
            "skipped_no_key": skipped_no_key,
            "failed_count": 0,
            "substeps": [
                {"step": "sync_or_backlog_update", "status": "ok"},
                {"step": "activate_framework", "status": "ok", "count": activated},
                {"step": "write_or_sync_view", "status": "ok"},
            ],
        }

    else:
        # ========== BRANCH A: Scoring_Inputs ==========

        # Step A1: Sync inputs from sheet to DB
        try:
            updated_inputs = run_flow3_sync_inputs_to_initiatives(
                db=db,
                commit_every=commit_every,
                spreadsheet_id=str(spreadsheet_id),
                tab_name=str(tab),
                initiative_keys=keys,
            )
        except Exception as e:
            logger.exception("pm.switch_framework.sync_inputs_failed")
            for k in keys:
                status_by_key[k] = "FAILED: sync failed"
            # Best-effort status write before returning
            try:
                from app.sheets.productops_writer import write_status_to_sheet
                write_status_to_sheet(
                    ctx.sheets_client,
                    str(spreadsheet_id),
                    str(tab),
                    {k: v for k, v in status_by_key.items() if v is not None},
                )
            except Exception:
                logger.warning("pm.switch_framework.status_write_failed_on_sync_error")
            return {
                "pm_job": "pm.switch_framework",
                "tab": tab,
                "selected_count": len(keys),
                "activated": 0,
                "written": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys),
                "substeps": [
                    {"step": "sync_or_backlog_update", "status": "failed", "error": str(e)[:50]},
                ],
            }

        # Step A2: Activate for selected initiatives
        svc = ScoringService(db)
        try:
            activated = svc.activate_for_initiatives(keys, commit_every=commit_every)
        except Exception as e:
            logger.exception("pm.switch_framework.activate_failed")
            for k in keys:
                status_by_key[k] = "FAILED: activate failed"
            # Best-effort status write before returning
            try:
                from app.sheets.productops_writer import write_status_to_sheet
                write_status_to_sheet(
                    ctx.sheets_client,
                    str(spreadsheet_id),
                    str(tab),
                    {k: v for k, v in status_by_key.items() if v is not None},
                )
            except Exception:
                logger.warning("pm.switch_framework.status_write_failed_on_activate_error")
            return {
                "pm_job": "pm.switch_framework",
                "tab": tab,
                "selected_count": len(keys),
                "activated": 0,
                "written": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys),
                "substeps": [
                    {"step": "sync_or_backlog_update", "status": "ok", "count": updated_inputs},
                    {"step": "activate_framework", "status": "failed", "error": str(e)[:50]},
                ],
            }

        # Step A3: Write updated scores back to Scoring_Inputs
        try:
            written = run_flow3_write_scores_to_sheet(
                db=db,
                spreadsheet_id=str(spreadsheet_id),
                tab_name=str(tab),
                initiative_keys=keys,
            )
        except Exception as e:
            logger.exception("pm.switch_framework.write_scores_failed")
            for k in keys:
                status_by_key[k] = "FAILED: write failed"
            # Best-effort status write before returning
            try:
                from app.sheets.productops_writer import write_status_to_sheet
                write_status_to_sheet(
                    ctx.sheets_client,
                    str(spreadsheet_id),
                    str(tab),
                    {k: v for k, v in status_by_key.items() if v is not None},
                )
            except Exception:
                logger.warning("pm.switch_framework.status_write_failed_on_write_error")
            return {
                "pm_job": "pm.switch_framework",
                "tab": tab,
                "selected_count": len(keys),
                "activated": activated,
                "written": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys),
                "substeps": [
                    {"step": "sync_or_backlog_update", "status": "ok", "count": updated_inputs},
                    {"step": "activate_framework", "status": "ok", "count": activated},
                    {"step": "write_or_sync_view", "status": "failed", "error": str(e)[:50]},
                ],
            }

        # All steps succeeded
        for k in keys:
            status_by_key[k] = "OK"

        # Step A4: Per-row status write (best-effort)
        try:
            from app.sheets.productops_writer import write_status_to_sheet
            write_status_to_sheet(
                ctx.sheets_client,
                str(spreadsheet_id),
                str(tab),
                {k: v for k, v in status_by_key.items() if v is not None},
            )
        except Exception:
            logger.warning("pm.switch_framework.status_write_failed")

        return {
            "pm_job": "pm.switch_framework",
            "tab": tab,
            "selected_count": len(keys),
            "activated": activated,
            "written": written,
            "skipped_no_key": skipped_no_key,
            "failed_count": 0,
            "substeps": [
                {"step": "sync_or_backlog_update", "status": "ok", "count": updated_inputs},
                {"step": "activate_framework", "status": "ok", "count": activated},
                {"step": "write_or_sync_view", "status": "ok", "count": written},
                {"step": "status_write", "status": "ok"},
            ],
        }


# ---------- PM Job #4 ----------

def _action_pm_save_selected(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    """PM Job #4: Save selected rows from current tab into DB (selection-scoped).

    Tab-aware behavior:
    - Scoring_Inputs: save editable input fields via Flow3 sync (no scoring compute/write)
    - MathModels: save math model fields via Flow4 sync
    - Params: save parameter rows via Flow4 sync
    - Central Backlog: save editable backlog fields via Flow1 backlog_update (no activate/sync)

    Always local-only (no cross-sheet propagation). Best-effort per-row Status write when supported.
    """
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    scope = ctx.payload.get("scope") or {}
    if not isinstance(sheet_ctx, dict):
        sheet_ctx = {}
    if not isinstance(options, dict):
        options = {}
    if not isinstance(scope, dict):
        scope = {}

    scope_type = scope.get("type") if isinstance(scope, dict) else None
    is_scope_all = scope_type == "all"

    cfg = settings.PRODUCT_OPS
    spreadsheet_id = sheet_ctx.get("spreadsheet_id") or (cfg.spreadsheet_id if cfg else None)
    tab = sheet_ctx.get("tab") or (cfg.scoring_inputs_tab if cfg else "Scoring_Inputs")
    commit_every = int(options.get("commit_every", settings.SCORING_BATCH_COMMIT_EVERY))

    keys = scope.get("initiative_keys") or []
    if not isinstance(keys, list):
        keys = []
    # Sanitize: skip blanks, dedupe
    keys = [k for k in keys if isinstance(k, str) and k.strip()]
    keys = list(dict.fromkeys(keys))
    original_keys = scope.get("initiative_keys")
    skipped_no_key = (len(original_keys) - len(keys)) if isinstance(original_keys, list) else 0

    metrics_kpi_keys = scope.get("kpi_keys") or []
    if not isinstance(metrics_kpi_keys, list):
        metrics_kpi_keys = []
    metrics_kpi_keys = [k for k in metrics_kpi_keys if isinstance(k, str) and k.strip()]
    metrics_kpi_keys = list(dict.fromkeys(metrics_kpi_keys))

    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id missing and PRODUCT_OPS not configured")

    is_metrics_config_tab = bool(cfg and tab == cfg.metrics_config_tab)
    is_kpi_contrib_tab = bool(cfg and tab == getattr(cfg, "kpi_contributions_tab", None))

    # Early bail if no selected keys (unless Metrics_Config/KPI_Contributions or explicit all-scope)
    if not keys and not is_metrics_config_tab and not is_kpi_contrib_tab and not is_scope_all:
        logger.info("pm.save_selected.no_keys_selected", extra={"skipped_no_key": skipped_no_key})
        return {
            "pm_job": "pm.save_selected",
            "tab": tab,
            "selected_count": 0,
            "saved_count": 0,
            "skipped_no_key": skipped_no_key,
            "failed_count": 0,
            "substeps": [
                {"step": "save", "status": "skipped", "reason": "no keys selected"},
                {"step": "status_write", "status": "skipped", "reason": "no keys selected"},
            ],
        }

    status_by_key: Dict[str, Optional[str]] = {k: None for k in keys}

    # Safer tab detection: prefer exact config matches, fallback to substring for Backlog
    tab_lc = str(tab).lower()

    if cfg and tab == getattr(cfg, "metrics_config_tab", None):
        # ---------- Branch M: Metrics_Config ----------
        try:
            svc = MetricsConfigSyncService(ctx.sheets_client)
            result = svc.sync_sheet_to_db(
                db=db,
                spreadsheet_id=str(spreadsheet_id),
                tab_name=str(tab),
                commit_every=commit_every,
                kpi_keys=metrics_kpi_keys or None,
            )
            saved = int(result.get("upserts", 0))
            row_count = int(result.get("row_count", 0))
        except Exception as e:
            logger.exception("pm.save_selected.metrics_config_sync_failed")
            return {
                "pm_job": "pm.save_selected",
                "tab": tab,
                "selected_count": len(metrics_kpi_keys),
                "saved_count": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(metrics_kpi_keys) or 1,
                "substeps": [
                    {"step": "save", "status": "failed", "error": str(e)[:50]},
                ],
            }

        return {
            "pm_job": "pm.save_selected",
            "tab": tab,
            "selected_count": len(metrics_kpi_keys) if metrics_kpi_keys else row_count,
            "saved_count": saved,
            "skipped_no_key": skipped_no_key,
            "failed_count": max(0, (len(metrics_kpi_keys) if metrics_kpi_keys else row_count) - saved),
            "substeps": [
                {"step": "save", "status": "ok", "count": saved},
            ],
        }

    if cfg and tab == getattr(cfg, "kpi_contributions_tab", None):
        # ---------- Branch K: KPI_Contributions ----------
        row_count_processed = 0
        writeback_count = 0
        try:
            svc = KPIContributionsSyncService(ctx.sheets_client)
            result = svc.sync_sheet_to_db(
                db=db,
                spreadsheet_id=str(spreadsheet_id),
                tab_name=str(tab),
                commit_every=commit_every,
                initiative_keys=keys or None,
            )
            saved = int(result.get("upserts", 0))
            unlocked = int(result.get("unlocked", 0))
            row_count_processed = int(result.get("row_count", 0))
            
            # FIX #1: Immediate writeback so PM sees updated source column
            try:
                from app.sheets.kpi_contributions_writer import write_kpi_contributions_to_sheet
                writeback_count = write_kpi_contributions_to_sheet(
                    db=db,
                    client=ctx.sheets_client,
                    spreadsheet_id=str(spreadsheet_id),
                    tab_name=str(tab),
                    initiative_keys=keys or None,
                )
                logger.info(
                    "pm.save_selected.kpi_contributions_writeback",
                    extra={"count": writeback_count},
                )
            except Exception as wb_err:
                logger.warning(
                    "pm.save_selected.kpi_contributions_writeback_failed",
                    extra={"error": str(wb_err)[:200]},
                )
                # Non-fatal: continue with response
                
        except Exception as e:
            logger.exception("pm.save_selected.kpi_contributions_sync_failed")
            for k in keys:
                status_by_key[k] = "FAILED: save failed"
            return {
                "pm_job": "pm.save_selected",
                "tab": tab,
                "selected_count": len(keys) if keys else row_count_processed,
                "saved_count": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys) or row_count_processed or 1,
                "substeps": [
                    {"step": "save", "status": "failed", "error": str(e)[:50]},
                ],
            }

        return {
            "pm_job": "pm.save_selected",
            "tab": tab,
            "selected_count": len(keys) if keys else row_count_processed,
            "saved_count": saved,
            "unlocked_count": unlocked,
            "writeback_count": writeback_count,
            "skipped_no_key": skipped_no_key,
            "failed_count": max(0, (len(keys) if keys else row_count_processed) - saved),
            "substeps": [
                {"step": "save", "status": "ok", "count": saved},
            ],
        }

    if cfg and tab == cfg.mathmodels_tab:
        # ---------- Branch B: MathModels ----------
        try:
            svc = MathModelSyncService(ctx.sheets_client)
            result = svc.sync_sheet_to_db(
                db=db,
                spreadsheet_id=str(spreadsheet_id),
                tab_name=str(tab),
                commit_every=commit_every,
                initiative_keys=keys,
            )
            saved = int(result.get("updated", 0))
        except Exception as e:
            logger.exception("pm.save_selected.mathmodels_sync_failed")
            for k in keys:
                status_by_key[k] = "FAILED: save failed"
            try:
                from app.sheets.productops_writer import write_status_to_productops_sheet as write_status_to_sheet
                write_status_to_sheet(
                    ctx.sheets_client,
                    str(spreadsheet_id),
                    str(tab),
                    {k: v for k, v in status_by_key.items() if v is not None},
                )
            except Exception:
                logger.warning("pm.save_selected.status_write_failed_on_mathmodels_error")
            return {
                "pm_job": "pm.save_selected",
                "tab": tab,
                "selected_count": len(keys),
                "saved_count": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys),
                "substeps": [
                    {"step": "save", "status": "failed", "error": str(e)[:50]},
                ],
            }

        for k in keys:
            status_by_key[k] = "OK"
        try:
            from app.sheets.productops_writer import write_status_to_productops_sheet as write_status_to_sheet
            write_status_to_sheet(
                ctx.sheets_client,
                str(spreadsheet_id),
                str(tab),
                {k: v for k, v in status_by_key.items() if v is not None},
            )
        except Exception:
            logger.warning("pm.save_selected.status_write_failed_mathmodels")

        return {
            "pm_job": "pm.save_selected",
            "tab": tab,
            "selected_count": len(keys),
            "saved_count": saved,
            "skipped_no_key": skipped_no_key,
            "failed_count": max(0, len(keys) - saved),
            "substeps": [
                {"step": "save", "status": "ok", "count": saved},
                {"step": "status_write", "status": "ok"},
            ],
        }

    if cfg and tab == cfg.params_tab:
        # ---------- Branch C: Params ----------
        try:
            svc = ParamsSyncService(ctx.sheets_client)
            result = svc.sync_sheet_to_db(
                db=db,
                spreadsheet_id=str(spreadsheet_id),
                tab_name=str(tab),
                commit_every=commit_every,
                initiative_keys=keys,
            )
            saved = int(result.get("upserts", 0))
        except Exception as e:
            logger.exception("pm.save_selected.params_sync_failed")
            for k in keys:
                status_by_key[k] = "FAILED: save failed"
            try:
                from app.sheets.productops_writer import write_status_to_productops_sheet as write_status_to_sheet
                write_status_to_sheet(
                    ctx.sheets_client,
                    str(spreadsheet_id),
                    str(tab),
                    {k: v for k, v in status_by_key.items() if v is not None},
                )
            except Exception:
                logger.warning("pm.save_selected.status_write_failed_on_params_error")
            return {
                "pm_job": "pm.save_selected",
                "tab": tab,
                "selected_count": len(keys),
                "saved_count": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys),
                "substeps": [
                    {"step": "save", "status": "failed", "error": str(e)[:50]},
                ],
            }

        for k in keys:
            status_by_key[k] = "OK"
        try:
            from app.sheets.productops_writer import write_status_to_productops_sheet as write_status_to_sheet
            write_status_to_sheet(
                ctx.sheets_client,
                str(spreadsheet_id),
                str(tab),
                {k: v for k, v in status_by_key.items() if v is not None},
            )
        except Exception:
            logger.warning("pm.save_selected.status_write_failed_params")

        return {
            "pm_job": "pm.save_selected",
            "tab": tab,
            "selected_count": len(keys),
            "saved_count": saved,
            "skipped_no_key": skipped_no_key,
            "failed_count": max(0, len(keys) - saved),
            "substeps": [
                {"step": "save", "status": "ok", "count": saved},
                {"step": "status_write", "status": "ok"},
            ],
        }

    if "backlog" in tab_lc:
        # ---------- Branch D: Central Backlog ----------
        try:
            saved = run_backlog_update(
                db,
                spreadsheet_id=str(spreadsheet_id),
                tab_name=str(tab),
                product_org=options.get("product_org"),
                commit_every=commit_every,
                initiative_keys=keys,
            )
        except Exception as e:
            logger.exception("pm.save_selected.backlog_update_failed")
            for k in keys:
                status_by_key[k] = "FAILED: save failed"
            # Best-effort status write (only if Backlog has a Status column; skip if not present)
            try:
                from app.sheets.productops_writer import write_status_to_productops_sheet as write_status_to_sheet
                write_status_to_sheet(
                    ctx.sheets_client,
                    str(spreadsheet_id),
                    str(tab),
                    {k: v for k, v in status_by_key.items() if v is not None},
                )
            except Exception:
                logger.warning("pm.save_selected.status_write_failed_on_backlog_error")
            return {
                "pm_job": "pm.save_selected",
                "tab": tab,
                "selected_count": len(keys),
                "saved_count": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys),
                "substeps": [
                    {"step": "save", "status": "failed", "error": str(e)[:50]},
                ],
            }

        for k in keys:
            status_by_key[k] = "OK"
        try:
            from app.sheets.productops_writer import write_status_to_productops_sheet as write_status_to_sheet
            write_status_to_sheet(
                ctx.sheets_client,
                str(spreadsheet_id),
                str(tab),
                {k: v for k, v in status_by_key.items() if v is not None},
            )
        except Exception:
            logger.warning("pm.save_selected.status_write_failed_backlog")

        saved_i = int(saved)
        return {
            "pm_job": "pm.save_selected",
            "tab": tab,
            "selected_count": len(keys),
            "saved_count": saved_i,
            "skipped_no_key": skipped_no_key,
            "failed_count": max(0, len(keys) - saved_i),
            "substeps": [
                {"step": "save", "status": "ok", "count": saved_i},
                {"step": "status_write", "status": "ok"},
            ],
        }

    # ---------- Branch E: Optimization Center Candidates ----------
    if "candidates" in tab_lc and "optimization" in tab_lc.replace("_", " "):
        try:
            from app.services.optimization.optimization_sync_service import sync_candidates_from_sheet
            result = sync_candidates_from_sheet(
                sheets_client=ctx.sheets_client,
                spreadsheet_id=str(spreadsheet_id),
                candidates_tab=str(tab),
                initiative_keys=keys or None,
                commit_every=commit_every,
                session=db,
            )
            saved = int(result.get("updated", 0))
            errors = result.get("errors", [])
        except Exception as e:
            logger.exception("pm.save_selected.candidates_sync_failed")
            return {
                "pm_job": "pm.save_selected",
                "tab": tab,
                "selected_count": len(keys),
                "saved_count": 0,
                "skipped_no_key": skipped_no_key,
                "failed_count": len(keys) or 1,
                "substeps": [
                    {"step": "save", "status": "failed", "error": str(e)[:50]},
                ],
            }

        return {
            "pm_job": "pm.save_selected",
            "tab": tab,
            "selected_count": len(keys) if keys else result.get("row_count", 0),
            "saved_count": saved,
            "skipped_no_key": skipped_no_key + result.get("skipped_no_key", 0),
            "failed_count": len(errors),
            "errors": errors[:5] if errors else [],  # Include first 5 errors
            "substeps": [
                {"step": "save", "status": "ok", "count": saved},
            ],
        }

    # ---------- Branch A: Scoring_Inputs (default) ----------
    try:
        saved = run_flow3_sync_inputs_to_initiatives(
            db=db,
            commit_every=commit_every,
            spreadsheet_id=str(spreadsheet_id),
            tab_name=str(tab),
            initiative_keys=(keys if keys else None) if is_scope_all else keys,
        )
    except Exception as e:
        logger.exception("pm.save_selected.inputs_sync_failed")
        for k in keys:
            status_by_key[k] = "FAILED: save failed"
        try:
            from app.sheets.productops_writer import write_status_to_productops_sheet as write_status_to_sheet
            write_status_to_sheet(
                ctx.sheets_client,
                str(spreadsheet_id),
                str(tab),
                {k: v for k, v in status_by_key.items() if v is not None},
            )
        except Exception:
            logger.warning("pm.save_selected.status_write_failed_on_inputs_error")
        return {
            "pm_job": "pm.save_selected",
            "tab": tab,
            "selected_count": len(keys),
            "saved_count": 0,
            "skipped_no_key": skipped_no_key,
            "failed_count": len(keys),
            "substeps": [
                {"step": "save", "status": "failed", "error": str(e)[:50]},
            ],
        }

    for k in keys:
        status_by_key[k] = "OK"
    try:
        from app.sheets.productops_writer import write_status_to_productops_sheet as write_status_to_sheet
        write_status_to_sheet(
            ctx.sheets_client,
            str(spreadsheet_id),
            str(tab),
            {k: v for k, v in status_by_key.items() if v is not None},
        )
    except Exception:
        logger.warning("pm.save_selected.status_write_failed_inputs")

    saved_i = int(saved)
    selected_count_report = len(keys) if keys else saved_i
    return {
        "pm_job": "pm.save_selected",
        "tab": tab,
        "selected_count": selected_count_report,
        "saved_count": saved_i,
        "skipped_no_key": skipped_no_key,
        "failed_count": max(0, selected_count_report - saved_i),
        "substeps": [
            {"step": "save", "status": "ok", "count": saved_i},
            {"step": "status_write", "status": "ok"},
        ],
    }

    # (No fallback needed; all branches return above)


def _action_pm_populate_candidates(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    """PM Job: Populate Optimization Candidates tab from DB (KPI contributions, constraints, status).
    
    Payload:
      - sheet_context: {spreadsheet_id, tab}
      - options: {scenario_name, constraint_set_name}
      - scope: {initiative_keys: list[str]} (optional - defaults to all optimization candidates)
    
    Orchestration:
      1. Extract scenario_name + constraint_set_name from options (required)
      2. Extract initiative keys from scope (or all if not provided)
      3. Read existing sheet keys ONCE to determine NEW vs EXISTING
      4. Query KPI metadata from OrganizationMetricConfig
      5. Load constraint set for specified scenario
      6. Write DB-derived columns in batch (KPI contributions, constraint flags, status)
      7. Preserve PM input columns (engineering_tokens, category, program_key, deadline_date)
      8. Skip formula columns (initiative_key, title, country, department, immediate_kpi_key)
    
    Returns:
      - populated_count: Number of initiatives written to sheet
      - skipped_no_key: Number of initiatives without initiative_key
      - failed_count: Number of write failures
    """
    from app.sheets.optimization_candidates_writer import populate_candidates_from_db
    
    sheet_ctx = ctx.payload.get("sheet_context") or {}
    options = ctx.payload.get("options") or {}
    scope = ctx.payload.get("scope") or {}
    
    # Get spreadsheet_id and tab from sheet_context (required)
    spreadsheet_id = sheet_ctx.get("spreadsheet_id")
    tab = sheet_ctx.get("tab") or "Candidates"
    
    if not spreadsheet_id:
        raise ValueError("sheet_context.spreadsheet_id is required for pm.populate_candidates")
    
    # Extract scenario_name + constraint_set_name from options (required)
    scenario_name = options.get("scenario_name")
    constraint_set_name = options.get("constraint_set_name")
    
    if not scenario_name or not constraint_set_name:
        logger.error("pm.populate_candidates.missing_params")
        return {
            "pm_job": "pm.populate_candidates",
            "tab": tab,
            "populated_count": 0,
            "skipped_no_key": 0,
            "failed_count": 0,
            "error": "Missing scenario_name or constraint_set_name in options",
            "substeps": [{"step": "validate", "status": "failed", "reason": "missing_params"}],
        }
    
    # Extract initiative keys from scope (optional filter)
    keys = scope.get("initiative_keys") or []
    if not isinstance(keys, list):
        keys = []
    
    # Sanitize: skip blanks, dedupe
    keys = [k for k in keys if isinstance(k, str) and k.strip()]
    keys = list(dict.fromkeys(keys))
    
    logger.info(
        "pm.populate_candidates.starting",
        extra={
            "spreadsheet_id": spreadsheet_id,
            "tab": tab,
            "scenario": scenario_name,
            "constraint_set": constraint_set_name,
            "filter_keys": len(keys) if keys else "all",
        }
    )
    
    try:
        result = populate_candidates_from_db(
            db=db,
            client=ctx.sheets_client,
            spreadsheet_id=str(spreadsheet_id),
            tab_name=str(tab),
            scenario_name=str(scenario_name),
            constraint_set_name=str(constraint_set_name),
            initiative_keys=keys if keys else None,
        )
        
        populated = result.get("populated_count", 0)
        skipped = result.get("skipped_no_key", 0)
        failed = result.get("failed_count", 0)
        
        logger.info(
            "pm.populate_candidates.completed",
            extra={"populated": populated, "skipped_no_key": skipped, "failed": failed}
        )
        
        return {
            "pm_job": "pm.populate_candidates",
            "tab": tab,
            "populated_count": populated,
            "skipped_no_key": skipped,
            "failed_count": failed,
            "substeps": [
                {"step": "read_existing", "status": "ok"},
                {"step": "populate", "status": "ok", "count": populated},
            ],
        }
        
    except Exception as e:
        logger.exception("pm.populate_candidates.failed")
        return {
            "pm_job": "pm.populate_candidates",
            "tab": tab,
            "populated_count": 0,
            "skipped_no_key": 0,
            "failed_count": 0,
            "error": str(e),
            "substeps": [{"step": "populate", "status": "failed", "error": str(e)}],
        }


def _action_pm_optimize_run_selected_candidates(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    """PM Job: Run optimization (Step 1+2+3 solver) on user-selected candidates.
    
    Reads Optimization Center sheet's Candidates tab and filters for is_selected_for_run=TRUE.
    
    Payload:
      - options: {scenario_name, constraint_set_name}
      - scope: {initiative_keys: list[str]} (optional - if provided, uses these instead of sheet)
    
    Orchestration:
      1. Read Candidates tab from Optimization Center sheet
      2. Filter for is_selected_for_run = TRUE
      3. Call run_flow5_optimization with scope_type="selected_only"
      4. Return result with run_id, status, selected_count, solver_status
    """
    from app.jobs.optimization_job import run_flow5_optimization
    from app.sheets.optimization_center_readers import CandidatesReader
    from app.services.optimization.optimization_sync_service import (
        sync_scenarios_from_sheet,
        sync_constraint_sets_from_sheets,
    )
    
    options = ctx.payload.get("options") or {}
    
    # Extract parameters
    scenario_name = options.get("scenario_name")
    constraint_set_name = options.get("constraint_set_name")
    
    if not scenario_name or not constraint_set_name:
        logger.error("pm.optimize_run_selected_candidates.missing_params")
        return {
            "pm_job": "pm.optimize_run_selected_candidates",
            "optimization_status": "failed",
            "error": "Missing scenario_name or constraint_set_name in options",
            "substeps": [{"step": "validate", "status": "failed", "reason": "missing_params"}],
        }
    
    # Check if scope.initiative_keys is provided (explicit selection)
    scope = ctx.payload.get("scope") or {}
    explicit_keys = scope.get("initiative_keys") or []
    
    # Track sync results for reporting
    synced_scenarios = []
    synced_constraints = []
    
    # AUTO-SYNC: Always sync scenarios and constraints from sheet to DB before optimization
    # This ensures DB has latest data regardless of selection method
    if not settings.OPTIMIZATION_CENTER:
        logger.error("pm.optimize_run_selected_candidates.no_config")
        return {
            "pm_job": "pm.optimize_run_selected_candidates",
            "optimization_status": "failed",
            "error": "Optimization Center sheet not configured",
            "substeps": [{"step": "config_check", "status": "failed", "reason": "no_config"}],
        }
    
    try:
        service = get_sheets_service()
        sheets_client = SheetsClient(service)
        
        logger.info("pm.optimize_run_selected_candidates.auto_sync_start")
        
        # 1. Sync scenarios first (constraints depend on scenarios existing)
        scenario_config_tab = settings.OPTIMIZATION_CENTER.scenario_config_tab or "Scenario_Config"
        synced_scenarios, scenario_errors = sync_scenarios_from_sheet(
            sheets_client=sheets_client,
            spreadsheet_id=settings.OPTIMIZATION_CENTER.spreadsheet_id,
            scenario_config_tab=scenario_config_tab,
            session=db,
        )
        
        if scenario_errors:
            logger.warning(
                "pm.optimize_run_selected_candidates.scenario_sync_errors",
                extra={"errors": scenario_errors}
            )
        
        logger.info(
            "pm.optimize_run_selected_candidates.scenarios_synced",
            extra={"count": len(synced_scenarios)}
        )
        
        # 2. Sync constraint sets (now that scenarios exist)
        constraints_tab = settings.OPTIMIZATION_CENTER.constraints_tab or "Constraints"
        targets_tab = settings.OPTIMIZATION_CENTER.targets_tab or "Targets"
        synced_constraints, constraint_messages = sync_constraint_sets_from_sheets(
            sheets_client=sheets_client,
            spreadsheet_id=settings.OPTIMIZATION_CENTER.spreadsheet_id,
            constraints_tab=constraints_tab,
            targets_tab=targets_tab,
            session=db,
        )
        
        logger.info(
            "pm.optimize_run_selected_candidates.constraints_synced",
            extra={"count": len(synced_constraints)}
        )
        
    except Exception as e:
        logger.exception("pm.optimize_run_selected_candidates.auto_sync_failed")
        return {
            "pm_job": "pm.optimize_run_selected_candidates",
            "optimization_status": "failed",
            "error": f"Auto-sync failed: {str(e)[:100]}",
            "substeps": [{"step": "auto_sync", "status": "failed", "error": str(e)[:50]}],
        }
    
    # Now determine selection method: explicit keys or sheet reading
    if explicit_keys and isinstance(explicit_keys, list):
        # Use explicitly provided keys (backwards compatibility)
        keys = [k.strip() for k in explicit_keys if isinstance(k, str) and k.strip()]
        keys = list(dict.fromkeys(keys))  # dedupe
        logger.info(
            "pm.optimize_run_selected_candidates.using_explicit_keys",
            extra={"count": len(keys)}
        )
    else:
        # Read from Optimization Center sheet (auto-sync already completed above)
        if not settings.OPTIMIZATION_CENTER:
            logger.error("pm.optimize_run_selected_candidates.no_config")
            return {
                "pm_job": "pm.optimize_run_selected_candidates",
                "optimization_status": "failed",
                "error": "Optimization Center sheet not configured",
                "substeps": [{"step": "read_sheet", "status": "failed", "reason": "no_config"}],
            }
        
        try:
            service = get_sheets_service()
            sheets_client = SheetsClient(service)
            reader = CandidatesReader(sheets_client)
            
            # Read candidates tab - returns List[Tuple[row_num, OptCandidateRow]]
            candidates_with_rows = reader.get_rows(
                spreadsheet_id=settings.OPTIMIZATION_CENTER.spreadsheet_id,
                tab_name=settings.OPTIMIZATION_CENTER.candidates_tab,
            )
            
            # Extract just the OptCandidateRow objects
            candidates = [row for _, row in candidates_with_rows]
            
            # Filter for is_selected_for_run = TRUE
            selected = [c for c in candidates if getattr(c, "is_selected_for_run", False)]
            keys = [str(c.initiative_key) for c in selected if c.initiative_key]
            
            logger.info(
                "pm.optimize_run_selected_candidates.read_from_sheet",
                extra={
                    "total_candidates": len(candidates),
                    "selected_count": len(keys),
                    "spreadsheet_id": settings.OPTIMIZATION_CENTER.spreadsheet_id,
                }
            )
        except Exception as e:
            logger.exception("pm.optimize_run_selected_candidates.sheet_read_failed")
            return {
                "pm_job": "pm.optimize_run_selected_candidates",
                "optimization_status": "failed",
                "error": f"Failed to read Candidates tab: {str(e)[:100]}",
                "substeps": [{"step": "read_sheet", "status": "failed", "error": str(e)[:50]}],
            }
    
    if not keys:
        logger.warning("pm.optimize_run_selected_candidates.no_valid_keys")
        return {
            "pm_job": "pm.optimize_run_selected_candidates",
            "input_candidates_count": 0,
            "skipped_no_key": 0,
            "optimization_status": "skipped",
            "reason": "No candidates selected (is_selected_for_run=TRUE not found)",
            "substeps": [{"step": "validate", "status": "skipped", "reason": "no_keys"}],
        }
    
    # Generate run_id (use local helper)
    run_id = _make_run_id()
    
    # Run optimization
    try:
        result = run_flow5_optimization(
            db=db,
            scenario_name=scenario_name,
            constraint_set_name=constraint_set_name,
            scope_type="selected_only",
            selected_initiative_keys=keys,
            run_id=run_id,
            solver_config=None,  # Use default config
        )
        
        return {
            "pm_job": "pm.optimize_run_selected_candidates",
            "run_id": result["run_id"],
            "scenario_name": result["scenario_name"],
            "constraint_set_name": result["constraint_set_name"],
            "scope_type": result["scope_type"],
            "input_candidates_count": len(keys),
            "skipped_no_key": 0,
            "optimization_status": result["status"],
            "selected_initiatives_count": result.get("selected_count", 0),
            "capacity_used_tokens": result.get("capacity_used_tokens", 0),
            "solver_status": result.get("solver_status", "unknown"),
            "feasibility_warnings": result.get("feasibility_warnings_count", 0),
            "substeps": [
                {"step": "auto_sync_scenarios", "status": "ok", "synced": len(synced_scenarios)},
                {"step": "auto_sync_constraints", "status": "ok", "synced": len(synced_constraints)},
                {"step": "read_sheet", "status": "ok", "selected_count": len(keys)},
                {"step": "build_problem", "status": "ok"},
                {"step": "feasibility_check", "status": "ok", "warnings": result.get("feasibility_warnings_count", 0)},
                {"step": "solve", "status": result["status"], "solver": result.get("solver_status", "unknown")},
            ],
        }
    
    except Exception as e:
        logger.exception("pm.optimize_run_selected_candidates.failed")
        return {
            "pm_job": "pm.optimize_run_selected_candidates",
            "input_candidates_count": len(keys),
            "skipped_no_key": 0,
            "optimization_status": "failed",
            "selected_initiatives_count": 0,
            "error": str(e)[:100],
            "substeps": [{"step": "solve", "status": "failed", "error": str(e)[:50]}],
        }


def _action_pm_optimize_run_all_candidates(db: Session, ctx: ActionContext) -> Dict[str, Any]:
    """PM Job: Run optimization on all candidates in scenario (full portfolio optimization).
    
    Payload:
      - options: {scenario_name, constraint_set_name}
    
    Orchestration:
      1. Auto-sync scenarios and constraints from sheet to DB
      2. Build optimization problem with scope_type="all_candidates"
      3. Run solver (capacity + governance + KPI optimization)
      4. Publish results to Runs/Results/Gaps tabs
      5. Return result with run_id, status, selected_count, solver_status
    """
    from app.jobs.optimization_job import run_flow5_optimization
    from app.services.optimization.optimization_sync_service import (
        sync_scenarios_from_sheet,
        sync_constraint_sets_from_sheets,
    )
    
    options = ctx.payload.get("options") or {}
    
    # Extract parameters
    scenario_name = options.get("scenario_name")
    constraint_set_name = options.get("constraint_set_name")
    
    if not scenario_name or not constraint_set_name:
        logger.error("pm.optimize_run_all_candidates.missing_params")
        return {
            "pm_job": "pm.optimize_run_all_candidates",
            "optimization_status": "failed",
            "error": "Missing scenario_name or constraint_set_name in options",
            "substeps": [{"step": "validate", "status": "failed", "reason": "missing_params"}],
        }
    
    # AUTO-SYNC: Sync scenarios and constraints from sheet to DB before optimization
    if not settings.OPTIMIZATION_CENTER:
        logger.error("pm.optimize_run_all_candidates.no_config")
        return {
            "pm_job": "pm.optimize_run_all_candidates",
            "optimization_status": "failed",
            "error": "Optimization Center sheet not configured",
            "substeps": [{"step": "config_check", "status": "failed", "reason": "no_config"}],
        }
    
    synced_scenarios = []
    synced_constraints = []
    
    try:
        service = get_sheets_service()
        sheets_client = SheetsClient(service)
        
        logger.info("pm.optimize_run_all_candidates.auto_sync_start")
        
        # 1. Sync scenarios first (constraints depend on scenarios existing)
        scenario_config_tab = settings.OPTIMIZATION_CENTER.scenario_config_tab or "Scenario_Config"
        synced_scenarios, scenario_errors = sync_scenarios_from_sheet(
            sheets_client=sheets_client,
            spreadsheet_id=settings.OPTIMIZATION_CENTER.spreadsheet_id,
            scenario_config_tab=scenario_config_tab,
            session=db,
        )
        
        if scenario_errors:
            logger.warning(
                "pm.optimize_run_all_candidates.scenario_sync_errors",
                extra={"errors": scenario_errors}
            )
        
        logger.info(
            "pm.optimize_run_all_candidates.scenarios_synced",
            extra={"count": len(synced_scenarios)}
        )
        
        # 2. Sync constraint sets (now that scenarios exist)
        constraints_tab = settings.OPTIMIZATION_CENTER.constraints_tab or "Constraints"
        targets_tab = settings.OPTIMIZATION_CENTER.targets_tab or "Targets"
        synced_constraints, constraint_messages = sync_constraint_sets_from_sheets(
            sheets_client=sheets_client,
            spreadsheet_id=settings.OPTIMIZATION_CENTER.spreadsheet_id,
            constraints_tab=constraints_tab,
            targets_tab=targets_tab,
            session=db,
        )
        
        logger.info(
            "pm.optimize_run_all_candidates.constraints_synced",
            extra={"count": len(synced_constraints)}
        )
        
    except Exception as e:
        logger.exception("pm.optimize_run_all_candidates.auto_sync_failed")
        return {
            "pm_job": "pm.optimize_run_all_candidates",
            "optimization_status": "failed",
            "error": f"Auto-sync failed: {str(e)[:100]}",
            "substeps": [{"step": "auto_sync", "status": "failed", "error": str(e)[:50]}],
        }
    
    # Generate run_id (use local helper)
    run_id = _make_run_id()
    
    # Run optimization
    try:
        result = run_flow5_optimization(
            db=db,
            scenario_name=scenario_name,
            constraint_set_name=constraint_set_name,
            scope_type="all_candidates",
            selected_initiative_keys=None,
            run_id=run_id,
            solver_config=None,  # Use default config
        )
        
        return {
            "pm_job": "pm.optimize_run_all_candidates",
            "run_id": result["run_id"],
            "scenario_name": result["scenario_name"],
            "constraint_set_name": result["constraint_set_name"],
            "scope_type": result["scope_type"],
            "optimization_status": result["status"],
            "input_candidates_count": result.get("candidate_count", 0),
            "selected_initiatives_count": result.get("selected_count", 0),
            "capacity_used_tokens": result.get("capacity_used_tokens", 0),
            "solver_status": result.get("solver_status", "unknown"),
            "feasibility_warnings": result.get("feasibility_warnings_count", 0),
            "substeps": [
                {"step": "auto_sync_scenarios", "status": "ok", "synced": len(synced_scenarios)},
                {"step": "auto_sync_constraints", "status": "ok", "synced": len(synced_constraints)},
                {"step": "build_problem", "status": "ok"},
                {"step": "feasibility_check", "status": "ok", "warnings": result.get("feasibility_warnings_count", 0)},
                {"step": "solve", "status": result["status"], "solver": result.get("solver_status", "unknown")},
            ],
        }
    
    except Exception as e:
        logger.exception("pm.optimize_run_all_candidates.failed")
        return {
            "pm_job": "pm.optimize_run_all_candidates",
            "optimization_status": "failed",
            "input_candidates_count": 0,
            "selected_initiatives_count": 0,
            "error": str(e)[:100],
            "substeps": [{"step": "solve", "status": "failed", "error": str(e)[:50]}],
        }


## ---------- Action Registry ----------

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

    # PM Jobs (V1 + V2 Math Models)
    "pm.backlog_sync": _action_pm_backlog_sync,
    "pm.score_selected": _action_pm_score_selected,
    "pm.switch_framework": _action_pm_switch_framework,
    "pm.save_selected": _action_pm_save_selected,
    "pm.suggest_math_model_llm": _action_pm_suggest_math_model_llm,
    "pm.seed_math_params": _action_pm_seed_math_params,
    
    # PM Jobs (V3 Optimization)
    "pm.populate_candidates": _action_pm_populate_candidates,
    "pm.optimize_run_selected_candidates": _action_pm_optimize_run_selected_candidates,
    "pm.optimize_run_all_candidates": _action_pm_optimize_run_all_candidates,
}
