# productroadmap_sheet_project/app/sheets/params_reader.py

"""Params sheet reader for ProductOps sheet."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Tuple, Optional

from app.sheets.client import SheetsClient
from app.sheets.models import ParamRow, PARAMS_HEADER_MAP
from app.utils.header_utils import normalize_header

logger = logging.getLogger("app.sheets.params_reader")

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
    # Unknown → treat as None rather than crashing the whole row
    return None


def _coerce_float(v: Any) -> Optional[float]:
    v = _blank_to_none(v)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        return None


# Pair of (row_number, ParamRow)
ParamRowPair = Tuple[int, ParamRow]


class ParamsReader:
    """Reads Params tab from ProductOps sheet.
    
    Columns expected:
    - initiative_key (str)
    - param_name (str)
    - value (str/float)
    - unit (str)
    - display (str)
    - description (str)
    - source (str)
    - approved (bool)
    - is_auto_seeded (bool)
    - framework (str) - default "MATH_MODEL"
    
    Returns rows as (row_number, ParamRow) pairs.
    """
    
    def __init__(self, client: SheetsClient) -> None:
        self.client = client
    
    def get_rows_for_sheet(
        self,
        spreadsheet_id: str,
        tab_name: str,
        header_row: int = 1,
        start_data_row: int = 4,  # Row 1=header, 2-3=metadata, data starts at 4
        max_rows: Optional[int] = None,
    ) -> List[ParamRowPair]:
        """Read Param rows for a given sheet/tab as (row_number, ParamRow).
        
        Uses open-ended range (A2:{end_col} without end row) to avoid scanning
        thousands of empty grid rows. Sheets API stops at last data automatically.
        
        Empty rows are debug-logged only. Partial rows (missing required fields)
        are warned about.
        """
        # Read header row only
        header_range = f"{tab_name}!{header_row}:{header_row}"
        header_values = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=header_range,
            value_render_option="UNFORMATTED_VALUE",
        )
        
        if not header_values or not header_values[0]:
            logger.info(f"Params tab '{tab_name}' has no header row")
            return []
        
        header = header_values[0]
        end_col_letter = _col_index_to_a1(len(header))
        
        # Read from row 1 and skip rows 2-3 to prevent empty row misalignment
        # (If we start from A4, Google Sheets skips empty rows causing row number drift)
        # Read data with open-ended range (no end row specified)
        # Sheets API will stop at the last row with data
        data_range = f"{tab_name}!A1:{end_col_letter}"
        all_values = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=data_range,
            value_render_option="UNFORMATTED_VALUE",
        ) or []
        
        # Skip header (row 1) and metadata (rows 2-3), keep rows 4+
        data_values = all_values[3:] if len(all_values) > 3 else []
        
        # Optionally cap at max_rows
        if max_rows is not None:
            data_values = data_values[:max_rows]
        
        rows: List[ParamRowPair] = []
        current_row_number = start_data_row
        
        for row_cells in data_values:
            if self._is_empty_row(row_cells):
                # Empty rows are normal; log at debug level only
                logger.debug("params_reader.skip_empty_row", extra={"row": current_row_number})
                current_row_number += 1
                continue
            
            row_dict = self._row_to_dict(header, row_cells)

            ik = row_dict.get("initiative_key")
            pn = row_dict.get("param_name")

            # Only warn on partially-filled rows missing required fields
            if not (isinstance(ik, str) and ik.strip()) or not (isinstance(pn, str) and pn.strip()):
                logger.warning(
                    "params_reader.skip_missing_required_fields",
                    extra={"row": current_row_number, "initiative_key": ik, "param_name": pn}
                )
                current_row_number += 1
                continue

            try:
                param_row = ParamRow(**row_dict)
                rows.append((current_row_number, param_row))
            except Exception as e:
                logger.warning(
                    "params_reader.parse_error",
                    extra={"row": current_row_number, "error": str(e)[:200]}
                )
            
            current_row_number += 1
        
        logger.info(
            "params_reader.complete",
            extra={"tab": tab_name, "rows_read": len(rows), "total_scanned": len(data_values)}
        )
        return rows
    
    def _row_to_dict(self, header: List[Any], row_cells: List[Any]) -> Dict[str, Any]:
        """Map a list of cell values into a dict based on header names.
        
        Uses PARAMS_HEADER_MAP for alias resolution.
        """
        row_dict: Dict[str, Any] = {}
        for idx, col_name in enumerate(header):
            key = str(col_name).strip()
            if not key:
                logger.warning(f"Skipping empty header cell at index {idx}")
                continue
            
            normalized_key = normalize_header(key)
            value = row_cells[idx] if idx < len(row_cells) else ""
            
            # Map to ParamRow field names using header map
            for canonical_field, aliases in PARAMS_HEADER_MAP.items():
                if normalized_key in [normalize_header(a) for a in aliases]:
                    # Field-specific normalization/coercion
                    if canonical_field in ("approved", "is_auto_seeded"):
                        row_dict[canonical_field] = _coerce_bool(value)
                    elif canonical_field in ("min", "max"):
                        row_dict[canonical_field] = _coerce_float(value)
                    elif canonical_field == "value":
                        # value can be float OR str; keep numeric if parseable, else keep string/non-empty
                        fv = _coerce_float(value)
                        row_dict[canonical_field] = fv if fv is not None else (_blank_to_none(value) or "")
                    else:
                        row_dict[canonical_field] = _blank_to_none(value)

                    break
        
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
