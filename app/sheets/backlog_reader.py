from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.sheets.client import SheetsClient
from app.config import settings
from app.utils.header_utils import get_value_by_header_alias

BacklogRow = Dict[str, Any]


class BacklogReader:
    """
    Reads the central backlog sheet and returns rows as (row_number, dict) pairs.

    Assumptions:
    - header_row contains column names (default 1)
    - start_data_row is the first data row (default 2)
    - Uses dynamic grid size to avoid truncation
    - Returns evaluated values (not formulas)
    """

    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def get_rows(
        self,
        spreadsheet_id: str,
        tab_name: str = "Backlog",
        header_row: int = 1,
        start_data_row: int = 2,
        max_rows: int | None = None,
    ) -> List[Tuple[int, BacklogRow]]:
        # Determine grid size to compute a precise A1 range
        total_rows, total_cols = self.client.get_sheet_grid_size(spreadsheet_id, tab_name)
        if total_rows <= 0 or total_cols <= 0:
            return []

        last_row = total_rows if max_rows is None else min(total_rows, header_row + max_rows)
        last_col_a1 = _col_index_to_a1(total_cols)
        a1_range = f"{tab_name}!A{header_row}:{last_col_a1}{last_row}"

        raw_values = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=a1_range,
            value_render_option="UNFORMATTED_VALUE",
        )
        if not raw_values:
            return []

        header = raw_values[0]
        data_rows = raw_values[1:]

        rows: List[Tuple[int, BacklogRow]] = []
        row_number = start_data_row

        for row_cells in data_rows:
            if self._is_empty_row(row_cells):
                row_number += 1
                continue
            row_dict = self._row_to_dict(header, row_cells)
            init_key = self._extract_initiative_key(row_dict)
            if not init_key:
                row_number += 1
                continue
            rows.append((row_number, row_dict))
            row_number += 1

        return rows

    def _row_to_dict(self, header: List[Any], row_cells: List[Any]) -> BacklogRow:
        row_dict: BacklogRow = {}
        for idx, col_name in enumerate(header):
            key = str(col_name).strip() if col_name is not None else ""
            if not key:
                continue
            value = row_cells[idx] if idx < len(row_cells) else ""
            row_dict[key] = value
        return row_dict

    @staticmethod
    def _is_empty_row(row_cells: List[Any]) -> bool:
        return all(cell in (None, "") for cell in row_cells)

    @staticmethod
    def _extract_initiative_key(row: BacklogRow) -> str:
        val = get_value_by_header_alias(
            row,
            getattr(settings, "INTAKE_KEY_HEADER_NAME", "Initiative Key"),
            getattr(settings, "INTAKE_KEY_HEADER_ALIASES", []),
        )
        return (str(val).strip() if val else "")


def _col_index_to_a1(idx: int) -> str:
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result
