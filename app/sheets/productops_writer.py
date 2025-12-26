# productroadmap_sheet_project/app/sheets/productops_writer.py
"""
Writer module for Product Ops Scoring_Inputs sheet output (score write-back).

Follows the same pattern as backlog_writer.py and intake_writer.py:
- Defines schema (output columns for per-framework scores)
- Implements targeted cell updates (not full regeneration)
- Used by Flow 3 jobs to write computed scores back to sheet
"""

from __future__ import annotations

import logging
from typing import Dict, List, Any, cast

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.sheets.client import SheetsClient
from app.utils.header_utils import normalize_header as _normalize_header
from app.utils.provenance import Provenance, token

from app.sheets.models import (
    PRODUCTOPS_SCORE_OUTPUT_COLUMNS,
    SCORE_FIELD_TO_HEADERS,
)

logger = logging.getLogger(__name__)

# Note: PRODUCTOPS_SCORE_OUTPUT_COLUMNS and SCORE_FIELD_TO_HEADERS are imported
# from app.sheets.models (centralized). Do not redefine locally.


def write_scores_to_productops_sheet(
    db: Session,
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str = "Scoring_Inputs",
    *,
    initiative_keys: List[str] | None = None,
) -> int:
    """Write per-framework scores from DB to Product Ops sheet using targeted cell updates.

    This is the output phase of Flow 3.C.2:
    - Reads per-framework scores from DB (rice_value_score, wsjf_overall_score, etc.)
    - Finds each initiative's row in the sheet by initiative_key
    - Updates ONLY the score columns (doesn't touch other columns)
    - Uses single batch_update_values API call for efficiency (all cells in one request)

    Args:
        db: Database session
        client: SheetsClient instance
        spreadsheet_id: Product Ops spreadsheet ID
        tab_name: Sheet tab name (default: "Scoring_Inputs")

    Returns:
        Number of initiatives with scores updated in sheet

    Side effects:
        - Updates Product Ops sheet cells for score columns via single batch API call
        - Logs progress and any missing initiatives
    """
    if not spreadsheet_id:
        raise ValueError("spreadsheet_id is required")

    # Step 1: Read sheet to get header row and find score column indices
    # Use explicit A1 range to ensure consistent header + body retrieval
    values = client.get_values(spreadsheet_id, f"{tab_name}!A1:ZZ")
    if not values or len(values) < 2:
        logger.warning("productops_writer.empty_sheet", extra={"tab": tab_name})
        return 0

    headers = values[0]
    norm_headers = [_normalize_header(h) for h in headers]

    # Build alias lookup: normalized alias -> canonical field
    alias_lookup: Dict[str, str] = {}
    for field, aliases in SCORE_FIELD_TO_HEADERS.items():
        for a in aliases:
            alias_lookup[_normalize_header(a)] = field

    # Step 2: Find which columns correspond to each score field + initiative_key
    col_map: Dict[str, int] = {}  # field_name -> column_index (0-based)
    for i, nh in enumerate(norm_headers):
        if nh == "initiative_key":
            col_map["initiative_key"] = i
            continue
        if nh in {"updated_source", "updated source"}:
            col_map["updated_source"] = i
            continue
        # If header matches any known alias, map to its canonical field
        if nh in alias_lookup:
            col_map[alias_lookup[nh]] = i

    if "initiative_key" not in col_map:
        logger.warning("productops_writer.no_key_column", extra={"tab": tab_name})
        return 0

    key_col = col_map["initiative_key"]

    # Step 3: Load initiatives from DB into memory (keyed by initiative_key)
    # Optimize: if initiative_keys provided, query only those keys
    if initiative_keys is not None and initiative_keys:
        initiatives_list = db.query(Initiative).filter(Initiative.initiative_key.in_(initiative_keys)).all()
    else:
        initiatives_list = db.query(Initiative).all()
    initiatives: Dict[str, Any] = cast(Dict[str, Any], {i.initiative_key: i for i in initiatives_list})

    logger.debug(
        "productops_writer.loaded_initiatives",
        extra={"count": len(initiatives), "score_columns": len(col_map) - 1},
    )

    # Step 4: Build batch update with all cell updates
    # Collect all updates into a single batch request for efficiency
    batch_updates: List[Dict[str, Any]] = []
    updated_initiatives: set = set()

    allowed: set[str] | None = None
    if initiative_keys is not None:
        allowed = set(k for k in initiative_keys if k)

    for row_idx, row_data in enumerate(values[1:], start=2):  # Start at row 2 (row 1 = headers)
        # Extract initiative key from this row
        key = (
            (row_data[key_col] if key_col < len(row_data) else "").strip()
            if key_col < len(row_data)
            else ""
        )
        if not key:
            continue
        if allowed is not None and key not in allowed:
            continue

        ini = initiatives.get(key)
        if not ini:
            logger.debug(
                "productops_writer.missing_initiative",
                extra={"initiative_key": key, "row": row_idx},
            )
            continue

        row_updated = False

        # For each score column, collect update if value exists
        for field, col_idx in col_map.items():
            if field == "initiative_key":
                continue
            if field == "updated_source":
                continue

            # Get value from DB
            score_value = getattr(ini, field, None)
            if score_value is None:
                continue  # Don't update empty scores (leave blank)

            # Add to batch
            cell_range = _cell_range_for_update(tab_name, col_idx, row_idx)
            batch_updates.append({
                "range": cell_range,
                "values": [[score_value]]
            })
            updated_initiatives.add(key)
            row_updated = True

        # If row had score updates and sheet has an Updated Source column, set it
        if row_updated and "updated_source" in col_map:
            us_col_idx = col_map["updated_source"]
            cell_range = _cell_range_for_update(tab_name, us_col_idx, row_idx)
            batch_updates.append({
                "range": cell_range,
                "values": [[token(Provenance.FLOW3_PRODUCTOPSSHEET_WRITE_SCORES)]],
            })

    # Step 5: Execute single batch update if we have any updates
    if batch_updates:
        try:
            client.batch_update_values(spreadsheet_id, batch_updates)
            logger.info(
                "productops_writer.done",
                extra={
                    "updated_initiatives": len(updated_initiatives),
                    "total_cells_updated": len(batch_updates),
                    "total_rows": len(values) - 1,
                },
            )
        except Exception:
            logger.exception(
                "productops_writer.batch_update_failed",
                extra={"num_updates": len(batch_updates)},
            )
            return 0
    else:
        logger.info(
            "productops_writer.no_updates",
            extra={"total_rows": len(values) - 1},
        )

    return len(updated_initiatives)


