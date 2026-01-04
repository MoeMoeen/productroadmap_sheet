# productroadmap_sheet_project/app/sheets/math_models_reader.py

"""MathModels sheet reader for ProductOps sheet."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple, Optional

from app.sheets.client import SheetsClient
from app.sheets.models import MathModelRow, MATHMODELS_HEADER_MAP
from app.utils.header_utils import normalize_header, get_value_by_header_alias

def _blank_to_none(v):
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v

def _coerce_bool(v):
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


# Pair of (row_number, MathModelRow)
MathModelRowPair = Tuple[int, MathModelRow]


class MathModelsReader:
    """Reads MathModels tab from ProductOps sheet.
    
    Columns expected:
    - initiative_key (str)
    - model_name (str)
    - model_description_free_text (str)
    - immediate_kpi_key (str)
    - metric_chain_text (str/JSON)
    - llm_suggested_metric_chain_text (str)
    - formula_text (str) - approved/final formula
    - status (str)
    - approved_by_user (bool)
    - llm_suggested_formula_text (str) - LLM suggestion column
    - llm_notes (str) - LLM notes column
    - assumptions_text (str)
    - model_prompt_to_llm (str)
    - suggested_by_llm (bool)
    
    Returns rows as (row_number, MathModelRow) pairs.
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
    ) -> List[MathModelRowPair]:
        """Read MathModel rows for a given sheet/tab as (row_number, MathModelRow)."""
        
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
        
        rows: List[MathModelRowPair] = []
        current_row_number = start_data_row
        
        for row_cells in data_rows:
            if self._is_empty_row(row_cells):
                current_row_number += 1
                continue
            
            row_dict = self._row_to_dict(header, row_cells)
            try:
                math_model_row = MathModelRow(**row_dict)
                rows.append((current_row_number, math_model_row))
            except Exception as e:
                # Log parsing errors but don't fail the entire read
                print(f"Error parsing MathModel row {current_row_number}: {e}")
            
            current_row_number += 1
        
        return rows
    
    def _row_to_dict(self, header: List[Any], row_cells: List[Any]) -> Dict[str, Any]:
        """Map a list of cell values into a dict based on header names.
        
        Uses MATHMODELS_HEADER_MAP for alias resolution.
        """
        row_dict: Dict[str, Any] = {}
        for idx, col_name in enumerate(header):
            key = str(col_name).strip()
            if not key:
                continue
            
            normalized_key = normalize_header(key)
            value = row_cells[idx] if idx < len(row_cells) else ""
            
            # Map to MathModelRow field names using header map
            for canonical_field, aliases in MATHMODELS_HEADER_MAP.items():
                if normalized_key in [normalize_header(a) for a in aliases]:
                    if canonical_field in ("approved_by_user", "suggested_by_llm"):
                        row_dict[canonical_field] = _coerce_bool(value)
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
