# productroadmap_sheet_project/app/jobs/flow3_product_ops_job.py

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.initiative import Initiative
from app.sheets.client import SheetsClient, get_sheets_service
from app.sheets.scoring_inputs_reader import ScoringInputsReader, ScoringInputsRow
from app.sheets.productops_writer import write_scores_to_productops_sheet
from app.utils.provenance import Provenance, token


class ScoringInputsFormatter(logging.Formatter):
    """Custom formatter that includes scoring-specific fields when present."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Build base message
        base = super().format(record)
        
        # Add scoring fields if present (using getattr for dynamic attributes)
        extra_parts = []
        initiative_key = getattr(record, 'initiative_key', None)
        if initiative_key:
            extra_parts.append(f"initiative={initiative_key}")
        
        active_framework = getattr(record, 'active_framework', None)
        if active_framework is not None:
            extra_parts.append(f"active_framework={active_framework}")
        
        frameworks = getattr(record, 'frameworks', None)
        if frameworks is not None:
            extra_parts.append(f"frameworks={frameworks}")
        
        count = getattr(record, 'count', None)
        if count is not None:
            extra_parts.append(f"count={count}")
        
        updated = getattr(record, 'updated', None)
        if updated is not None:
            extra_parts.append(f"updated={updated}")
        
        if extra_parts:
            return f"{base} | {' '.join(extra_parts)}"
        return base


# Only set up handler if not already configured (avoid duplicate handlers)
logger = logging.getLogger(__name__)
if not logger.handlers:
    formatter = ScoringInputsFormatter("%(asctime)s [%(levelname)s] %(name)s :: %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def _get_product_ops_reader(spreadsheet_id: Optional[str] = None, tab_name: Optional[str] = None) -> ScoringInputsReader:
    sheet_id = spreadsheet_id or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    tab = tab_name or (settings.PRODUCT_OPS.scoring_inputs_tab if settings.PRODUCT_OPS else None) or "Scoring_Inputs"
    if not sheet_id:
        raise ValueError("PRODUCT_OPS is not configured and no spreadsheet_id override was provided.")
    service = get_sheets_service()
    client = SheetsClient(service)
    return ScoringInputsReader(client=client, spreadsheet_id=sheet_id, tab_name=tab)


def run_flow3_preview_inputs(*, spreadsheet_id: Optional[str] = None, tab_name: Optional[str] = None) -> List[ScoringInputsRow]:
    """Fetch and parse the Product Ops Scoring_Inputs tab; return parsed rows for inspection."""
    reader = _get_product_ops_reader(spreadsheet_id, tab_name)
    rows = reader.read()
    logger.info("flow3.preview.rows", extra={"count": len(rows)})
    sample = rows
    for r in sample:
        logger.debug(
            "flow3.preview.row",
            extra={
                "initiative_key": r.initiative_key,
                "active_framework": r.active_scoring_framework,
                "frameworks": list(r.framework_inputs.keys()),
            },
        )
    return rows


def run_flow3_sync_inputs_to_initiatives(
    db: Session,
    *,
    commit_every: Optional[int] = None,
    spreadsheet_id: Optional[str] = None,
    tab_name: Optional[str] = None,
    initiative_keys: Optional[List[str]] = None,
) -> int:
    """Strong sync: write Scoring_Inputs values into Initiative fields.

    Unified naming convention across all layers (sheet → code → DB):
      - Sheet: "RICE: Reach" or "rice_reach" → Reader: rice_reach → DB: Initiative.rice_reach
      
    Mappings:
      - Initiative Key → finder
      - Active Scoring Framework → Initiative.active_scoring_framework
      - Use Math Model → Initiative.use_math_model
      - Strategic Priority Coefficient → Initiative.strategic_priority_coefficient
      - Risk Level → Initiative.risk_level
      - Time Sensitivity Score → Initiative.time_sensitivity_score
      
    RICE parameters:
      - RICE: Reach → Initiative.rice_reach
      - RICE: Impact → Initiative.rice_impact
      - RICE: Confidence → Initiative.rice_confidence
      - RICE: Effort → Initiative.rice_effort
      
    WSJF parameters:
      - WSJF: Business Value → Initiative.wsjf_business_value
      - WSJF: Time Criticality → Initiative.wsjf_time_criticality
      - WSJF: Risk Reduction → Initiative.wsjf_risk_reduction
      - WSJF: Job Size → Initiative.wsjf_job_size
      
    Shared parameter:
      - effort_engineering_days (can be populated from rice_effort or wsjf_job_size for backwards compatibility)

    Strong sync: empty cells → None in DB.
    """
    batch_size = commit_every or settings.SCORING_BATCH_COMMIT_EVERY

    rows = run_flow3_preview_inputs(spreadsheet_id=spreadsheet_id, tab_name=tab_name)
    # Filter to selected initiatives if provided
    if initiative_keys is not None:
        allowed = set(k for k in initiative_keys if k)
        rows = [r for r in rows if r.initiative_key in allowed]
    total = len(rows)
    updated = 0
    logger.info("flow3.sync.start", extra={"rows": total})

    # Index initiatives by key for faster lookups
    keys = [r.initiative_key for r in rows]
    if not keys:
        return 0
    existing: Dict[str, Initiative] = {}
    for i in db.query(Initiative).filter(Initiative.initiative_key.in_(keys)).all():
        existing[getattr(i, "initiative_key")] = i

    for idx, row in enumerate(rows, start=1):
        ini = existing.get(row.initiative_key)
        if not ini:
            logger.warning("flow3.sync.missing_initiative", extra={"initiative_key": row.initiative_key})
            continue

        # admin fields
        if row.active_scoring_framework is not None:
            ini.active_scoring_framework = row.active_scoring_framework  # type: ignore[assignment]
        if row.use_math_model is not None:
            ini.use_math_model = bool(row.use_math_model)  # type: ignore[assignment]

        # extras (strong sync: always set; blank = default 1.0)
        spc = row.extras.get("strategic_priority_coefficient")
        ini.strategic_priority_coefficient = float(spc) if spc is not None else 1.0  # type: ignore[assignment]
        
        rl = row.extras.get("risk_level")
        ini.risk_level = str(rl) if rl else None  # type: ignore[assignment]
        
        # SCHEMA FIX: time_sensitivity_score is Float, not string
        ts = row.extras.get("time_sensitivity_score")
        ini.time_sensitivity_score = float(ts) if ts is not None else None  # type: ignore[assignment]

        # framework inputs (unified naming: sheet → reader → DB all use rice_reach, wsjf_job_size, etc.)
        rice = row.framework_inputs.get("RICE")
        if rice:
            # Direct mapping to new framework-prefixed DB fields
            ini.rice_reach = rice.get("rice_reach")  # type: ignore[assignment]
            ini.rice_impact = rice.get("rice_impact")  # type: ignore[assignment]
            ini.rice_confidence = rice.get("rice_confidence")  # type: ignore[assignment]
            ini.rice_effort = rice.get("rice_effort")  # type: ignore[assignment]
            
            # Also update effort_engineering_days for backwards compatibility
            if rice.get("rice_effort") is not None:
                ini.effort_engineering_days = rice.get("rice_effort")  # type: ignore[assignment]

        wsjf = row.framework_inputs.get("WSJF")
        if wsjf:
            # Direct mapping to new framework-prefixed DB fields
            ini.wsjf_business_value = wsjf.get("wsjf_business_value")  # type: ignore[assignment]
            ini.wsjf_time_criticality = wsjf.get("wsjf_time_criticality")  # type: ignore[assignment]
            ini.wsjf_risk_reduction = wsjf.get("wsjf_risk_reduction")  # type: ignore[assignment]
            ini.wsjf_job_size = wsjf.get("wsjf_job_size")  # type: ignore[assignment]
            
            # Also update effort_engineering_days for backwards compatibility (WSJF wins if both present)
            if wsjf.get("wsjf_job_size") is not None:
                ini.effort_engineering_days = wsjf.get("wsjf_job_size")  # type: ignore[assignment]

        ini.updated_source = token(Provenance.FLOW3_PRODUCTOPSSHEET_READ_INPUTS)  # type: ignore[assignment]
        updated += 1

        if batch_size and (idx % batch_size == 0):
            try:
                db.commit()
                logger.info("flow3.sync.batch_commit", extra={"count": idx})
            except Exception:
                db.rollback()
                logger.exception("flow3.sync.batch_commit_failed")

    try:
        db.commit()
        logger.info("flow3.sync.done", extra={"updated": updated})
    except Exception:
        db.rollback()
        logger.exception("flow3.sync.final_commit_failed")

    return updated


def run_flow3_write_scores_to_sheet(
    db: Session,
    *,
    spreadsheet_id: Optional[str] = None,
    tab_name: Optional[str] = None,
    initiative_keys: Optional[List[str]] = None,
    warnings_by_key: Optional[Dict[str, Any]] = None,
) -> int:
    """Flow 3.C Phase 2: Write per-framework scores from DB back to Product Ops sheet.

    This completes the round-trip for Flow 3:
    1. Flow 3.B: Sync inputs from sheet to DB (active_scoring_framework, rice_reach, etc.)
    2. Flow 2/3.C.1: Compute scores using ScoringService (stores in rice_value_score, wsjf_value_score)
    3. Flow 3.C.2 (this function): Write computed scores back to sheet

    Benefits:
    - PM can see computed scores for audit/validation
    - Both framework scores visible for comparison
    - Complete data lineage: inputs → DB → outputs → PM review

    Uses targeted cell updates (efficient):
    - Finds each initiative's row by initiative_key
    - Updates only the score columns (rice_value_score, wsjf_overall_score, etc.)
    - Batch updates via Google Sheets API

    Args:
        db: Database session
        spreadsheet_id: Override Product Ops spreadsheet ID
        tab_name: Override Scoring_Inputs tab name

    Returns:
        Number of initiatives with scores written to sheet
    """
    sheet_id = spreadsheet_id or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    tab = tab_name or (settings.PRODUCT_OPS.scoring_inputs_tab if settings.PRODUCT_OPS else None) or "Scoring_Inputs"
    if not sheet_id:
        raise ValueError("PRODUCT_OPS is not configured and no spreadsheet_id override was provided.")

    service = get_sheets_service()
    client = SheetsClient(service)

    try:
        count = write_scores_to_productops_sheet(
            db,
            client,
            sheet_id,
            tab,
            initiative_keys=initiative_keys,
            warnings_by_key=warnings_by_key,
        )
        logger.info("flow3.write_scores.done", extra={"updated": count})
        return count
    except Exception:
        logger.exception("flow3.write_scores.failed")
        raise
