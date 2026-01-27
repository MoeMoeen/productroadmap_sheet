#productroadmap_sheet_project/app/sheets/kpi_contributions_reader.py
"""KPI_Contributions sheet reader for ProductOps sheet."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.sheets.client import SheetsClient
from app.sheets.models import KPIContributionRow, KPI_CONTRIBUTIONS_HEADER_MAP
from app.utils.header_utils import normalize_header

logger = logging.getLogger("app.sheets.kpi_contributions_reader")


def _blank_to_none(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


ContribRowPair = Tuple[int, KPIContributionRow]


class KPIContributionsReader:
    """Reads KPI_Contributions tab from ProductOps sheet."""

    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def get_rows_for_sheet(
        self,
        spreadsheet_id: str,
        tab_name: str,
        header_row: int = 1,
        start_data_row: int = 4,  # Row 1=header, 2-3=metadata, data starts at 4
        max_rows: Optional[int] = None,
    ) -> List[ContribRowPair]:
        header_range = f"{tab_name}!{header_row}:{header_row}"
        header_values = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=header_range,
            value_render_option="UNFORMATTED_VALUE",
        )

        if not header_values or not header_values[0]:
            logger.info("kpi_contrib_reader.empty_header", extra={"tab": tab_name})
            return []

        header = header_values[0]
        end_col_letter = _col_index_to_a1(len(header))

        # Read from row 1 and skip rows 2-3 to prevent empty row misalignment
        # (If we start from A4, Google Sheets skips empty rows causing row number drift)
        data_range = f"{tab_name}!A1:{end_col_letter}"
        all_values = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=data_range,
            value_render_option="UNFORMATTED_VALUE",
        ) or []
        
        # Skip header (row 1) and metadata (rows 2-3), keep rows 4+
        data_values = all_values[3:] if len(all_values) > 3 else []

        if max_rows is not None:
            data_values = data_values[:max_rows]

        rows: List[ContribRowPair] = []
        current_row_number = start_data_row

        for row_cells in data_values:
            if self._is_empty_row(row_cells):
                current_row_number += 1
                continue

            row_dict = self._row_to_dict(header, row_cells)
            key = row_dict.get("initiative_key")
            if not (isinstance(key, str) and key.strip()):
                logger.warning(
                    "kpi_contrib_reader.skip_missing_key",
                    extra={"row": current_row_number},
                )
                current_row_number += 1
                continue

            try:
                contrib_row = KPIContributionRow(**row_dict)
                rows.append((current_row_number, contrib_row))
            except Exception as e:
                logger.warning(
                    "kpi_contrib_reader.parse_error",
                    extra={"row": current_row_number, "error": str(e)[:200]},
                )

            current_row_number += 1

        logger.info(
            "kpi_contrib_reader.complete",
            extra={"tab": tab_name, "rows_read": len(rows), "total_scanned": len(data_values)},
        )
        return rows

    def _row_to_dict(self, header: List[Any], row_cells: List[Any]) -> Dict[str, Any]:
        # Precompute alias lookup once per row to avoid nested scans (O(cols))
        alias_lookup: Dict[str, str] = {}
        for canonical_field, aliases in KPI_CONTRIBUTIONS_HEADER_MAP.items():
            for alias in aliases:
                alias_lookup[normalize_header(alias)] = canonical_field

        row_dict: Dict[str, Any] = {}
        for idx, col_name in enumerate(header):
            key = str(col_name).strip()
            if not key:
                continue

            normalized_key = normalize_header(key)
            value = row_cells[idx] if idx < len(row_cells) else ""

            canonical_field = alias_lookup.get(normalized_key)
            if not canonical_field:
                continue

            if canonical_field == "kpi_contribution_json":
                row_dict[canonical_field] = self._parse_contribution(value)
            else:
                row_dict[canonical_field] = _blank_to_none(value)

        return row_dict

    def _parse_contribution(self, value: Any) -> Any:
        v = _blank_to_none(value)
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                loaded = json.loads(v)
                return loaded
            except Exception:
                logger.warning("kpi_contrib_reader.json_parse_failed", extra={"value": str(v)[:120]})
                return v
        return v

    def _is_empty_row(self, row_cells: Iterable[Any]) -> bool:
        for cell in row_cells:
            if cell not in (None, ""):
                return False
        return True


def _col_index_to_a1(idx: int) -> str:
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result
