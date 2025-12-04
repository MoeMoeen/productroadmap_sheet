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

logger = logging.getLogger(__name__)

# Score output columns (write-back phase)
# These are the columns that Flow 3.C.2 populates with computed scores
PRODUCTOPS_SCORE_OUTPUT_COLUMNS: List[str] = [
    "rice_value_score",
    "rice_effort_score",
    "rice_overall_score",
    "wsjf_value_score",
    "wsjf_effort_score",
    "wsjf_overall_score",
]

# Map score field names to column header variations (for flexible header parsing)
# Handles both "rice_value_score" (direct) and "RICE: Value Score" (namespaced) formats
SCORE_FIELD_TO_HEADERS: Dict[str, List[str]] = {
    "rice_value_score": ["rice_value_score", "rice: value score"],
    "rice_effort_score": ["rice_effort_score", "rice: effort score"],
    "rice_overall_score": ["rice_overall_score", "rice: overall score"],
    "wsjf_value_score": ["wsjf_value_score", "wsjf: value score"],
    "wsjf_effort_score": ["wsjf_effort_score", "wsjf: effort score"],
    "wsjf_overall_score": ["wsjf_overall_score", "wsjf: overall score"],
}


def write_scores_to_productops_sheet(
    db: Session,
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str = "Scoring_Inputs",
) -> int:
    """Write per-framework scores from DB to Product Ops sheet using targeted cell updates.

    This is the output phase of Flow 3.C.2:
    - Reads per-framework scores from DB (rice_value_score, wsjf_overall_score, etc.)
    - Finds each initiative's row in the sheet by initiative_key
    - Updates ONLY the score columns (doesn't touch other columns)
    - Uses batchUpdate for efficiency (multiple updates in single API call)

    Args:
        db: Database session
        client: SheetsClient instance
        spreadsheet_id: Product Ops spreadsheet ID
        tab_name: Sheet tab name (default: "Scoring_Inputs")

    Returns:
        Number of initiatives with scores updated in sheet

    Side effects:
        - Updates Product Ops sheet cells for score columns
        - Logs progress and any missing initiatives
    """
    if not spreadsheet_id:
        raise ValueError("spreadsheet_id is required")

    # Step 1: Read sheet to get header row and find score column indices
    values = client.get_values(spreadsheet_id, tab_name)
    if not values or len(values) < 2:
        logger.warning("productops_writer.empty_sheet", extra={"tab": tab_name})
        return 0

    headers = values[0]
    norm_headers = [_normalize_header(h) for h in headers]

    # Step 2: Find which columns correspond to each score field + initiative_key
    col_map: Dict[str, int] = {}  # field_name -> column_index (0-based)
    for i, nh in enumerate(norm_headers):
        if nh == "initiative_key":
            col_map["initiative_key"] = i
        elif nh in PRODUCTOPS_SCORE_OUTPUT_COLUMNS:
            col_map[nh] = i

    if "initiative_key" not in col_map:
        logger.warning("productops_writer.no_key_column", extra={"tab": tab_name})
        return 0

    key_col = col_map["initiative_key"]

    # Step 3: Load all initiatives from DB into memory (keyed by initiative_key)
    initiatives_list = db.query(Initiative).all()
    initiatives: Dict[str, Any] = cast(Dict[str, Any], {i.initiative_key: i for i in initiatives_list})

    logger.debug(
        "productops_writer.loaded_initiatives",
        extra={"count": len(initiatives), "score_columns": len(col_map) - 1},
    )

    # Step 4: Build targeted cell updates using update_values for each cell
    # Google Sheets API: update_values(range, values) where range is A1 notation like "Sheet!M2:M2"
    updated_initiatives: set = set()

    for row_idx, row_data in enumerate(values[1:], start=2):  # Start at row 2 (row 1 = headers)
        # Extract initiative key from this row
        key = (
            (row_data[key_col] if key_col < len(row_data) else "").strip()
            if key_col < len(row_data)
            else ""
        )
        if not key:
            continue

        ini = initiatives.get(key)
        if not ini:
            logger.debug(
                "productops_writer.missing_initiative",
                extra={"initiative_key": key, "row": row_idx},
            )
            continue

        # For each score column, update if value exists
        for field, col_idx in col_map.items():
            if field == "initiative_key":
                continue

            # Get value from DB
            score_value = getattr(ini, field, None)
            if score_value is None:
                continue  # Don't update empty scores (leave blank)

            # Update this single cell
            cell_range = _cell_range_for_update(tab_name, col_idx, row_idx)
            try:
                client.update_values(spreadsheet_id, cell_range, [[score_value]])
                updated_initiatives.add(key)
            except Exception:
                logger.exception(
                    "productops_writer.cell_update_failed",
                    extra={"field": field, "row": row_idx, "range": cell_range},
                )

    logger.info(
        "productops_writer.done",
        extra={"updated_initiatives": len(updated_initiatives), "total_rows": len(values) - 1},
    )

    return len(updated_initiatives)


def _normalize_header(name: str) -> str:
    """Normalize sheet header to lowercase field name format.

    Handles both formats:
    - Direct: "rice_value_score" → "rice_value_score"
    - Namespaced: "RICE: Value Score" → "rice_value_score"

    Args:
        name: Raw header string from sheet

    Returns:
        Normalized lowercase field name
    """
    n = (name or "").strip().lower()

    # If it has a colon, it's namespaced format (e.g., "RICE: Value Score")
    if ":" in n:
        fw, param = [p.strip() for p in n.split(":", 1)]
        normalized = f"{fw}_{param.replace(' ', '_')}"
        return normalized

    # Otherwise, assume direct format (e.g., "rice_value_score")
    return n.replace(" ", "_")


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
    "PRODUCTOPS_SCORE_OUTPUT_COLUMNS",
    "SCORE_FIELD_TO_HEADERS",
]
