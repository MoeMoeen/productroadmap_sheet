# productroadmap_sheet_project/app/sheets/optimization_center_writers.py
"""Writers for Optimization Center tabs (DB -> Sheets).

Pattern:
- Header-only read to map column indices (alias-aware)
- Key-column read with blank-run cutoff
- Build updates only for owned/editable columns
- Chunked batch_update_values for targeted writes
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from app.sheets.client import SheetsClient
from app.sheets.models import (
    OPT_CANDIDATES_HEADER_MAP,
    OPT_SCENARIO_CONFIG_HEADER_MAP,
    OPT_CONSTRAINTS_HEADER_MAP,
    OPT_TARGETS_HEADER_MAP,
    OPT_RUNS_HEADER_MAP,
    OPT_RUNS_OUTPUT_FIELDS,
    OPT_RESULTS_HEADER_MAP,
    OPT_RESULTS_OUTPUT_FIELDS,
    OPT_GAPS_ALERTS_HEADER_MAP,
    OPT_GAPS_ALERTS_OUTPUT_FIELDS,
)
from app.utils.header_utils import normalize_header
from app.utils.provenance import Provenance, token

logger = logging.getLogger(__name__)

_BLANK_RUN_CUTOFF = 50
_BATCH_UPDATE_CHUNK_SIZE = 200
_SYSTEM_STATUS_FIELDS = ["run_status", "updated_source", "updated_at"]
_UPDATED_SOURCE_TOKEN = token(Provenance.FLOW6_SYNC_OPT_CENTER)


def _now_iso() -> str:
    """Get the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _col_index_to_a1(idx: int) -> str:
    """Convert a 1-based column index to A1 notation (e.g., 1 -> 'A', 27 -> 'AA')."""
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def _to_sheet_value(value: Any) -> Any:
    """Convert a Python value to a Sheets-compatible value."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value)
        except Exception:
            return str(value)
    return value


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert a row object to a dictionary."""
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, "model_dump") and callable(getattr(row, "model_dump")):
        try:
            return row.model_dump()
        except Exception:
            return dict(getattr(row, "__dict__", {}))
    if hasattr(row, "dict") and callable(getattr(row, "dict")):
        try:
            return row.dict()
        except Exception:
            return dict(getattr(row, "__dict__", {}))
    return dict(getattr(row, "__dict__", {}))


def _build_alias_lookup(header_map: Dict[str, List[str]]) -> Dict[str, str]:
    """Build a lookup of normalized header aliases to field names."""
    lookup: Dict[str, str] = {}
    for field, aliases in header_map.items():
        for a in aliases:
            lookup[normalize_header(a)] = field
    return lookup


def _build_column_map(header: Sequence[Any], header_map: Dict[str, List[str]]) -> Dict[int, str]:
    """Build a mapping of column indices to field names based on header aliases."""
    alias_lookup = _build_alias_lookup(header_map)
    col_map: Dict[int, str] = {}
    for idx, col_name in enumerate(header):
        nh = normalize_header(str(col_name))
        field = alias_lookup.get(nh)
        if field:
            col_map[idx] = field
    return col_map


def _read_header(client: SheetsClient, spreadsheet_id: str, tab_name: str) -> List[Any]:
    """Read the header row (first row) of a given tab."""
    header_values = client.get_values(spreadsheet_id, f"{tab_name}!1:1")
    return header_values[0] if header_values else []


def _read_key_rows_composite(
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str,
    key_fields: List[str],
    col_map: Dict[int, str],
    key_builder,
) -> Dict[str, int]:
    """Read key columns and map composite keys to row numbers."""
    col_indices: List[int] = []
    for idx, field in col_map.items():
        if field in key_fields:
            col_indices.append(idx)
    if not col_indices:
        logger.warning("opt_writer.no_key_columns", extra={"tab": tab_name, "key_fields": key_fields})
        return {}

    ranges = []
    for col_idx in sorted(col_indices):
        col_letter = _col_index_to_a1(col_idx + 1)
        ranges.append(f"{tab_name}!{col_letter}2:{col_letter}")

    value_ranges = client.batch_get_values(spreadsheet_id, ranges)
    col_values: Dict[int, List[Any]] = {}
    for col_idx, vr in zip(sorted(col_indices), value_ranges):
        col_values[col_idx] = vr.get("values", []) if vr else []

    max_rows = 0
    for vals in col_values.values():
        max_rows = max(max_rows, len(vals))

    key_to_row: Dict[str, int] = {}
    blank_run = 0
    for offset in range(max_rows):
        row_dict: Dict[str, Any] = {}
        for col_idx in col_indices:
            vals = col_values.get(col_idx, [])
            cell_val = ""
            if offset < len(vals):
                entry = vals[offset]
                raw_val = entry[0] if isinstance(entry, list) and entry else entry
                cell_val = str(raw_val).strip() if raw_val is not None else ""
            field = col_map.get(col_idx)
            if field:
                row_dict[field] = cell_val
        key = key_builder(row_dict)
        key = str(key).strip() if key is not None else ""
        row_num = offset + 2
        if not key:
            blank_run += 1
            if blank_run >= _BLANK_RUN_CUTOFF:
                break
            continue
        blank_run = 0
        if key in key_to_row:
            logger.warning("opt_writer.duplicate_key", extra={"tab": tab_name, "key": key, "row": row_num})
            continue
        key_to_row[key] = row_num
    return key_to_row


