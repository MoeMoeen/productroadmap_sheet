#productroadmap_sheet_project/app/sheets/metrics_config_reader.py
"""Metrics_Config sheet reader for ProductOps sheet."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.sheets.client import SheetsClient
from app.sheets.models import MetricsConfigRow, METRICS_CONFIG_HEADER_MAP
from app.utils.header_utils import normalize_header

logger = logging.getLogger("app.sheets.metrics_config_reader")


def _blank_to_none(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def _coerce_bool(v: Any) -> Optional[bool]:
    v = _blank_to_none(v)
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "y"):
        return True
    if s in ("false", "0", "no", "n"):
        return False
    return None


MetricRowPair = Tuple[int, MetricsConfigRow]


class MetricsConfigReader:
    """Reads Metrics_Config tab from ProductOps sheet."""

    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def get_rows_for_sheet(
        self,
        spreadsheet_id: str,
        tab_name: str,
        header_row: int = 1,
        start_data_row: int = 4,  # Row 1=header, 2-3=metadata, data starts at 4
        max_rows: Optional[int] = None,
    ) -> List[MetricRowPair]:
        """Read KPI rows as (row_number, MetricsConfigRow)."""
        header_range = f"{tab_name}!{header_row}:{header_row}"
        header_values = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=header_range,
            value_render_option="UNFORMATTED_VALUE",
        )

        if not header_values or not header_values[0]:
            logger.info("metrics_config_reader.empty_header", extra={"tab": tab_name})
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

        rows: List[MetricRowPair] = []
        current_row_number = start_data_row

        for row_cells in data_values:
            if self._is_empty_row(row_cells):
                current_row_number += 1
                continue

            row_dict = self._row_to_dict(header, row_cells)
            key = row_dict.get("kpi_key")
            if not (isinstance(key, str) and key.strip()):
                logger.warning(
                    "metrics_config_reader.skip_missing_key",
                    extra={"row": current_row_number},
                )
                current_row_number += 1
                continue

            try:
                metric_row = MetricsConfigRow(**row_dict)
                rows.append((current_row_number, metric_row))
            except Exception as e:
                logger.warning(
                    "metrics_config_reader.parse_error",
                    extra={"row": current_row_number, "error": str(e)[:200]},
                )

            current_row_number += 1

        logger.info(
            "metrics_config_reader.complete",
            extra={"tab": tab_name, "rows_read": len(rows), "total_scanned": len(data_values)},
        )
        return rows

    def _row_to_dict(self, header: List[Any], row_cells: List[Any]) -> Dict[str, Any]:
        row_dict: Dict[str, Any] = {}
        for idx, col_name in enumerate(header):
            key = str(col_name).strip()
            if not key:
                continue

            normalized_key = normalize_header(key)
            value = row_cells[idx] if idx < len(row_cells) else ""

            for canonical_field, aliases in METRICS_CONFIG_HEADER_MAP.items():
                if normalized_key in [normalize_header(a) for a in aliases]:
                    if canonical_field == "is_active":
                        row_dict[canonical_field] = _coerce_bool(value)
                    elif canonical_field == "kpi_level":
                        v = _blank_to_none(value)
                        row_dict[canonical_field] = str(v).strip().lower() if isinstance(v, str) else v
                    else:
                        row_dict[canonical_field] = _blank_to_none(value)
                    break

        return row_dict

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