def write_status_to_productops_sheet(
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str,
    status_by_key: Dict[str, str],
) -> int:
    """Write per-row Status messages for selected initiatives.

    Finds the initiative_key and Status columns, and writes short messages for keys present
    in status_by_key. If Status column is missing, logs a warning and returns 0.
    """
    values = client.get_values(spreadsheet_id, f"{tab_name}!A1:ZZ")
    if not values or len(values) < 2:
        logger.warning("productops_writer.status.empty_sheet", extra={"tab": tab_name})
        return 0

    headers = values[0]
    norm_headers = [_normalize_header(h) for h in headers]

    # Locate initiative_key and Status columns
    key_col = None
    status_col = None
    for i, nh in enumerate(norm_headers):
        if nh == "initiative_key":
            key_col = i
        elif nh in {"status", "last_run_status", "run_status"}:
            status_col = i

    if key_col is None:
        logger.warning("productops_writer.status.no_key_column", extra={"tab": tab_name})
        return 0
    if status_col is None:
        logger.warning("productops_writer.status.no_status_column", extra={"tab": tab_name})
        return 0

    # Build batch updates only for keys we have messages for
    batch_updates: List[Dict[str, Any]] = []
    written = 0
    for row_idx, row_data in enumerate(values[1:], start=2):
        key = (
            (row_data[key_col] if key_col < len(row_data) else "").strip()
            if key_col < len(row_data)
            else ""
        )
        if not key:
            continue
        msg = status_by_key.get(key)
        if msg is None:
            continue
        cell_range = _cell_range_for_update(tab_name, status_col, row_idx)
        batch_updates.append({
            "range": cell_range,
            "values": [[msg]],
        })
        written += 1

    if batch_updates:
        try:
            client.batch_update_values(spreadsheet_id, batch_updates)
        except Exception:
            logger.exception("productops_writer.status.batch_update_failed", extra={"num_updates": len(batch_updates)})
            return 0

    return written


# Use shared header normalization from app.utils.header_utils


def _cell_range_for_update(tab_name: str, col_idx: int, row_idx: int) -> str:
    """Build A1 notation cell range for a single cell update.

    Args:
        tab_name: Sheet tab name
        col_idx: Column index (0-based)
        row_idx: Row index (1-based, where 1 = header)

    Returns:
        A1 notation range like "Scoring_Inputs!M2:M2"
    """
    col_letter = _col_index_to_a1(col_idx + 1)  # Convert to 1-based
    return f"{tab_name}!{col_letter}{row_idx}:{col_letter}{row_idx}"


def _col_index_to_a1(idx: int) -> str:
    """Convert column index (1-based) to A1 letter notation.

    Args:
        idx: Column index (1-based)

    Returns:
        Column letter(s) e.g., "A", "Z", "AA", "AB"
    """
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


__all__ = [
    "write_scores_to_productops_sheet",
    "write_status_to_productops_sheet",
    "PRODUCTOPS_SCORE_OUTPUT_COLUMNS",
    "SCORE_FIELD_TO_HEADERS",
]