def _chunked_updates(client: SheetsClient, spreadsheet_id: str, updates: List[Dict[str, Any]]) -> None:
    """Send batch_update_values in chunks to avoid size limits."""
    for i in range(0, len(updates), _BATCH_UPDATE_CHUNK_SIZE):
        chunk = updates[i : i + _BATCH_UPDATE_CHUNK_SIZE]
        client.batch_update_values(
            spreadsheet_id=spreadsheet_id,
            data=chunk,
            value_input_option="USER_ENTERED",
        )


def _build_updates_for_rows(
    rows: Iterable[Any],
    col_map: Dict[int, str],
    key_fields: List[str],
    key_builder,
    write_fields: List[str],
    tab_name: str,
    key_to_row: Dict[str, int],
) -> Tuple[List[Dict[str, Any]], List[int], Set[Tuple[int, str]]]:
    field_to_col = {field: idx for idx, field in col_map.items()}
    updates: List[Dict[str, Any]] = []
    write_set = set(write_fields)
    key_field_set = set(key_fields)
    stamped_rows: List[int] = []
    touched_fields: Set[Tuple[int, str]] = set()

    for row in rows:
        rd = _row_to_dict(row)
        key = key_builder(rd)
        if not key:
            continue
        row_num = key_to_row.get(str(key).strip())
        if not row_num:
            logger.debug("opt_writer.missing_row", extra={"tab": tab_name, "key": key})
            continue

        row_had_update = False
        for field in write_set:
            if field in key_field_set:
                continue
            col_idx = field_to_col.get(field)
            if col_idx is None:
                continue
            value = rd.get(field)
            if value is None:
                continue  # never clear user-entered values
            cell_range = f"{tab_name}!{_col_index_to_a1(col_idx + 1)}{row_num}"
            updates.append({"range": cell_range, "values": [[_to_sheet_value(value)]]})
            row_had_update = True
            touched_fields.add((row_num, field))
        if row_had_update:
            stamped_rows.append(row_num)

    return updates, stamped_rows, touched_fields


