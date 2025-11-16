from __future__ import annotations

from typing import Optional

from app.config import settings
from app.sheets.client import get_sheets_service


def _column_index_to_a1(idx: int) -> str:
    # 1-based index -> A, B, ..., Z, AA, AB, ...
    result = ""
    while idx:
        idx, remainder = divmod(idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


class GoogleSheetsIntakeWriter:
    """
    Concrete writer that writes the initiative_key back to the intake sheet.

    Finds the column by matching header == settings.INTAKE_KEY_HEADER_NAME on header row.
    """

    def __init__(self, service=None):
        self.service = service or get_sheets_service()

    def _find_key_column_index(self, sheet_id: str, tab_name: str) -> Optional[int]:
        header_row = settings.INTAKE_HEADER_ROW_INDEX
        range_a1 = f"{tab_name}!{header_row}:{header_row}"
        resp = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=range_a1, valueRenderOption="UNFORMATTED_VALUE")
            .execute()
        )
        values = resp.get("values", [[]])
        headers = values[0] if values else []
        target = (settings.INTAKE_KEY_HEADER_NAME or "").strip().lower()
        for i, h in enumerate(headers, start=1):  # 1-based column index
            if isinstance(h, str) and h.strip().lower() == target:
                return i
        return None

    def write_initiative_key(self, sheet_id: str, tab_name: str, row_number: int, initiative_key: str) -> None:
        col_idx = self._find_key_column_index(sheet_id, tab_name)
        if not col_idx:
            # No matching header; nothing to do
            return
        col_a1 = _column_index_to_a1(col_idx)
        cell_a1 = f"{tab_name}!{col_a1}{row_number}"
        body = {"values": [[initiative_key]]}
        (
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=sheet_id,
                range=cell_a1,
                valueInputOption="RAW",
                body=body,
            )
            .execute()
        )