# productroadmap_sheet_project/app/sheets/kpi_contributions_writer.py
"""
Writer module for Product Ops KPI_Contributions sheet output (DB → sheet writeback).

System-generates the entire KPI_Contributions tab:
- initiative_key: From DB (system populates)
- kpi_contribution_json: Active contributions (PM can override, otherwise system-computed)
- kpi_contribution_computed_json: Always reflects latest system computation
- kpi_contribution_source: "math_model_derived" or "pm_override"
- notes: PM notes (preserved from sheet)
- run_status, updated_source, updated_at: System metadata columns

Logic:
- Query initiatives from DB (all or filtered)
- For each initiative, find existing row by initiative_key OR append new row
- Write system columns (initiative_key, computed_json, source, status, provenance)
- Preserve PM-editable columns (kpi_contribution_json, notes) if row exists
"""

from __future__ import annotations

import logging
import json
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.sheets.client import SheetsClient
from app.utils.header_utils import normalize_header as _normalize_header
from app.utils.provenance import Provenance, token
from app.sheets.models import KPI_CONTRIBUTIONS_HEADER_MAP

logger = logging.getLogger(__name__)

# Batch size guardrail to avoid Sheets API payload/range limits
_BATCH_UPDATE_CHUNK_SIZE = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_sheet_value(value: Any) -> Any:
    """Normalize values before sending to Sheets to avoid JSON serialization errors."""
    if value is None:
        return None
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value)
        except Exception:
            return str(value)
    return value