class OptimizationCenterWriter:
    """Writer for Optimization Center tabs (DB -> Sheets)."""
    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def _write_tab(
        self,
        spreadsheet_id: str,
        tab_name: str,
        header_map: Dict[str, List[str]],
        key_fields: List[str],
        key_builder,
        write_fields: List[str],
        rows: Iterable[Any],
    ) -> int:
        """Write rows to a specific tab in the spreadsheet."""
        header = _read_header(self.client, spreadsheet_id, tab_name)
        if not header:
            logger.warning("opt_writer.empty_sheet", extra={"tab": tab_name})
            return 0

        col_map = _build_column_map(header, header_map)
        missing_keys = [kf for kf in key_fields if kf not in col_map.values()]
        if missing_keys:
            logger.warning("opt_writer.no_key_columns", extra={"tab": tab_name, "missing": missing_keys})
            return 0

        key_to_row = _read_key_rows_composite(
            self.client,
            spreadsheet_id,
            tab_name,
            key_fields=key_fields,
            col_map=col_map,
            key_builder=key_builder,
        )
        if not key_to_row:
            logger.info("opt_writer.no_existing_keys", extra={"tab": tab_name})
        updates, rows_to_stamp, touched_fields = _build_updates_for_rows(
            rows=rows,
            col_map=col_map,
            key_fields=key_fields,
            key_builder=key_builder,
            write_fields=write_fields,
            tab_name=tab_name,
            key_to_row=key_to_row,
        )

        if rows_to_stamp:
            field_to_col = {field: idx for idx, field in col_map.items()}
            us_col = field_to_col.get("updated_source")
            ua_col = field_to_col.get("updated_at")
            ts = _now_iso()
            for row_num in rows_to_stamp:
                if us_col is not None and (row_num, "updated_source") not in touched_fields:
                    updates.append(
                        {
                            "range": f"{tab_name}!{_col_index_to_a1(us_col + 1)}{row_num}",
                            "values": [[_UPDATED_SOURCE_TOKEN]],
                        }
                    )
                if ua_col is not None and (row_num, "updated_at") not in touched_fields:
                    updates.append(
                        {
                            "range": f"{tab_name}!{_col_index_to_a1(ua_col + 1)}{row_num}",
                            "values": [[ts]],
                        }
                    )

        if not updates:
            logger.info("opt_writer.no_updates", extra={"tab": tab_name})
            return 0

        try:
            _chunked_updates(self.client, spreadsheet_id, updates)
        except Exception:
            logger.exception("opt_writer.batch_update_failed", extra={"tab": tab_name, "updates": len(updates)})
            raise

        return len(updates)

    def write_candidates(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any]) -> int:
        return self._write_tab(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            header_map=OPT_CANDIDATES_HEADER_MAP,
            key_fields=["initiative_key"],
            key_builder=lambda rd: str(rd.get("initiative_key", "")).strip(),
            write_fields=_SYSTEM_STATUS_FIELDS,
            rows=rows,
        )

    def write_scenario_config(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any]) -> int:
        return self._write_tab(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            header_map=OPT_SCENARIO_CONFIG_HEADER_MAP,
            key_fields=["scenario_name"],
            key_builder=lambda rd: str(rd.get("scenario_name", "")).strip(),
            write_fields=_SYSTEM_STATUS_FIELDS,
            rows=rows,
        )

    def write_constraints(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any]) -> int:
        return self._write_tab(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            header_map=OPT_CONSTRAINTS_HEADER_MAP,
            key_fields=["scenario_name", "constraint_set_name", "constraint_type", "dimension", "dimension_key"],
            key_builder=lambda rd: "|".join([
                str(rd.get("scenario_name", "")).strip(),
                str(rd.get("constraint_set_name", "")).strip(),
                str(rd.get("constraint_type", "")).strip(),
                str(rd.get("dimension", "")).strip(),
                str(rd.get("dimension_key", "")).strip(),
            ]).strip("|"),
            write_fields=_SYSTEM_STATUS_FIELDS,
            rows=rows,
        )

    def write_targets(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any]) -> int:
        return self._write_tab(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            header_map=OPT_TARGETS_HEADER_MAP,
            key_fields=["scenario_name", "constraint_set_name", "dimension", "dimension_key", "kpi_key"],
            key_builder=lambda rd: "|".join([
                str(rd.get("scenario_name", "")).strip(),
                str(rd.get("constraint_set_name", "")).strip(),
                str(rd.get("dimension", "")).strip(),
                str(rd.get("dimension_key", "")).strip(),
                str(rd.get("kpi_key", "")).strip(),
            ]).strip("|"),
            write_fields=_SYSTEM_STATUS_FIELDS,
            rows=rows,
        )

    def append_runs_row(self, spreadsheet_id: str, tab_name: str, row: Dict[str, Any]) -> None:
        """
        Append single row to Runs tab (append-only, no key matching).
        
        Args:
            spreadsheet_id: Google Sheets ID
            tab_name: Tab name (e.g., "Runs")
            row: Dict with run data
        """
        # Read header row to get column mapping
        header_values = self.client.get_values(spreadsheet_id, f"{tab_name}!1:1")
        if not header_values or not header_values[0]:
            logger.error(f"No header found in {tab_name}")
            return
        
        header = [normalize_header(str(h)) for h in header_values[0]]
        alias_lookup = _build_alias_lookup(OPT_RUNS_HEADER_MAP)
        
        # Find next empty row
        all_values = self.client.get_values(spreadsheet_id, f"{tab_name}!A:A")
        next_row = len(all_values) + 1 if all_values else 2  # Header is row 1, data starts at 2
        
        # Build row values
        row_values = []
        for h_norm in header:
            field = alias_lookup.get(h_norm)
            if not field:
                row_values.append(None)
                continue
            value = row.get(field)
            row_values.append(_to_sheet_value(value))
        
        # Append row
        range_name = f"{tab_name}!A{next_row}"
        self.client.update_values(spreadsheet_id, range_name, [row_values])
        logger.info(f"Appended 1 row to {tab_name}", extra={"run_id": row.get("run_id")})

    def append_results_rows(self, spreadsheet_id: str, tab_name: str, rows: List[Dict[str, Any]]) -> int:
        """
        Append multiple rows to Results tab (append-only batch write).
        
        Args:
            spreadsheet_id: Google Sheets ID
            tab_name: Tab name (e.g., "Results")
            rows: List of dicts with result data
            
        Returns:
            Number of rows appended
        """
        if not rows:
            return 0
        
        # Read header row to get column mapping
        header_values = self.client.get_values(spreadsheet_id, f"{tab_name}!1:1")
        if not header_values or not header_values[0]:
            logger.error(f"No header found in {tab_name}")
            return 0
        
        header = [normalize_header(str(h)) for h in header_values[0]]
        alias_lookup = _build_alias_lookup(OPT_RESULTS_HEADER_MAP)
        
        # Find next empty row
        all_values = self.client.get_values(spreadsheet_id, f"{tab_name}!A:A")
        next_row = len(all_values) + 1 if all_values else 2
        
        # Build batch values
        batch_values = []
        for row_data in rows:
            row_values = []
            for h_norm in header:
                field = alias_lookup.get(h_norm)
                if not field:
                    row_values.append(None)
                    continue
                value = row_data.get(field)
                row_values.append(_to_sheet_value(value))
            batch_values.append(row_values)
        
        # Batch append
        range_name = f"{tab_name}!A{next_row}"
        self.client.update_values(spreadsheet_id, range_name, batch_values)
        logger.info(
            f"Appended {len(batch_values)} rows to {tab_name}",
            extra={"run_id": rows[0].get("run_id") if rows else None}
        )
        return len(batch_values)

    def append_gaps_rows(self, spreadsheet_id: str, tab_name: str, rows: List[Dict[str, Any]]) -> int:
        """
        Append multiple rows to Gaps_and_Alerts tab (append-only batch write).
        
        Args:
            spreadsheet_id: Google Sheets ID
            tab_name: Tab name (e.g., "Gaps_and_Alerts")
            rows: List of dicts with gap data
            
        Returns:
            Number of rows appended
        """
        if not rows:
            return 0
        
        # Read header row to get column mapping
        header_values = self.client.get_values(spreadsheet_id, f"{tab_name}!1:1")
        if not header_values or not header_values[0]:
            logger.error(f"No header found in {tab_name}")
            return 0
        
        header = [normalize_header(str(h)) for h in header_values[0]]
        alias_lookup = _build_alias_lookup(OPT_GAPS_ALERTS_HEADER_MAP)
        
        # Find next empty row
        all_values = self.client.get_values(spreadsheet_id, f"{tab_name}!A:A")
        next_row = len(all_values) + 1 if all_values else 2
        
        # Build batch values
        batch_values = []
        for row_data in rows:
            row_values = []
            for h_norm in header:
                field = alias_lookup.get(h_norm)
                if not field:
                    row_values.append(None)
                    continue
                value = row_data.get(field)
                row_values.append(_to_sheet_value(value))
            batch_values.append(row_values)
        
        # Batch append
        range_name = f"{tab_name}!A{next_row}"
        self.client.update_values(spreadsheet_id, range_name, batch_values)
        logger.info(
            f"Appended {len(batch_values)} rows to {tab_name}",
            extra={"run_id": rows[0].get("run_id") if rows else None}
        )
        return len(batch_values)

    def write_runs(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any]) -> int:
        return self._write_tab(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            header_map=OPT_RUNS_HEADER_MAP,
            key_fields=["run_id"],
            key_builder=lambda rd: str(rd.get("run_id", "")).strip(),
            write_fields=OPT_RUNS_OUTPUT_FIELDS + _SYSTEM_STATUS_FIELDS,
            rows=rows,
        )

    def write_results(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any]) -> int:
        return self._write_tab(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            header_map=OPT_RESULTS_HEADER_MAP,
            key_fields=["initiative_key"],
            key_builder=lambda rd: str(rd.get("initiative_key", "")).strip(),
            write_fields=OPT_RESULTS_OUTPUT_FIELDS + _SYSTEM_STATUS_FIELDS,
            rows=rows,
        )

    def write_gaps_alerts(self, spreadsheet_id: str, tab_name: str, rows: Iterable[Any]) -> int:
        return self._write_tab(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            header_map=OPT_GAPS_ALERTS_HEADER_MAP,
            key_fields=["country", "kpi_key"],
            key_builder=lambda rd: "|".join([
                str(rd.get("country", "")).strip(),
                str(rd.get("kpi_key", "")).strip(),
            ]).strip("|"),
            write_fields=OPT_GAPS_ALERTS_OUTPUT_FIELDS + _SYSTEM_STATUS_FIELDS,
            rows=rows,
        )


__all__ = [
    "OptimizationCenterWriter",
]
