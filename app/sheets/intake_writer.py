# projectroadmap_sheet_project/app/sheets/intake_writer.py

from __future__ import annotations

from typing import Optional

from app.config import settings
from app.sheets.client import SheetsClient
from app.utils.header_utils import normalize_header


def _col_index_to_a1(idx: int) -> str:
    if idx <= 0:
        return "A"
    s = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


class GoogleSheetsIntakeWriter:
    """Concrete writer for writing initiative_key back to intake sheet.

    Finds the column by matching the header (case-insensitive) on the configured header row.
    """

    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def _find_key_column_index(self, sheet_id: str, tab_name: str) -> Optional[int]:
        """Find the column index (1-based) for the initiative key header."""
        header_row = getattr(settings, "INTAKE_HEADER_ROW_INDEX", 1) or 1
        range_a1 = f"{tab_name}!{header_row}:{header_row}"
        values = self.client.get_values(sheet_id, range_a1)
        headers = values[0] if values else []
        target = normalize_header(getattr(settings, "INTAKE_KEY_HEADER_NAME", "Initiative Key") or "")
        # allow aliases (normalized)
        alias_set = {normalize_header(h) for h in (getattr(settings, "INTAKE_KEY_HEADER_ALIASES", []) or [])}
        for i, h in enumerate(headers, start=1):
            if h is None:
                continue
            name = normalize_header(str(h))
            if name == target or name in alias_set:
                return i
        return None

    def write_initiative_key(self, sheet_id: str, tab_name: str, row_number: int, initiative_key: str) -> None:
        """Write the initiative_key to the specified row in the intake sheet."""
        col_idx = self._find_key_column_index(sheet_id, tab_name)
        if not col_idx:
            return
        col_a1 = _col_index_to_a1(col_idx)
        cell_a1 = f"{tab_name}!{col_a1}{row_number}"
        self.client.update_values(
            spreadsheet_id=sheet_id,
            range_=cell_a1,
            values=[[initiative_key]],
            value_input_option="RAW",
        )
