# productroadmap_sheet_project/app/sheets/backlog_writer.py

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.sheets.client import SheetsClient
from app.sheets.models import CENTRAL_EDITABLE_FIELDS
from app.sheets.models import CENTRAL_BACKLOG_HEADER, CENTRAL_HEADER_TO_FIELD


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


def initiative_to_backlog_row(initiative: Initiative) -> List[Any]:
    """Convert an Initiative ORM object to a row matching CENTRAL_BACKLOG_HEADER order."""
    deps_inits = _list_join(getattr(initiative, "dependencies_initiatives", None))

    return [
        _to_sheet_value(getattr(initiative, "initiative_key", None)),
        _to_sheet_value(getattr(initiative, "title", None)),
        _to_sheet_value(getattr(initiative, "requesting_team", None)),
        _to_sheet_value(getattr(initiative, "requester_name", None)),
        _to_sheet_value(getattr(initiative, "requester_email", None)),
        _to_sheet_value(getattr(initiative, "country", None)),
        _to_sheet_value(getattr(initiative, "product_area", None)),
        _to_sheet_value(getattr(initiative, "status", None)),
        _to_sheet_value(getattr(initiative, "strategic_theme", None)),
        _to_sheet_value(getattr(initiative, "customer_segment", None)),
        _to_sheet_value(getattr(initiative, "initiative_type", None)),
        _to_sheet_value(getattr(initiative, "hypothesis", None)),
        _to_sheet_value(getattr(initiative, "problem_statement", None)),
        _to_sheet_value(getattr(initiative, "value_score", None)),
        _to_sheet_value(getattr(initiative, "effort_score", None)),
        _to_sheet_value(getattr(initiative, "overall_score", None)),
        _to_sheet_value(getattr(initiative, "active_scoring_framework", None)),
        _to_sheet_value(getattr(initiative, "use_math_model", None)),
        deps_inits,
        _to_sheet_value(getattr(initiative, "dependencies_others", None)),
        _to_sheet_value(getattr(initiative, "llm_summary", None)),
        _to_sheet_value(getattr(initiative, "llm_notes", None)),
        _to_sheet_value(getattr(initiative, "strategic_priority_coefficient", None)),
        _to_sheet_value(getattr(initiative, "updated_at", None)),
        _to_sheet_value(getattr(initiative, "updated_source", None)),
    ]


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
    """Regenerate the central backlog sheet from Initiatives in the DB.

    Notes (best practice):
    - One-shot overwrite using a single update_values call for performance.
    - Start at A1; Sheets will expand as needed.
    - For very large datasets, consider paging or batchUpdate with Clear request first.
    """
    initiatives: List[Initiative] = (
        db.query(Initiative).order_by(getattr(Initiative, "id")).all()
    )

    values: List[List[Any]] = [CENTRAL_BACKLOG_HEADER]
    for ini in initiatives:
        values.append(initiative_to_backlog_row(ini))

    # Build explicit A1 end range from header width and number of rows
    col_count = len(CENTRAL_BACKLOG_HEADER)
    row_count = 1 + len(initiatives)
    end_col = _col_index_to_a1(col_count)
    end_a1 = f"{end_col}{row_count if row_count > 0 else 1}"

    # Optional: read grid size (not strictly required for write) — available for validation/metrics
    # grid_rows, grid_cols = client.get_sheet_grid_size(backlog_spreadsheet_id, backlog_tab_name)

    # Write starting at A1; overwrite content in that block
    client.update_values(
        spreadsheet_id=backlog_spreadsheet_id,
        range_=f"{backlog_tab_name}!A1:{end_a1}",
        values=values,
        value_input_option="USER_ENTERED",
    )

    # Configure protected ranges (warning-only) to prevent edits on non-product-owned columns
    _apply_backlog_protected_ranges(
        client=client,
        spreadsheet_id=backlog_spreadsheet_id,
        tab_name=backlog_tab_name,
        header=CENTRAL_BACKLOG_HEADER,
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

    non_product_cols = []
    for idx, col_name in enumerate(header):
        field = CENTRAL_HEADER_TO_FIELD.get(col_name)
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


