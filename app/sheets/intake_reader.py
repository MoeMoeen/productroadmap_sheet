from __future__ import annotations
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from app.sheets.client import SheetsClient

# Central place for the intake row shape (a single logical row dict)
IntakeRow = Dict[str, Any]
# Pair of (row_number, row_dict)
IntakeRowPair = Tuple[int, IntakeRow]


class IntakeReader:
    """Reads department intake sheets and returns rows as (row_number, dict) pairs.

    Assumptions:
    - Header row contains column names (default row 1)
    - Data rows start at row 2 by default
    - We want evaluated values (valueRenderOption="UNFORMATTED_VALUE")
    """

    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def get_rows_for_sheet(
        self,
        spreadsheet_id: str,
        tab_name: str,
        header_row: int = 1,
        start_data_row: int = 4,  # Row 1=header, 2-3=metadata, data starts at 4
        max_rows: int | None = None,
    ) -> List[IntakeRowPair]:
        """Read intake rows for a given sheet/tab as (row_number, row_dict)."""

        # Determine grid size to build a precise A1 range
        grid_rows, grid_cols = self.client.get_sheet_grid_size(spreadsheet_id, tab_name)
        # limit rows to grid unless max_rows explicitly provided
        last_row = grid_rows if max_rows is None else min(grid_rows, header_row + max_rows)
        end_col_letter = _col_index_to_a1(grid_cols)
        range_ = f"{tab_name}!A{header_row}:{end_col_letter}{last_row}"

        raw_values = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=range_,
            value_render_option="UNFORMATTED_VALUE",
        )

        if not raw_values:
            return []

        header = raw_values[0]
        # Skip rows 2-3 (metadata), start data from row 4+ to prevent row number misalignment
        # when empty rows exist between metadata and data
        data_rows = raw_values[3:] if len(raw_values) > 3 else []

        rows: List[IntakeRowPair] = []
        current_row_number = start_data_row

        for row_cells in data_rows:
            if self._is_empty_row(row_cells):
                current_row_number += 1
                continue
            row_dict = self._row_to_dict(header, row_cells)
            rows.append((current_row_number, row_dict))
            current_row_number += 1

        return rows

    def _row_to_dict(self, header: List[Any], row_cells: List[Any]) -> IntakeRow:
        """Map a list of cell values into a dict based on header names.

        Extra header cells beyond the row are ignored; missing cells become "".
        Blank header columns are ignored.
        """
        row_dict: IntakeRow = {}
        for idx, col_name in enumerate(header):
            key = str(col_name).strip()
            if not key:
                continue
            value = row_cells[idx] if idx < len(row_cells) else ""
            row_dict[key] = value
        return row_dict

    def _is_empty_row(self, row_cells: Iterable[Any]) -> bool:
        """A row is empty if all cells are None or empty string."""
        for cell in row_cells:
            if cell not in (None, ""):
                return False
        return True


def _col_index_to_a1(idx: int) -> str:
    """Convert 1-based column index to A1 letter(s)."""
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result
