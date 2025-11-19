from __future__ import annotations

from typing import Any, List, Dict

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative  # type: ignore
from app.sheets.client import SheetsClient
from app.services.backlog_service import CENTRAL_EDITABLE_FIELDS


# Central Backlog header definition (keep single source of truth)
CENTRAL_BACKLOG_HEADER: List[str] = [
    "Initiative Key",
    "Title",
    "Requesting Team",
    "Requester Name",
    "Requester Email",
    "Country",
    "Product Area",
    "Status",
    "Strategic Theme",
    "Customer Segment",
    "Initiative Type",
    "Hypothesis",
    "Value Score",
    "Effort Score",
    "Overall Score",
    "Active Scoring Framework",
    "Use Math Model",
    "Dependencies Initiatives",
    "Dependencies Others",
    "LLM Summary",
    "LLM Notes",
    "Strategic Priority Coefficient",
    # Metadata (appended at the end)
    "Updated At",
    "Updated Source",
]

# Map header labels to Initiative field names for editability decisions
CENTRAL_HEADER_TO_FIELD: Dict[str, str] = {
    "Initiative Key": "initiative_key",
    "Title": "title",
    "Requesting Team": "requesting_team",
    "Requester Name": "requester_name",
    "Requester Email": "requester_email",
    "Country": "country",
    "Product Area": "product_area",
    "Status": "status",
    "Strategic Theme": "strategic_theme",
    "Customer Segment": "customer_segment",
    "Initiative Type": "initiative_type",
    "Hypothesis": "hypothesis",
    "Value Score": "value_score",
    "Effort Score": "effort_score",
    "Overall Score": "overall_score",
    "Active Scoring Framework": "active_scoring_framework",
    "Use Math Model": "use_math_model",
    "Dependencies Initiatives": "dependencies_initiatives",
    "Dependencies Others": "dependencies_others",
    "LLM Summary": "llm_summary",
    "LLM Notes": "llm_notes",
    "Strategic Priority Coefficient": "strategic_priority_coefficient",
    "Updated At": "updated_at",
    "Updated Source": "updated_source",
}


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
        getattr(initiative, "initiative_key", None),
        getattr(initiative, "title", None),
        getattr(initiative, "requesting_team", None),
        getattr(initiative, "requester_name", None),
        getattr(initiative, "requester_email", None),
        getattr(initiative, "country", None),
        getattr(initiative, "product_area", None),
        getattr(initiative, "status", None),
        getattr(initiative, "strategic_theme", None),
        getattr(initiative, "customer_segment", None),
        getattr(initiative, "initiative_type", None),
        getattr(initiative, "hypothesis", None),
        getattr(initiative, "value_score", None),
        getattr(initiative, "effort_score", None),
        getattr(initiative, "overall_score", None),
        getattr(initiative, "active_scoring_framework", None),
        getattr(initiative, "use_math_model", None),
        deps_inits,
        getattr(initiative, "dependencies_others", None),
        getattr(initiative, "llm_summary", None),
        getattr(initiative, "llm_notes", None),
        getattr(initiative, "strategic_priority_coefficient", None),
        # Metadata
        getattr(initiative, "updated_at", None),
        getattr(initiative, "updated_source", None),
    ]


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


def _col_index_to_a1(idx: int) -> str:
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def _apply_backlog_protected_ranges(
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str,
    header: List[str],
) -> None:
    """Protect all columns that are NOT in CENTRAL_EDITABLE_FIELDS (warning-only).

    We identify columns by header labels using CENTRAL_HEADER_TO_FIELD mapping.
    Columns without a known mapping are protected by default.
    """
    props = client.get_sheet_properties(spreadsheet_id, tab_name)
    sheet_id = props.get("sheetId")
    grid = props.get("gridProperties", {})
    row_count = int(grid.get("rowCount", 1000))
    if sheet_id is None:
        return

    # Determine which column indexes (0-based) to protect
    protected_col_indexes: List[int] = []
    for idx, label in enumerate(header):
        field = CENTRAL_HEADER_TO_FIELD.get(label)
        # If field not mapped or not editable centrally, protect it
        if not field or field not in CENTRAL_EDITABLE_FIELDS:
            protected_col_indexes.append(idx)

    # Clear existing auto-protected ranges created by this tool (optional best-effort)
    requests: List[dict] = []
    for pr in props.get("protectedRanges", []) or []:
        desc = pr.get("description", "") or ""
        if desc.startswith("AutoProtected (product backlog)"):
            requests.append({"deleteProtectedRange": {"protectedRangeId": pr.get("protectedRangeId")}})

    # Add new protected ranges
    for col_idx in protected_col_indexes:
        requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": row_count,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "description": f"AutoProtected (product backlog): protect column {header[col_idx]}",
                        # Use warningOnly to avoid permission issues while still warning editors
                        "warningOnly": True,
                    }
                }
            }
        )

    client.batch_update(spreadsheet_id, requests)
