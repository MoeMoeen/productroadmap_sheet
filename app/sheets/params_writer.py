# productroadmap_sheet_project/app/sheets/params_writer.py

"""Params sheet writer for ProductOps sheet.

Implements append-only strategy:
- Never deletes existing rows
- Only updates value cells if not already approved
- Adds is_auto_seeded flag to track auto-generated parameters
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
import logging

from app.sheets.client import SheetsClient
from app.sheets.models import PARAMS_HEADER_MAP
from app.utils.header_utils import normalize_header

logger = logging.getLogger(__name__)


class ParamsWriter:
    """Writer for Params tab with append-only strategy.
    
    Rules:
    1. Never delete rows
    2. Only update value if not approved
    3. Only update metadata if row doesn't exist
    4. Track is_auto_seeded flag for each parameter
    
    This ensures human-edited parameters are never lost, while still
    allowing automatic parameter suggestion and updates.
    """
    
    def __init__(self, client: SheetsClient) -> None:
        self.client = client
    
    def append_parameters(
        self,
        spreadsheet_id: str,
        tab_name: str,
        parameters: List[Dict[str, Any]],
    ) -> None:
        """Append new parameter rows to the Params tab.
        
        Each parameter dict should have:
        {
            "initiative_key": str,
            "param_name": str,
            "value": str/float,
            "unit": Optional[str],
            "display": Optional[str],
            "description": Optional[str],
            "source": Optional[str],
            "approved": bool (default False),
            "is_auto_seeded": bool (default True),
            "framework": str (default "MATH_MODEL"),
        }
        """
        if not parameters:
            return
        
        # Get header to determine column order
        header_row = 1
        range_a1 = f"{tab_name}!{header_row}:{header_row}"
        header_values = self.client.get_values(spreadsheet_id, range_a1)
        
        if not header_values or not header_values[0]:
            logger.error(f"Could not find header row in {tab_name}")
            return
        
        header = header_values[0]
        column_indices = self._build_column_indices(header)
        
        # Get current last row
        grid_rows, _ = self.client.get_sheet_grid_size(spreadsheet_id, tab_name)
        start_append_row = grid_rows + 1
        
        # Build rows in column order
        rows_to_append = []
        for param in parameters:
            row = self._build_row(param, column_indices, len(header))
            rows_to_append.append(row)
        
        # Append rows
        if rows_to_append:
            end_col = _col_index_to_a1(len(header))
            range_a1 = f"{tab_name}!A{start_append_row}:{end_col}{start_append_row + len(rows_to_append) - 1}"
            
            self.client.update_values(
                spreadsheet_id=spreadsheet_id,
                range_=range_a1,
                values=rows_to_append,
                value_input_option="RAW",
            )
            
            logger.info(f"Appended {len(rows_to_append)} parameters to {tab_name}")
    
    def update_parameter_value(
        self,
        spreadsheet_id: str,
        tab_name: str,
        row_number: int,
        value: str,
        is_auto_seeded: bool = False,
    ) -> None:
        """Update a parameter value if not already approved.
        
        Only updates if the approved flag is False or absent.
        """
        # First, check if approved
        approved_col_idx = self._find_column_index(spreadsheet_id, tab_name, "approved")
        value_col_idx = self._find_column_index(spreadsheet_id, tab_name, "value")
        
        if not value_col_idx:
            logger.warning(f"Could not find value column in {tab_name}")
            return
        
        # Check if row is approved
        if approved_col_idx:
            approved_cell_a1 = f"{tab_name}!{_col_index_to_a1(approved_col_idx)}{row_number}"
            approved_values = self.client.get_values(spreadsheet_id, approved_cell_a1)
            if approved_values and approved_values[0]:
                approved = approved_values[0][0]
                if approved is True or approved == "TRUE" or approved == "true":
                    logger.warning(
                        f"Cannot update value for {tab_name} row {row_number}: already approved"
                    )
                    return
        
        # Update value
        value_cell_a1 = f"{tab_name}!{_col_index_to_a1(value_col_idx)}{row_number}"
        self.client.update_values(
            spreadsheet_id=spreadsheet_id,
            range_=value_cell_a1,
            values=[[value]],
            value_input_option="RAW",
        )
        
        # Update is_auto_seeded if column exists
        auto_seeded_col_idx = self._find_column_index(spreadsheet_id, tab_name, "is_auto_seeded")
        if auto_seeded_col_idx:
            auto_seeded_cell_a1 = f"{tab_name}!{_col_index_to_a1(auto_seeded_col_idx)}{row_number}"
            self.client.update_values(
                spreadsheet_id=spreadsheet_id,
                range_=auto_seeded_cell_a1,
                values=[[is_auto_seeded]],
                value_input_option="RAW",
            )
    
    def update_parameters_batch(
        self,
        spreadsheet_id: str,
        tab_name: str,
        updates: List[Dict[str, Any]],
    ) -> None:
        """Batch update multiple parameters in a single API call.
        
        Each update dict should have:
        {
            "row_number": int,
            "value": Optional[str],
            "is_auto_seeded": Optional[bool],
        }
        
        Only updates values if not approved.
        """
        if not updates:
            return
        
        # Find columns
        value_col_idx = self._find_column_index(spreadsheet_id, tab_name, "value")
        approved_col_idx = self._find_column_index(spreadsheet_id, tab_name, "approved")
        auto_seeded_col_idx = self._find_column_index(spreadsheet_id, tab_name, "is_auto_seeded")
        
        # Build batch update data
        batch_data = []
        
        for update in updates:
            row_number = update.get("row_number")
            new_value = update.get("value")
            is_auto_seeded = update.get("is_auto_seeded", False)
            
            # Check if approved (skip if yes)
            if approved_col_idx:
                approved_cell_a1 = f"{tab_name}!{_col_index_to_a1(approved_col_idx)}{row_number}"
                approved_values = self.client.get_values(spreadsheet_id, approved_cell_a1)
                if approved_values and approved_values[0]:
                    approved = approved_values[0][0]
                    if approved is True or approved == "TRUE" or approved == "true":
                        logger.debug(
                            f"Skipping update to row {row_number}: already approved"
                        )
                        continue
            
            # Add value update
            if value_col_idx and new_value is not None:
                value_cell_a1 = f"{tab_name}!{_col_index_to_a1(value_col_idx)}{row_number}"
                batch_data.append({
                    "range": value_cell_a1,
                    "values": [[new_value]],
                })
            
            # Add auto_seeded update
            if auto_seeded_col_idx:
                auto_seeded_cell_a1 = f"{tab_name}!{_col_index_to_a1(auto_seeded_col_idx)}{row_number}"
                batch_data.append({
                    "range": auto_seeded_cell_a1,
                    "values": [[is_auto_seeded]],
                })
        
        if batch_data:
            self.client.batch_update_values(
                spreadsheet_id=spreadsheet_id,
                data=batch_data,
                value_input_option="RAW",
            )
    
    def _build_column_indices(self, header: List[str]) -> Dict[str, int]:
        """Build a mapping of normalized column names to 1-based indices."""
        indices = {}
        for i, col_name in enumerate(header, start=1):
            normalized = normalize_header(str(col_name))
            indices[normalized] = i
        return indices
    
    def _build_row(
        self,
        param: Dict[str, Any],
        column_indices: Dict[str, int],
        total_cols: int,
    ) -> List[Any]:
        """Build a row in the correct column order."""
        row = [""] * total_cols  # Initialize with empty strings
        
        field_mapping = {
            "initiative_key": "initiative_key",
            "param_name": "param_name",
            "value": "value",
            "unit": "unit",
            "display": "display",
            "description": "description",
            "source": "source",
            "approved": "approved",
            "is_auto_seeded": "is_auto_seeded",
            "framework": "framework",
        }
        
        for normalized_col, param_field in field_mapping.items():
            if normalized_col in column_indices and param_field in param:
                col_idx = column_indices[normalized_col] - 1  # Convert to 0-based
                row[col_idx] = param[param_field]
        
        return row
    
    def _find_column_index(
        self,
        spreadsheet_id: str,
        tab_name: str,
        column_name: str,
    ) -> Optional[int]:
        """Find the 1-based column index for a given column name.
        
        Uses PARAMS_HEADER_MAP to check for all known aliases.
        """
        header_row = 1
        range_a1 = f"{tab_name}!{header_row}:{header_row}"
        
        try:
            values = self.client.get_values(spreadsheet_id, range_a1)
            if not values:
                return None
            
            headers = values[0]
            
            # Get all aliases for this canonical column name
            aliases = PARAMS_HEADER_MAP.get(column_name, [column_name])
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
