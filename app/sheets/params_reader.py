# productroadmap_sheet_project/app/sheets/params_reader.py

"""Params sheet reader for ProductOps sheet."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple, Optional

from app.sheets.client import SheetsClient
from app.sheets.models import ParamRow, PARAMS_HEADER_MAP
from app.utils.header_utils import normalize_header


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
        start_data_row: int = 2,
        max_rows: Optional[int] = None,
    ) -> List[ParamRowPair]:
        """Read Param rows for a given sheet/tab as (row_number, ParamRow)."""
        
        # Get grid size to build precise A1 range
        grid_rows, grid_cols = self.client.get_sheet_grid_size(spreadsheet_id, tab_name)
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
        data_rows = raw_values[1:]
        
        rows: List[ParamRowPair] = []
        current_row_number = start_data_row
        
        for row_cells in data_rows:
            if self._is_empty_row(row_cells):
                current_row_number += 1
                continue
            
            row_dict = self._row_to_dict(header, row_cells)
            try:
                param_row = ParamRow(**row_dict)
                rows.append((current_row_number, param_row))
            except Exception as e:
                # Log parsing errors but don't fail the entire read
                print(f"Error parsing Param row {current_row_number}: {e}")
            
            current_row_number += 1
        
        return rows
    
    def _row_to_dict(self, header: List[Any], row_cells: List[Any]) -> Dict[str, Any]:
        """Map a list of cell values into a dict based on header names.
        
        Uses PARAMS_HEADER_MAP for alias resolution.
        """
        row_dict: Dict[str, Any] = {}
        for idx, col_name in enumerate(header):
            key = str(col_name).strip()
            if not key:
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
