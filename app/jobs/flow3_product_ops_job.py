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
                raise

    try:
        db.commit()
        logger.info("flow3.sync.done", extra={"updated_count": updated})
    except Exception:
        db.rollback()
        logger.exception("flow3.sync.final_commit_failed")
        raise

    return updated


def run_flow3_write_scores_to_sheet(
    db: Session,
    *,
    client: Optional[SheetsClient] = None,
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
        client: Optional SheetsClient (if None, creates a new one)
        spreadsheet_id: Override Product Ops spreadsheet ID
        tab_name: Override Scoring_Inputs tab name
        initiative_keys: Optional filter for specific initiatives
        warnings_by_key: Optional warnings to include in status column

    Returns:
        Number of initiatives with scores written to sheet
    """
    sheet_id = spreadsheet_id or (settings.PRODUCT_OPS.spreadsheet_id if settings.PRODUCT_OPS else None)
    tab = tab_name or (settings.PRODUCT_OPS.scoring_inputs_tab if settings.PRODUCT_OPS else None) or "Scoring_Inputs"
    if not sheet_id:
        raise ValueError("PRODUCT_OPS is not configured and no spreadsheet_id override was provided.")

    # Use provided client or create new one (backwards compatible)
    if client is None:
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
        logger.info("flow3.write_scores.done", extra={"updated_count": count})
        return count
    except Exception:
        logger.exception("flow3.write_scores.failed")
        raise


def run_flow3_populate_initiatives(
    db: Session,
    *,
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str,
) -> Dict[str, int]:
    """Populate Scoring_Inputs tab with optimization candidate initiatives from DB.
    
    Production-grade implementation that:
    1. Uses ScoringInputsReader abstraction (handles header parsing, sparse sheets)
    2. Normalizes initiative keys for robust matching (INIT-4 == INIT-0004)
    3. Uses dedicated writer helper for appending
    4. Accepts sheets_client from caller (no redundant client creation)
    
    This enables the PM workflow:
    1. Mark initiatives as optimization candidates in Central Backlog
    2. Run "Populate Initiatives" action to bring them into Scoring_Inputs
    3. Edit framework parameters (rice_reach, wsjf_business_value, etc.) as needed
    4. Run "Score Selected" to compute and write back scores
    
    Args:
        db: Database session
        client: SheetsClient instance (passed from action context)
        spreadsheet_id: Product Ops spreadsheet ID
        tab_name: Scoring_Inputs tab name (must match configured tab)
        
    Returns:
        Dict with counts: {total_candidates, existing_in_sheet, newly_added}
        
    Raises:
        RuntimeError: On sheet read/write failures
    """
    from app.services.optimization.optimization_compiler import normalize_initiative_key
    from app.sheets.productops_writer import append_initiative_keys_to_scoring_inputs
    
    # Step 1: Query optimization candidates from DB
    candidates = db.query(Initiative).filter(
        Initiative.is_optimization_candidate.is_(True),
        Initiative.is_archived.is_(False),
    ).order_by(Initiative.initiative_key).all()
    
    total_candidates = len(candidates)
    
    logger.info("flow3.populate.candidates_found", extra={"count": total_candidates})
    
    if not candidates:
        return {"total_candidates": 0, "existing_in_sheet": 0, "newly_added": 0, "db_collisions": 0, "sheet_collisions": 0}
    
    # Normalize DB keys for robust matching
    # This handles variants like INIT-4, INIT-0004, init_4, etc.
    candidate_keys_raw: list[str] = [str(ini.initiative_key) for ini in candidates]
    candidate_keys_raw = [k for k in candidate_keys_raw if k]  # Filter empty strings
    
    # Duplicate detection: warn if multiple DB keys collapse to the same normalized key
    candidate_keys_normalized: dict[str, str] = {}
    db_collisions = 0
    for raw_key in candidate_keys_raw:
        norm_key = normalize_initiative_key(raw_key)
        if norm_key in candidate_keys_normalized:
            existing_raw = candidate_keys_normalized[norm_key]
            db_collisions += 1
            logger.warning(
                "flow3.populate.db_duplicate_collision",
                extra={
                    "normalized_key": norm_key,
                    "existing_raw": existing_raw,
                    "new_raw": raw_key,
                    "kept": existing_raw,  # first-wins
                }
            )
        else:
            candidate_keys_normalized[norm_key] = raw_key
    
    # Step 2: Read existing keys from Scoring_Inputs using the reader abstraction
    # ScoringInputsReader already handles:
    # - Header parsing with aliases
    # - Sparse sheet handling (skips empty rows gracefully)
    # - Proper column detection
    reader = ScoringInputsReader(client=client, spreadsheet_id=spreadsheet_id, tab_name=tab_name)
    existing_rows = reader.read()
    
    # Normalize existing keys for comparison (with duplicate detection)
    existing_keys_normalized: dict[str, str] = {}
    sheet_collisions = 0
    for row in existing_rows:
        if not row.initiative_key:
            continue
        norm_key = normalize_initiative_key(row.initiative_key)
        if norm_key in existing_keys_normalized:
            existing_raw = existing_keys_normalized[norm_key]
            sheet_collisions += 1
            logger.warning(
                "flow3.populate.sheet_duplicate_collision",
                extra={
                    "normalized_key": norm_key,
                    "existing_raw": existing_raw,
                    "new_raw": row.initiative_key,
                    "kept": existing_raw,  # first-wins
                }
            )
        else:
            existing_keys_normalized[norm_key] = row.initiative_key
    
    logger.info("flow3.populate.existing_keys", extra={"count": len(existing_keys_normalized)})
    
    # Step 3: Find new keys to add (compare normalized forms)
    new_normalized_keys = set(candidate_keys_normalized.keys()) - set(existing_keys_normalized.keys())
    
    if not new_normalized_keys:
        logger.info("flow3.populate.no_new_keys")
        # Count matches using normalized comparison
        matches = len(set(candidate_keys_normalized.keys()) & set(existing_keys_normalized.keys()))
        return {
            "total_candidates": total_candidates,
            "existing_in_sheet": matches,
            "newly_added": 0,
            "db_collisions": db_collisions,
            "sheet_collisions": sheet_collisions,
        }
    
    # Map back to original (canonical) keys for writing
    # Use the DB's canonical form (from candidate_keys_normalized mapping)
    new_keys_to_write = sorted([
        candidate_keys_normalized[nk] 
        for nk in new_normalized_keys 
        if nk in candidate_keys_normalized
    ])
    
    # Step 4: Append new keys using the writer helper
    # This handles:
    # - Finding the correct append position (robust to gaps)
    # - Batch writing for efficiency
    written = append_initiative_keys_to_scoring_inputs(
        client=client,
        spreadsheet_id=spreadsheet_id,
        tab_name=tab_name,
        initiative_keys=new_keys_to_write,
    )
    
    # Count matches for the response
    matches = len(set(candidate_keys_normalized.keys()) & set(existing_keys_normalized.keys()))
    
    logger.info(
        "flow3.populate.done",
        extra={
            "total_candidates": total_candidates,
            "existing": matches,
            "newly_added": written,
            "db_collisions": db_collisions,
            "sheet_collisions": sheet_collisions,
        }
    )
    
    return {
        "total_candidates": total_candidates,
        "existing_in_sheet": matches,
        "newly_added": written,
        "db_collisions": db_collisions,
        "sheet_collisions": sheet_collisions,
    }
