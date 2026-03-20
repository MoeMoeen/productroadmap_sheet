# productroadmap_sheet_project/app/sheets/instructions_writer.py
"""Writer for system-managed instruction rows on sheet tabs.

Render a merged, formatted instructions row using copy from the instructions registry.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.sheets.client import SheetsClient
from app.sheets.instructions_registry import TabInstructions
from app.sheets.layout import data_start_row


def _build_instruction_text(t: TabInstructions) -> str:
    parts: List[str] = []
    parts.append(f"\U0001F9ED {t.title} — What this tab is for")
    parts.extend([f"• {line}" for line in (t.lines or [])])

    if t.steps:
        parts.append("")
        parts.append("📋 Step-by-Step Walkthrough")
        for i, step in enumerate(t.steps, start=1):
            parts.append(f"{i}. {step}")

    if t.warnings:
        parts.append("")
        parts.append("⚠️ Notes")
        parts.extend([f"• {w}" for w in t.warnings])

    if t.actions:
        parts.append("")
        parts.append("✅ Useful actions (Roadmap AI menu)")
        parts.extend([f"• {a}" for a in t.actions])

    return "\n".join(parts).strip()


def _col_to_a1(col_idx_1_based: int) -> str:
    """Convert 1-based column index to A1 column letters."""
    letters = []
    n = max(1, col_idx_1_based)
    while n:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(ord("A") + rem))
    return "".join(reversed(letters))


def write_tab_instructions_row(
    *,
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str,
    instructions: TabInstructions,
    instruction_row: int = 4,
) -> None:
    """
    Writes a merged, wrapped instructions row to the given tab.

    - Writes to A{instruction_row} and merges across all columns in the sheet grid
    - Applies basic formatting (wrap, small font, background, vertical align)
    """
    # Guard against overwriting data when layout isn't configured
    if data_start_row(tab_name) <= instruction_row:
        raise ValueError(
            f"Instruction row {instruction_row} would overlap data for tab '{tab_name}'. "
            "Update TAB_LAYOUT/data_start_row first."
        )

    props = client.get_sheet_properties(spreadsheet_id, tab_name)
    sheet_id = None
    grid_cols = None
    frozen_cols = 0

    if isinstance(props, dict):
        # Shape A: { properties: { sheetId, gridProperties } }
        if isinstance(props.get("properties"), dict):
            sheet_id = props["properties"].get("sheetId")
            grid_props = props["properties"].get("gridProperties") or {}
            grid_cols = grid_props.get("columnCount")
            frozen_cols = grid_props.get("frozenColumnCount") or 0
        # Shape B: { sheetId, gridProperties }
        if sheet_id is None and props.get("sheetId") is not None:
            sheet_id = props.get("sheetId")
            grid_props = props.get("gridProperties") or {}
            grid_cols = grid_props.get("columnCount")
            frozen_cols = grid_props.get("frozenColumnCount") or 0
        # Shape C: { sheets: [ { properties: { title, sheetId, gridProperties } } ] }
        if sheet_id is None and isinstance(props.get("sheets"), list):
            for sh in props.get("sheets", []):
                if sh.get("properties", {}).get("title") == tab_name:
                    sheet_id = sh["properties"].get("sheetId")
                    grid_props = sh["properties"].get("gridProperties") or {}
                    grid_cols = grid_props.get("columnCount")
                    frozen_cols = grid_props.get("frozenColumnCount") or 0
                    break

    if sheet_id is None:
        raise ValueError(f"Cannot resolve sheetId for tab '{tab_name}'")

    if not isinstance(grid_cols, int) or grid_cols <= 0:
        header = client.get_values(spreadsheet_id, f"{tab_name}!1:1") or []
        grid_cols = max(1, len(header[0]) if header and header[0] else 1)

    text = _build_instruction_text(instructions)

    # If the sheet has frozen columns, avoid merging across the frozen boundary.
    start_col_idx = int(frozen_cols) if frozen_cols and frozen_cols > 0 else 0
    end_col_idx = grid_cols  # exclusive
    if end_col_idx is None:
        end_col_idx = start_col_idx + 1
    if end_col_idx <= start_col_idx:
        end_col_idx = start_col_idx + 1

    # Write value starting at the first non-frozen column (or A if none frozen)
    start_col_a1 = _col_to_a1(start_col_idx + 1)
    client.update_values(
        spreadsheet_id=spreadsheet_id,
        range_=f"{tab_name}!{start_col_a1}{instruction_row}",
        values=[[text]],
        value_input_option="RAW",
    )

    r0 = instruction_row - 1  # 0-based inclusive
    r1 = instruction_row      # 0-based exclusive

    requests: List[Dict[str, Any]] = [
        {
            "unmergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r0,
                    "endRowIndex": r1,
                    "startColumnIndex": start_col_idx,
                    "endColumnIndex": end_col_idx,
                }
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r0,
                    "endRowIndex": r1,
                    "startColumnIndex": start_col_idx,
                    "endColumnIndex": end_col_idx,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r0,
                    "endRowIndex": r1,
                    "startColumnIndex": start_col_idx,
                    "endColumnIndex": end_col_idx,
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {"fontSize": 10, "bold": False},
                        "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.98},
                    }
                },
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment,textFormat,backgroundColor)",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": r0,
                    "endIndex": r1,
                },
                "properties": {"pixelSize": 110},
                "fields": "pixelSize",
            }
        },
    ]

    client.batch_update(spreadsheet_id, requests)
