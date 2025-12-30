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
from datetime import datetime, timezone

from app.sheets.client import SheetsClient
from app.sheets.models import PARAMS_HEADER_MAP
from app.utils.header_utils import normalize_header
from app.utils.provenance import Provenance, token

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    
    def _get_last_data_row(self, spreadsheet_id: str, tab_name: str) -> int:
        """Return last row index (1-based) that has data in initiative_key column.
        
        Returns 1 if only header exists.
        
        Important: values[idx] corresponds to sheet row (idx + 1).
        """
        try:
            init_key_col_idx = self._find_column_index(spreadsheet_id, tab_name, "initiative_key") or 1
            col_letter = _col_index_to_a1(init_key_col_idx)

            values = self.client.get_values(spreadsheet_id, f"{tab_name}!{col_letter}:{col_letter}") or []

            # Walk backwards; values[idx] corresponds to row (idx + 1)
            for idx in range(len(values) - 1, 0, -1):  # skip header at idx=0
                cell = values[idx][0] if (isinstance(values[idx], list) and values[idx]) else ""
                if str(cell).strip():
                    return idx + 1  # Convert list index to sheet row number

            return 1
        except Exception as e:
            logger.error(f"Error finding last data row in {tab_name}: {e}")
            return 1
    
    def append_parameters(
        self,
        spreadsheet_id: str,
        tab_name: str,
        parameters: List[Dict[str, Any]],
    ) -> None:
        """Append new parameter rows to the Params tab using append API.
        
        Uses append_values() + updatedRange to guarantee no race conditions.
        
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
        
        # Build rows in column order
        rows_to_append = []
        for param in parameters:
            row = self._build_row(param, column_indices, len(header))
            rows_to_append.append(row)
        
        if not rows_to_append:
            return
        
        # Append rows and capture response with updatedRange
        range_a1 = f"{tab_name}!A:A"
        append_resp = self.client.append_values(
            spreadsheet_id=spreadsheet_id,
            range_=range_a1,
            values=rows_to_append,
            value_input_option="RAW",
        )
        
        # Parse updatedRange from response to get exact row numbers
        import re
        updates = append_resp.get("updates", {}) if isinstance(append_resp, dict) else {}
        updated_range = updates.get("updatedRange")  # e.g. "Params!A14:N19"
        
        if not updated_range:
            logger.warning(
                "params_writer.append_parameters.no_updatedRange",
                extra={"response": str(append_resp)[:200]}
            )
            return
        
        # Parse "Params!A14:N19" to extract start_row and end_row
        m = re.search(r"!([A-Z]+)(\d+):([A-Z]+)(\d+)$", updated_range)
        if not m:
            logger.warning(
                "params_writer.append_parameters.cannot_parse_updatedRange",
                extra={"updatedRange": updated_range}
            )
            return
        
        start_row = int(m.group(2))
        end_row = int(m.group(4))
        
        # Stamp provenance for each appended row
        us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
        ua_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_at")
        if us_col_idx or ua_col_idx:
            us_col_letter = _col_index_to_a1(us_col_idx) if us_col_idx else None
            ua_col_letter = _col_index_to_a1(ua_col_idx) if ua_col_idx else None
            ts = _now_iso()
            batch_data = []
            for row_num in range(start_row, end_row + 1):
                if us_col_letter:
                    batch_data.append({
                        "range": f"{tab_name}!{us_col_letter}{row_num}",
                        "values": [[token(Provenance.FLOW4_SYNC_PARAMS)]],
                    })
                if ua_col_letter:
                    batch_data.append({
                        "range": f"{tab_name}!{ua_col_letter}{row_num}",
                        "values": [[ts]],
                    })
            if batch_data:
                self.client.batch_update_values(
                    spreadsheet_id=spreadsheet_id,
                    data=batch_data,
                    value_input_option="RAW",
                )
        
        logger.info(
            "params_writer.append_parameters.complete",
            extra={"rows_appended": len(rows_to_append), "updated_range": updated_range}
        )
    
    def append_new_params(
        self,
        spreadsheet_id: str,
        tab_name: str,
        params: List[Dict[str, Any]],
    ) -> None:
        """Append new parameter rows (Step 8 seeding).
        
        Each param dict should have:
        {
            "initiative_key": str,
            "param_name": str,
            "param_display": Optional[str],
            "description": Optional[str],
            "unit": Optional[str],
            "source": Optional[str],
            "approved": bool (default False),
            "is_auto_seeded": bool (default True),
            "framework": str (default "MATH_MODEL"),
        }
        
        Uses batch append for efficiency.
        """
        if not params:
            logger.info("No params to append")
            return
        
        # Get header
        header_row = 1
        range_a1 = f"{tab_name}!{header_row}:{header_row}"
        header_values = self.client.get_values(spreadsheet_id, range_a1)
        
        if not header_values or not header_values[0]:
            logger.error(f"Could not find header row in {tab_name}")
            return
        
        header = header_values[0]
        column_indices = self._build_column_indices(header)
        
        # Build rows
        rows_to_append = []
        for param in params:
            row = self._build_row(param, column_indices, len(header))
            rows_to_append.append(row)
        
        if not rows_to_append:
            return
        
        # Append rows and capture response with updatedRange
        range_a1 = f"{tab_name}!A:A"
        append_resp = self.client.append_values(
            spreadsheet_id=spreadsheet_id,
            range_=range_a1,
            values=rows_to_append,
            value_input_option="RAW",
        )
        
        # Parse updatedRange from response to get exact row numbers
        updates = append_resp.get("updates", {}) if isinstance(append_resp, dict) else {}
        updated_range = updates.get("updatedRange")  # e.g. "Params!A14:N19"
        
        if not updated_range:
            logger.warning(
                "params_writer.append_new_params.no_updatedRange",
                extra={"response": str(append_resp)[:200]}
            )
            return
        
        # Parse "Params!A14:N19" to extract start_row and end_row
        import re
        m = re.search(r"!([A-Z]+)(\d+):([A-Z]+)(\d+)$", updated_range)
        if not m:
            logger.warning(
                "params_writer.append_new_params.cannot_parse_updatedRange",
                extra={"updatedRange": updated_range}
            )
            return
        
        start_row = int(m.group(2))
        end_row = int(m.group(4))
        
        # Stamp provenance for each appended row
        us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
        ua_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_at")
        if us_col_idx or ua_col_idx:
            us_col_letter = _col_index_to_a1(us_col_idx) if us_col_idx else None
            ua_col_letter = _col_index_to_a1(ua_col_idx) if ua_col_idx else None
            ts = _now_iso()
            batch_data = []
            for row_num in range(start_row, end_row + 1):
                if us_col_letter:
                    batch_data.append({
                        "range": f"{tab_name}!{us_col_letter}{row_num}",
                        "values": [[token(Provenance.FLOW4_SEED_PARAMS)]],
                    })
                if ua_col_letter:
                    batch_data.append({
                        "range": f"{tab_name}!{ua_col_letter}{row_num}",
                        "values": [[ts]],
                    })
            if batch_data:
                self.client.batch_update_values(
                    spreadsheet_id=spreadsheet_id,
                    data=batch_data,
                    value_input_option="RAW",
                )
        
        logger.info(
            "params_writer.append_new_params.complete",
            extra={"rows_appended": len(rows_to_append), "updated_range": updated_range}
        )

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
        
        # Stamp provenance if Updated Source column exists
        us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
        ua_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_at")
        if us_col_idx or ua_col_idx:
            updates = []
            if us_col_idx:
                us_a1 = f"{tab_name}!{_col_index_to_a1(us_col_idx)}{row_number}"
                updates.append({"range": us_a1, "values": [[token(Provenance.FLOW4_SYNC_PARAMS)]]})
            if ua_col_idx:
                ua_a1 = f"{tab_name}!{_col_index_to_a1(ua_col_idx)}{row_number}"
                updates.append({"range": ua_a1, "values": [[_now_iso()]]})
            if updates:
                self.client.batch_update_values(
                    spreadsheet_id=spreadsheet_id,
                    data=updates,
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
        updated_rows = set()
        
        for update in updates:
            row_number = update.get("row_number")
            new_value = update.get("value")
            is_auto_seeded = update.get("is_auto_seeded", False)

            if not isinstance(row_number, int):
                logger.debug("params_writer.update_batch.skip_bad_row", extra={"row_number": row_number})
                continue
            
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
                updated_rows.add(row_number)
            
            # Add auto_seeded update
            if auto_seeded_col_idx:
                auto_seeded_cell_a1 = f"{tab_name}!{_col_index_to_a1(auto_seeded_col_idx)}{row_number}"
                batch_data.append({
                    "range": auto_seeded_cell_a1,
                    "values": [[is_auto_seeded]],
                })
                updated_rows.add(row_number)
        
        if batch_data:
            # Add provenance token for all updated rows if Updated Source column exists
            us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
            ua_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_at")
            if us_col_idx or ua_col_idx:
                ts = _now_iso()
                for row_number in updated_rows:
                    if us_col_idx:
                        us_a1 = f"{tab_name}!{_col_index_to_a1(us_col_idx)}{row_number}"
                        batch_data.append({
                            "range": us_a1,
                            "values": [[token(Provenance.FLOW4_SYNC_PARAMS)]],
                        })
                    if ua_col_idx:
                        ua_a1 = f"{tab_name}!{_col_index_to_a1(ua_col_idx)}{row_number}"
                        batch_data.append({
                            "range": ua_a1,
                            "values": [[ts]],
                        })
            self.client.batch_update_values(
                spreadsheet_id=spreadsheet_id,
                data=batch_data,
                value_input_option="RAW",
            )
    
    def backfill_seeded_provenance(
        self,
        spreadsheet_id: str,
        tab_name: str,
    ) -> int:
        """Backfill Updated Source and is_auto_seeded for existing AI-seeded rows.
        
        Finds rows where source matches AI indicators (e.g., "ai_suggested") and
        either updated_source or is_auto_seeded is blank/missing, then sets:
        - updated_source = flow4.seed_params
        - is_auto_seeded = TRUE
        
        Returns number of rows updated.
        """
        # Get all rows
        range_a1 = f"{tab_name}!A:Z"
        try:
            all_values = self.client.get_values(spreadsheet_id, range_a1)
        except Exception as e:
            logger.error(f"Could not read {tab_name} for backfill: {e}")
            return 0
        
        if not all_values or len(all_values) < 2:
            return 0
        
        # Find relevant columns
        notes_col_idx = self._find_column_index(spreadsheet_id, tab_name, "notes")
        updated_source_col_idx = self._find_column_index(spreadsheet_id, tab_name, "Updated_Source")
        is_auto_seeded_col_idx = self._find_column_index(spreadsheet_id, tab_name, "is_auto_seeded")
        
        if not (notes_col_idx or updated_source_col_idx or is_auto_seeded_col_idx):
            logger.warning(f"Could not find required columns in {tab_name} for backfill")
            return 0
        
        batch_data = []
        updated_count = 0
        touched_rows = set()
        
        ua_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_at")

        # Scan rows starting from row 2 (skip header)
        for row_idx, row in enumerate(all_values[1:], start=2):
            notes_val = row[notes_col_idx - 1] if notes_col_idx and notes_col_idx <= len(row) else None
            updated_source_val = row[updated_source_col_idx - 1] if updated_source_col_idx and updated_source_col_idx <= len(row) else None
            is_auto_seeded_val = row[is_auto_seeded_col_idx - 1] if is_auto_seeded_col_idx and is_auto_seeded_col_idx <= len(row) else None
            
            # Check if this row looks AI-seeded (check notes column)
            is_ai_seeded = (
                notes_val and 
                isinstance(notes_val, str) and 
                ("ai_suggested" in notes_val.lower() or "llm" in notes_val.lower())
            )
            
            if not is_ai_seeded:
                logger.info(f"Skipping row {row_idx} in {tab_name}: not AI-seeded")
                continue
            
            # Check if backfill needed
            needs_updated_source = not updated_source_val or updated_source_val == ""
            needs_is_auto_seeded = not is_auto_seeded_val or is_auto_seeded_val == "" or not is_auto_seeded_val
            
            if needs_updated_source and updated_source_col_idx:
                us_a1 = f"{tab_name}!{_col_index_to_a1(updated_source_col_idx)}{row_idx}"
                batch_data.append({
                    "range": us_a1,
                    "values": [[token(Provenance.FLOW4_SEED_PARAMS)]],
                })
                updated_count += 1
                touched_rows.add(row_idx)
            
            if needs_is_auto_seeded and is_auto_seeded_col_idx:
                auto_a1 = f"{tab_name}!{_col_index_to_a1(is_auto_seeded_col_idx)}{row_idx}"
                batch_data.append({
                    "range": auto_a1,
                    "values": [[True]],
                })
                updated_count += 1
                touched_rows.add(row_idx)

            if ua_col_idx and row_idx in touched_rows:
                ua_a1 = f"{tab_name}!{_col_index_to_a1(ua_col_idx)}{row_idx}"
                batch_data.append({
                    "range": ua_a1,
                    "values": [[_now_iso()]],
                })
        
        if batch_data:
            self.client.batch_update_values(
                spreadsheet_id=spreadsheet_id,
                data=batch_data,
                value_input_option="RAW",
            )
            logger.info(f"Backfilled {updated_count} cells in {tab_name}")
        
        return updated_count

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
            "framework": "framework",
            "param_name": "param_name",
            "param_display": "param_display",
            "description": "description",
            "unit": "unit",
            "min": "min",
            "max": "max",
            "source": "source",
            "value": "value",
            "approved": "approved",
            "is_auto_seeded": "is_auto_seeded",
            "notes": "notes",
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
