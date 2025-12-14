# productroadmap_sheet_project/app/sheets/math_models_writer.py

"""MathModels sheet writer for ProductOps sheet.

Writes LLM suggestions to separate columns in the MathModels tab.
Never overwrites user-approved cells.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
import logging

from app.sheets.client import SheetsClient
from app.sheets.models import MATHMODELS_HEADER_MAP
from app.utils.header_utils import normalize_header

logger = logging.getLogger(__name__)


class MathModelsWriter:
    """Writer for LLM suggestions in MathModels tab.
    
    Strategy:
    - llm_suggested_formula_text column: populated by LLM, never overwrites
    - llm_notes column: populated by LLM, never overwrites
    - Never updates formula_text, assumptions_text, or approved fields
      if approved_by_user is True
    
    This prevents overwriting human-made changes while still providing
    LLM suggestions side-by-side.
    """
    
    def __init__(self, client: SheetsClient) -> None:
        self.client = client
    
    def write_formula_suggestion(
        self,
        spreadsheet_id: str,
        tab_name: str,
        row_number: int,
        llm_suggested_formula_text: str,
    ) -> None:
        """Write a formula suggestion to the llm_suggested_formula_text column."""
        col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_suggested_formula_text")
        if not col_idx:
            logger.warning(f"Could not find llm_suggested_formula_text column in {tab_name}")
            return
        
        col_a1 = _col_index_to_a1(col_idx)
        cell_a1 = f"{tab_name}!{col_a1}{row_number}"
        
        self.client.update_values(
            spreadsheet_id=spreadsheet_id,
            range_=cell_a1,
            values=[[llm_suggested_formula_text]],
            value_input_option="RAW",
        )
    
    def write_llm_notes(
        self,
        spreadsheet_id: str,
        tab_name: str,
        row_number: int,
        llm_notes: str,
    ) -> None:
        """Write LLM notes/assumptions to the llm_notes column."""
        col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_notes")
        if not col_idx:
            logger.warning(f"Could not find llm_notes column in {tab_name}")
            return
        
        col_a1 = _col_index_to_a1(col_idx)
        cell_a1 = f"{tab_name}!{col_a1}{row_number}"
        
        self.client.update_values(
            spreadsheet_id=spreadsheet_id,
            range_=cell_a1,
            values=[[llm_notes]],
            value_input_option="RAW",
        )
    
    def write_suggestions_batch(
        self,
        spreadsheet_id: str,
        tab_name: str,
        suggestions: List[Dict[str, Any]],
    ) -> None:
        """Batch write multiple suggestions in a single API call.
        
        Each suggestion dict should have:
        {
            "row_number": int,
            "llm_suggested_formula_text": Optional[str],
            "llm_notes": Optional[str],
        }
        """
        if not suggestions:
            return
        
        # Find column indices
        formula_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_suggested_formula_text")
        assumptions_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_notes")
        
        if not formula_col_idx and not assumptions_col_idx:
            logger.warning(f"Could not find suggestion columns in {tab_name}")
            return
        
        # Build batch update data
        batch_data = []
        
        for suggestion in suggestions:
            row_number = suggestion.get("row_number")
            formula_sugg = suggestion.get("llm_suggested_formula_text")
            assumptions_sugg = suggestion.get("llm_notes")
            
            if formula_col_idx and formula_sugg:
                col_a1 = _col_index_to_a1(formula_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({
                    "range": cell_a1,
                    "values": [[formula_sugg]],
                })
            
            if assumptions_col_idx and assumptions_sugg:
                col_a1 = _col_index_to_a1(assumptions_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({
                    "range": cell_a1,
                    "values": [[assumptions_sugg]],
                })
        
        if batch_data:
            self.client.batch_update_values(
                spreadsheet_id=spreadsheet_id,
                data=batch_data,
                value_input_option="RAW",
            )
    
    def _find_column_index(
        self,
        spreadsheet_id: str,
        tab_name: str,
        column_name: str,
    ) -> Optional[int]:
        """Find the 1-based column index for a given column name.
        
        Uses MATHMODELS_HEADER_MAP to check for all known aliases.
        """
        header_row = 1
        range_a1 = f"{tab_name}!{header_row}:{header_row}"
        
        try:
            values = self.client.get_values(spreadsheet_id, range_a1)
            if not values:
                return None
            
            headers = values[0]
            
            # Get all aliases for this canonical column name
            aliases = MATHMODELS_HEADER_MAP.get(column_name, [column_name])
            normalized_aliases = [normalize_header(a) for a in aliases]
            
            for i, h in enumerate(headers, start=1):
                if h is None:
                    continue
                if normalize_header(str(h)) in normalized_aliases:
                    return i
            
            return None
        except Exception as e:
            logger.error(f"Error finding column {column_name} in {tab_name}: {e}")
            return None


def _col_index_to_a1(idx: int) -> str:
    """Convert 1-based column index to A1 letter(s)."""
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result
