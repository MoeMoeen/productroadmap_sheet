# productroadmap_sheet_project/app/sheets/backlog_writer.py

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import logging
import json

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.sheets.client import SheetsClient
from app.sheets.layout import data_start_row
from app.sheets.models import CENTRAL_EDITABLE_FIELDS
from app.sheets.models import CENTRAL_BACKLOG_HEADER, CENTRAL_HEADER_TO_FIELD
from app.utils.provenance import Provenance, token
from app.utils.header_utils import normalize_header

logger = logging.getLogger(__name__)


def _to_sheet_value(value: Any):
    """Normalize Python values into something Sheets API can accept.

    - datetime/date -> ISO string
    - None -> ""
    - everything else -> as-is
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None:
        return ""
    return value


def _list_join(values: Any) -> str:
    """Render list-like values as comma-separated string for Sheets."""
    if not values:
        return ""
    if isinstance(values, (list, tuple)):
        return ", ".join(str(v) for v in values if v is not None and str(v) != "")
    return str(values)


def _initiative_field_value(field: str, initiative: Initiative, now_ts: datetime) -> Any:
    if field == "updated_at":
        return now_ts
    if field == "updated_source":
        return token(Provenance.FLOW1_BACKLOGSHEET_WRITE)
    if field == "intake_source":
        source_sheet_key = str(getattr(initiative, "source_sheet_key", "") or "").strip()
        source_tab_name = str(getattr(initiative, "source_tab_name", "") or "").strip()
        if source_sheet_key and source_tab_name:
            return f"{source_sheet_key} / {source_tab_name}"
        if source_sheet_key:
            return source_sheet_key
        if source_tab_name:
            return source_tab_name
        return ""

    # Special case: metric_chain_json lives on InitiativeMathModel, not Initiative
    # Fetch from primary math model (is_primary=True)
    if field == "metric_chain_json":
        primary_models = [m for m in initiative.math_models if m.is_primary]
        if primary_models:
            value = primary_models[0].metric_chain_json
            if value is not None:
                try:
                    return json.dumps(value)
                except Exception:
                    return str(value)
        return ""

    value = getattr(initiative, field, None)
    if field == "dependencies_initiatives":
        return _list_join(value)
    if isinstance(value, list):
        return _list_join(value)
    return value


def initiative_cell_values(
    header: List[str],
    initiative: Initiative,
    sheet_to_canonical: Dict[str, str],
    now_ts: datetime,
) -> Dict[str, Any]:
    """Map header names (owned columns) to outgoing sheet values for this initiative.

    Uses sheet_to_canonical to resolve aliases to canonical headers before looking up DB fields.
    Unknown columns are intentionally excluded.
    """
    values: Dict[str, Any] = {}
    for col in header:
        canon = sheet_to_canonical.get(col)
        if not canon:
            continue
        field = CENTRAL_HEADER_TO_FIELD.get(canon)
        if not field:
            continue
        values[col] = _to_sheet_value(_initiative_field_value(field, initiative, now_ts))
    return values


def _col_index_to_a1(idx: int) -> str:
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def write_backlog_from_db(
    db: Session,
    client: SheetsClient,
    backlog_spreadsheet_id: str,
    backlog_tab_name: str = "Backlog",
    include_archived: bool = False,
) -> dict[str, int]:
    """Rewrite backend-owned backlog columns from current DB initiatives.

    Strategy:
    1. Read header row to preserve column structure
    2. Clear only backend-owned data columns below the header/metadata rows
    3. Write all DB initiatives starting at data_start_row
    
    This removes stale system-managed values without wiping PM-added helper or formula
    columns that are not part of the canonical backlog schema.
    
    Returns:
        Dict with counts: {initiatives_written, cells_updated, archived_rows_excluded}
    """
    total_initiatives_query = db.query(Initiative)
    initiatives_query = db.query(Initiative)
    if not include_archived:
        initiatives_query = initiatives_query.filter(Initiative.is_archived.is_(False))

    initiatives: List[Initiative] = initiatives_query.order_by(getattr(Initiative, "id")).all()
    archived_rows_excluded = max(total_initiatives_query.count() - len(initiatives), 0) if not include_archived else 0

    # 1) Read header row
    header_values = client.get_values(
        spreadsheet_id=backlog_spreadsheet_id,
        range_=f"{backlog_tab_name}!1:1",
        value_render_option="UNFORMATTED_VALUE",
    )
    header: List[str] = header_values[0] if header_values else CENTRAL_BACKLOG_HEADER

    # Build sheet->canonical mapping for owned columns (alias-aware)
    norm_to_header = {normalize_header(k): k for k in CENTRAL_HEADER_TO_FIELD.keys()}
    col_idx_map = {header[i]: i for i in range(len(header))}
    
    owned_sheet_to_canonical: Dict[str, str] = {}
    for col in header:
        canon = norm_to_header.get(normalize_header(str(col)))
        if canon:
            owned_sheet_to_canonical[col] = canon

    # 2) Clear only backend-owned columns so PM-added helper/formula columns survive.
    _dsr = data_start_row(backlog_tab_name)
    grid_rows, grid_cols = client.get_sheet_grid_size(backlog_spreadsheet_id, backlog_tab_name)
    owned_headers = [col for col in header if col in owned_sheet_to_canonical]
    if grid_rows >= _dsr:
        clear_ranges: List[str] = []
        for col in owned_headers:
            col_idx = col_idx_map.get(col)
            if col_idx is None:
                continue
            col_a1 = _col_index_to_a1(col_idx + 1)
            clear_ranges.append(f"{backlog_tab_name}!{col_a1}{_dsr}:{col_a1}{grid_rows}")

        for clear_range in clear_ranges:
            client.clear_values(backlog_spreadsheet_id, clear_range)

        logger.info(
            "backlog.clearing_owned_columns",
            extra={"column_count": len(clear_ranges), "grid_rows": grid_rows},
        )

    # 3) Build rows for all initiatives
    now_ts = datetime.now(timezone.utc)
    
    batch_data: List[Dict[str, Any]] = []
    
    for row_offset, ini in enumerate(initiatives):
        target_row = _dsr + row_offset
        values_by_header = initiative_cell_values(owned_headers, ini, owned_sheet_to_canonical, now_ts)
        
        # Write each owned column for this initiative
        for col, value in values_by_header.items():
            col_idx = col_idx_map.get(col)
            if col_idx is None:
                continue
            col_a1 = _col_index_to_a1(col_idx + 1)
            cell_range = f"{backlog_tab_name}!{col_a1}{target_row}"
            batch_data.append({"range": cell_range, "values": [[value]]})

    cells_updated = 0
    if batch_data:
        # Chunk to avoid API range count limits
        CHUNK_SIZE = 200
        for i in range(0, len(batch_data), CHUNK_SIZE):
            chunk = batch_data[i : i + CHUNK_SIZE]
            client.batch_update_values(
                spreadsheet_id=backlog_spreadsheet_id,
                data=chunk,
                value_input_option="USER_ENTERED",
            )
            cells_updated += len(chunk)

    logger.info(
        "backlog.write_complete",
        extra={
            "initiatives": len(initiatives),
            "cells": cells_updated,
            "archived_excluded_count": archived_rows_excluded,
        },
    )

    # Configure protected ranges using the actual sheet header
    _apply_backlog_protected_ranges(
        client=client,
        spreadsheet_id=backlog_spreadsheet_id,
        tab_name=backlog_tab_name,
        header=header,
    )
    
    return {
        "initiatives_written": len(initiatives),
        "cells_updated": cells_updated,
        "archived_rows_excluded": archived_rows_excluded,
    }


def _apply_backlog_protected_ranges(
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str,
    header: List[str],
) -> None:
    """Protect all columns that are NOT in CENTRAL_EDITABLE_FIELDS (warning-only).

    More robust parsing of sheet properties to avoid KeyError when the client
    returns a simplified structure.
    """
    props = client.get_sheet_properties(spreadsheet_id, tab_name)
    if not props:
        return

    # Try multiple shapes
    sheet_id: Optional[int] = None
    sheet_props = None

    # Shape A: {"properties": {"sheetId": X, ...}}
    if isinstance(props, dict) and "properties" in props and isinstance(props["properties"], dict):
        sheet_props = props["properties"]
        sheet_id = sheet_props.get("sheetId")

    # Shape B: {"sheetId": X, "title": "..."}
    if sheet_id is None and "sheetId" in props:
        sheet_id = props.get("sheetId")
        sheet_props = props  # may also carry protectedRanges

    # Shape C: {"sheets": [{ "properties": {...}, ...}, ...]}
    if sheet_id is None and "sheets" in props:
        for s in props["sheets"]:
            p = s.get("properties", {})
            if p.get("title") == tab_name:
                sheet_id = p.get("sheetId")
                sheet_props = s  # full sheet entry
                break

    if sheet_id is None:
        # Cannot proceed safely
        return

    existing = []
    # protectedRanges may be at top level or inside sheet entry
    if isinstance(sheet_props, dict):
        existing = sheet_props.get("protectedRanges", []) or []
    if not existing and isinstance(props, dict):
        existing = props.get("protectedRanges", []) or []

    # Delete previously auto-added warning ranges
    to_delete_ids = [
        pr.get("protectedRangeId")
        for pr in existing
        if isinstance(pr, dict) and pr.get("description", "").startswith("AUTO_PROTECT_NON_PRODUCT")
    ]
    delete_requests = [
        {"deleteProtectedRange": {"protectedRangeId": rid}}
        for rid in to_delete_ids
        if rid is not None
    ]

    # Use alias-aware mapping for protection as well
    norm_to_field = {normalize_header(k): v for k, v in CENTRAL_HEADER_TO_FIELD.items()}
    non_product_cols = []
    for idx, col_name in enumerate(header):
        field = norm_to_field.get(normalize_header(str(col_name)))
        if field not in CENTRAL_EDITABLE_FIELDS:
            non_product_cols.append(idx)

    add_requests = []
    for col_idx in non_product_cols:
        add_requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,          # leave header row editable
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "description": f"AUTO_PROTECT_NON_PRODUCT_{col_idx}",
                        "warningOnly": True,
                    }
                }
            }
        )

    batch_requests = delete_requests + add_requests
    if batch_requests:
        client.batch_update(spreadsheet_id, batch_requests)