def write_kpi_contributions_to_sheet(
    db: Session,
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str = "KPI_Contributions",
    *,
    initiative_keys: Optional[List[str]] = None,
) -> int:
    """Write system-computed KPI contributions from DB to KPI_Contributions sheet.

    System-generates the entire KPI_Contributions tab with upsert logic:
    - For each initiative in DB, find existing row by initiative_key OR append new row
    - Write system columns: initiative_key, kpi_contribution_computed_json, 
      kpi_contribution_source, run_status, updated_source, updated_at
    - Preserve PM-editable columns: kpi_contribution_json, notes (if row already exists)

    Args:
        db: Database session
        client: SheetsClient instance
        spreadsheet_id: Product Ops spreadsheet ID
        tab_name: Sheet tab name (default: "KPI_Contributions")
        initiative_keys: Optional list of initiative keys to write (None = all)

    Returns:
        Number of initiatives written to sheet

    Side effects:
        - Updates existing rows or appends new rows via batch API calls
        - Preserves PM edits in kpi_contribution_json and notes columns
        - Logs progress
    """
    if not spreadsheet_id:
        raise ValueError("spreadsheet_id is required")

    # Step 1: Read header row to map column indices
    header_values = client.get_values(spreadsheet_id, f"{tab_name}!1:1")
    if not header_values or not header_values[0]:
        logger.warning("kpi_contributions_writer.empty_sheet", extra={"tab": tab_name})
        return 0

    headers = header_values[0]
    norm_headers = [_normalize_header(h) for h in headers]

    # Build alias lookup: normalized alias -> canonical field
    alias_lookup: Dict[str, str] = {}
    for field, aliases in KPI_CONTRIBUTIONS_HEADER_MAP.items():
        for a in aliases:
            alias_lookup[_normalize_header(a)] = field

    # Step 2: Map column indices for all known fields
    col_map: Dict[str, int] = {}  # field_name -> column_index (0-based)
    for i, nh in enumerate(norm_headers):
        if nh in alias_lookup:
            col_map[alias_lookup[nh]] = i

    if "initiative_key" not in col_map:
        logger.warning("kpi_contributions_writer.no_key_column", extra={"tab": tab_name})
        return 0

    key_col = col_map["initiative_key"]

    # Step 3: Read all existing initiative_key values to build row index map
    key_col_letter = _col_index_to_a1(key_col + 1)
    key_range = f"{tab_name}!{key_col_letter}2:{key_col_letter}"
    key_values_result = client.get_values(spreadsheet_id, key_range)
    existing_keys_raw: List[Any] = key_values_result.get("values", []) if key_values_result else []  # type: ignore[assignment]
    
    # Map initiative_key -> row_index (1-based, where 1 = header)
    row_index_by_key: Dict[str, int] = {}
    for offset, entry in enumerate(existing_keys_raw):
        if isinstance(entry, list):
            key = entry[0] if entry else ""
        else:
            key = entry
        key = str(key).strip()
        if key:
            row_index_by_key[key] = offset + 4  # Row 1=header, 2-3=metadata, data starts at 4

    next_append_row = len(existing_keys_raw) + 4  # Next empty row for append (skip header + 2 metadata rows)

    # Step 4: Load initiatives from DB
    if initiative_keys is not None and initiative_keys:
        initiatives_list = (
            db.query(Initiative)
            .filter(Initiative.initiative_key.in_(initiative_keys))  # type: ignore[arg-type]
            .all()
        )
    else:
        initiatives_list = db.query(Initiative).all()

    # Step 5: Build batch updates (update existing rows + append new rows)
    batch_updates: List[Dict[str, Any]] = []
    updated_initiatives: Set[str] = set()
    ts = _now_iso()

    for ini in initiatives_list:
        key = str(ini.initiative_key)  # type: ignore[arg-type]
        
        # Determine row index (existing or new)
        if key in row_index_by_key:
            row_idx = row_index_by_key[key]
        else:
            # Append new row
            row_idx = next_append_row
            next_append_row += 1

        # Write initiative_key (always)
        if "initiative_key" in col_map:
            col_idx = col_map["initiative_key"]
            cell_range = _cell_range_for_update(tab_name, col_idx, row_idx)
            batch_updates.append({
                "range": cell_range,
                "values": [[key]]
            })

        # Write kpi_contribution_computed_json (always)
        if "kpi_contribution_computed_json" in col_map:
            computed_val = ini.kpi_contribution_computed_json
            col_idx = col_map["kpi_contribution_computed_json"]
            cell_range = _cell_range_for_update(tab_name, col_idx, row_idx)
            batch_updates.append({
                "range": cell_range,
                "values": [[_to_sheet_value(computed_val)]]
            })

        # Write kpi_contribution_source (always)
        if "kpi_contribution_source" in col_map:
            source_val = ini.kpi_contribution_source or "math_model_derived"
            col_idx = col_map["kpi_contribution_source"]
            cell_range = _cell_range_for_update(tab_name, col_idx, row_idx)
            batch_updates.append({
                "range": cell_range,
                "values": [[source_val]]
            })

        # Write run_status (always "OK" for now)
        if "run_status" in col_map:
            col_idx = col_map["run_status"]
            cell_range = _cell_range_for_update(tab_name, col_idx, row_idx)
            batch_updates.append({
                "range": cell_range,
                "values": [["OK"]]
            })

        # Write updated_source (always)
        if "updated_source" in col_map:
            col_idx = col_map["updated_source"]
            cell_range = _cell_range_for_update(tab_name, col_idx, row_idx)
            batch_updates.append({
                "range": cell_range,
                "values": [[token(Provenance.FLOW3_PRODUCTOPSSHEET_WRITE_KPI_CONTRIBUTIONS)]]
            })

        # Write updated_at (always)
        if "updated_at" in col_map:
            col_idx = col_map["updated_at"]
            cell_range = _cell_range_for_update(tab_name, col_idx, row_idx)
            batch_updates.append({
                "range": cell_range,
                "values": [[ts]]
            })

        updated_initiatives.add(key)

    # Step 6: Execute batch updates in safe chunks
    if batch_updates:
        try:
            for i in range(0, len(batch_updates), _BATCH_UPDATE_CHUNK_SIZE):
                chunk = batch_updates[i : i + _BATCH_UPDATE_CHUNK_SIZE]
                client.batch_update_values(spreadsheet_id, chunk)
            logger.info(
                "kpi_contributions_writer.done",
                extra={
                    "updated_initiatives": len(updated_initiatives),
                    "total_cells_updated": len(batch_updates),
                    "existing_rows": len(row_index_by_key),
                    "appended_rows": next_append_row - len(existing_keys_raw) - 2,
                },
            )
        except Exception:
            logger.exception(
                "kpi_contributions_writer.batch_update_failed",
                extra={"num_updates": len(batch_updates)},
            )
            raise
    else:
        logger.info(
            "kpi_contributions_writer.no_updates",
            extra={"total_initiatives": len(initiatives_list)},
        )

    return len(updated_initiatives)


def _cell_range_for_update(tab_name: str, col_idx: int, row_idx: int) -> str:
    """Build A1 notation cell range for a single cell update.

    Args:
        tab_name: Sheet tab name
        col_idx: Column index (0-based)
        row_idx: Row index (1-based, where 1 = header)

    Returns:
        A1 notation range like "KPI_Contributions!C2:C2"
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
    "write_kpi_contributions_to_sheet",
]
