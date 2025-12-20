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
from app.utils.provenance import Provenance, token

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

        # Stamp provenance if Updated Source column exists
        us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
        if us_col_idx:
            us_a1 = f"{tab_name}!{_col_index_to_a1(us_col_idx)}{row_number}"
            self.client.update_values(
                spreadsheet_id=spreadsheet_id,
                range_=us_a1,
                values=[[token(Provenance.FLOW4_SYNC_MATHMODELS)]],
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

        # Stamp provenance if Updated Source column exists
        us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
        if us_col_idx:
            us_a1 = f"{tab_name}!{_col_index_to_a1(us_col_idx)}{row_number}"
            self.client.update_values(
                spreadsheet_id=spreadsheet_id,
                range_=us_a1,
                values=[[token(Provenance.FLOW4_SYNC_MATHMODELS)]],
                value_input_option="RAW",
            )
    
    def write_suggestions_batch(
        self,
        spreadsheet_id: str,
        tab_name: str,
        suggestions: List[Dict[str, Any]],
    ) -> None:
        """Batch write multiple suggestions in a single API call.
        
        CRITICAL: Re-checks approved_by_user before writing to prevent race conditions
        where PM approves during job execution.
        
        Each suggestion dict should have:
        {
            "row_number": int,
            "llm_suggested_formula_text": Optional[str],
            "assumptions_text": Optional[str],
            "llm_notes": Optional[str],
        }
        """
        if not suggestions:
            return
        
        # Find column indices
        formula_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_suggested_formula_text")
        assumptions_col_idx = self._find_column_index(spreadsheet_id, tab_name, "assumptions_text")
        notes_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_notes")
        approved_col_idx = self._find_column_index(spreadsheet_id, tab_name, "approved_by_user")
        
        # Guard: require at least one suggestion column
        if not (formula_col_idx or assumptions_col_idx or notes_col_idx):
            logger.warning(f"Could not find suggestion columns in {tab_name}")
            return
        
        # Race-safety: fetch current approved status before writing
        row_numbers: List[int] = []
        for s in suggestions:
            row_num = s.get("row_number")
            if isinstance(row_num, int):
                row_numbers.append(row_num)
        approved_map = {}
        if approved_col_idx and row_numbers:
            approved_map = self._get_approved_status_for_rows(
                spreadsheet_id,
                tab_name,
                row_numbers,
                approved_col_idx,
            )
        elif not approved_col_idx and row_numbers:
            logger.warning(f"Could not find approved_by_user column in {tab_name}; skipping race-safety check")
        
        # Build batch update data
        batch_data = []
        
        for suggestion in suggestions:
            row_number = suggestion.get("row_number")
            
            # Guard: row_number must be int
            if not isinstance(row_number, int):
                logger.warning("mathmodels.write.skip_bad_row_number", extra={"row_number": row_number})
                continue
            
            # RACE-SAFETY CHECK: Skip if now approved (staleness guard)
            if approved_map.get(row_number, False):
                logger.info("mathmodels.write.skip_approved", extra={"row": row_number})
                continue
            
            formula_sugg = suggestion.get("llm_suggested_formula_text")
            assumptions_sugg = suggestion.get("assumptions_text")
            notes_sugg = suggestion.get("llm_notes")
            
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

            if notes_col_idx and notes_sugg:
                col_a1 = _col_index_to_a1(notes_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({
                    "range": cell_a1,
                    "values": [[notes_sugg]],
                })
        
        if batch_data:
            # If Updated Source column exists, add provenance token for each updated row
            us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
            if us_col_idx:
                for suggestion in suggestions:
                    row_number = suggestion.get("row_number")
                    if isinstance(row_number, int):
                        us_a1 = f"{tab_name}!{_col_index_to_a1(us_col_idx)}{row_number}"
                        batch_data.append({
                            "range": us_a1,
                            "values": [[token(Provenance.FLOW4_SYNC_MATHMODELS)]],
                        })

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
    
    def _get_approved_status_for_rows(
        self,
        spreadsheet_id: str,
        tab_name: str,
        row_numbers: List[int],
        approved_col_idx: int,
    ) -> Dict[int, bool]:
        """Re-fetch approved_by_user status for rows to detect staleness.
        
        Returns dict mapping row_number -> approved_by_user value.
        Used to prevent race conditions where PM approves during job execution.
        """
        if not row_numbers or not approved_col_idx:
            return {}
        
        try:
            col_a1 = _col_index_to_a1(approved_col_idx)
            ranges = [f"{tab_name}!{col_a1}{row_num}" for row_num in row_numbers]
            
            # Fetch approved status for all rows in one call
            result = {}
            for row_num, range_a1 in zip(row_numbers, ranges):
                values = self.client.get_values(spreadsheet_id, range_a1)
                if values and values[0]:
                    # True if cell is "TRUE", "true", "1", etc.
                    cell_val = str(values[0][0]).strip().lower()
                    result[row_num] = cell_val in ("true", "1", "yes")
                else:
                    result[row_num] = False
            
            return result
        except Exception as e:
            logger.error(f"Error fetching approved status in {tab_name}: {e}")
            return {}


def _col_index_to_a1(idx: int) -> str:
    """Convert 1-based column index to A1 letter(s)."""
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result
