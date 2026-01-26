# productroadmap_sheet_project/app/sheets/backlog_writer.py

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import logging
import json

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.sheets.client import SheetsClient
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

    value = getattr(initiative, field, None)
    if field == "dependencies_initiatives":
        return _list_join(value)
    if field == "metric_chain_json" and value is not None:
        try:
            return json.dumps(value)
        except Exception:
            return str(value)
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
) -> None:
    """Upsert initiatives into the backlog sheet without overwriting unknown columns.

    Strategy: read header + existing rows, map initiative_key → row number, then perform
    targeted cell writes only for columns we own. New initiatives append at the end.
    """
    initiatives: List[Initiative] = (
        db.query(Initiative).order_by(getattr(Initiative, "id")).all()
    )

    # 1) Read header row
    header_values = client.get_values(
        spreadsheet_id=backlog_spreadsheet_id,
        range_=f"{backlog_tab_name}!1:1",
        value_render_option="UNFORMATTED_VALUE",
    )
    header: List[str] = header_values[0] if header_values else CENTRAL_BACKLOG_HEADER

    # Build lookup for initiative_key column(s) using normalized header matching
    norm_header = [normalize_header(str(h)) for h in header]
    norm_to_header = {normalize_header(k): k for k in CENTRAL_HEADER_TO_FIELD.keys()}
    col_idx_map = {header[i]: i for i in range(len(header))}
    initiative_header_candidates = [h for h, field in CENTRAL_HEADER_TO_FIELD.items() if field == "initiative_key"]
    norm_initiative_candidates = {normalize_header(h) for h in initiative_header_candidates}
    init_key_indices = [idx for idx, h in enumerate(header) if normalize_header(str(h)) in norm_initiative_candidates]
    if not init_key_indices:
        logger.error("backlog.no_initiative_key_column", extra={"header": header})
        raise RuntimeError("Backlog write failed: no initiative key column found in sheet header")

    # Build sheet->canonical mapping for owned columns (alias-aware)
    owned_sheet_to_canonical: Dict[str, str] = {}
    for col in header:
        canon = norm_to_header.get(normalize_header(str(col)))
        if canon:
            owned_sheet_to_canonical[col] = canon

    # 2) Read existing initiative_key column only to map initiative_key -> row number, with blank-run cutoff
    init_col_idx = init_key_indices[0]  # prefer first match
    init_col_a1 = _col_index_to_a1(init_col_idx + 1)
    grid_rows, _ = client.get_sheet_grid_size(backlog_spreadsheet_id, backlog_tab_name)
    end_row = grid_rows if grid_rows > 0 else 1
    key_col_values = client.get_values(
        spreadsheet_id=backlog_spreadsheet_id,
        range_=f"{backlog_tab_name}!{init_col_a1}4:{init_col_a1}{end_row}",  # Row 1=header, 2-3=metadata, data starts at 4
        value_render_option="UNFORMATTED_VALUE",
    ) or []

    init_key_to_rownum: Dict[str, int] = {}
    blank_run = 0
    BLANK_STOP_THRESHOLD = 50
    for offset, row_cells in enumerate(key_col_values, start=4):  # Row 1=header, 2-3=metadata, data starts at 4
        cell_val = row_cells[0] if row_cells else None
        if cell_val is None or cell_val == "":
            blank_run += 1
            if blank_run >= BLANK_STOP_THRESHOLD:
                break
            continue
        blank_run = 0
        key = str(cell_val).strip()
        if not key:
            continue
        if key in init_key_to_rownum:
            logger.warning("backlog.duplicate_initiative_key_in_sheet", extra={"initiative_key": key, "row": offset})
            continue
        init_key_to_rownum[key] = offset

    next_append_row = max(init_key_to_rownum.values(), default=3) + 1  # Default to row 4 if no data (1=header, 2-3=metadata)

    # 3) Build batch updates grouped by column to reduce request count
    owned_headers = [col for col in header if col in owned_sheet_to_canonical]

    updates_by_col: Dict[str, Dict[int, Any]] = {col: {} for col in owned_headers}

    now_ts = datetime.now(timezone.utc)

    for ini in initiatives:
        target_row = init_key_to_rownum.get(str(ini.initiative_key))
        if not target_row:
            target_row = next_append_row
            next_append_row += 1
            init_key_to_rownum[str(ini.initiative_key)] = target_row
        values_by_header = initiative_cell_values(owned_headers, ini, owned_sheet_to_canonical, now_ts)
        for col, value in values_by_header.items():
            updates_by_col[col][target_row] = value

    batch_data: List[Dict[str, Any]] = []
    for col, row_values in updates_by_col.items():
        if not row_values:
            continue
        col_idx = col_idx_map.get(col)
        if col_idx is None:
            continue
        col_a1 = _col_index_to_a1(col_idx + 1)
        # group consecutive rows to minimize ranges
        sorted_rows = sorted(row_values.keys())
        start = prev = sorted_rows[0]
        group_vals: List[Any] = [row_values[start]]
        for r in sorted_rows[1:]:
            if r == prev + 1:
                group_vals.append(row_values[r])
            else:
                range_a1 = f"{backlog_tab_name}!{col_a1}{start}:{col_a1}{prev}"
                batch_data.append({"range": range_a1, "values": [[v] for v in group_vals]})
                start = r
                group_vals = [row_values[r]]
            prev = r
        range_a1 = f"{backlog_tab_name}!{col_a1}{start}:{col_a1}{prev}"
        batch_data.append({"range": range_a1, "values": [[v] for v in group_vals]})

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

    # Configure protected ranges using the actual sheet header
    _apply_backlog_protected_ranges(
        client=client,
        spreadsheet_id=backlog_spreadsheet_id,
        tab_name=backlog_tab_name,
        header=header,
    )


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


