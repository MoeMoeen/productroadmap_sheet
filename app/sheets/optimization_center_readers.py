# productroadmap_sheet_project/app/sheets/optimization_center_readers.py
"""Readers for Optimization Center tabs (Candidates, Scenario_Config, Constraints, Targets, Runs, Results, Gaps_and_alerts)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from app.sheets.client import SheetsClient
from app.sheets.models import (
    OPT_CANDIDATES_HEADER_MAP,
    OPT_SCENARIO_CONFIG_HEADER_MAP,
    OPT_CONSTRAINTS_HEADER_MAP,
    OPT_TARGETS_HEADER_MAP,
    OPT_RUNS_HEADER_MAP,
    OPT_RESULTS_HEADER_MAP,
    OPT_GAPS_ALERTS_HEADER_MAP,
    OptCandidateRow,
    OptScenarioConfigRow,
    OptConstraintRow,
    OptTargetRow,
    OptRunRow,
    OptResultRow,
    OptGapAlertRow,
)
from app.utils.header_utils import normalize_header


logger = logging.getLogger(__name__)


def _col_index_to_a1(idx: int) -> str:
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def _blank_to_none(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, str) and val.strip() == "":
        return None
    return val


def _to_bool(val: Any) -> Optional[bool]:
    val = _blank_to_none(val)
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    return None


def _to_float(val: Any) -> Optional[float]:
    val = _blank_to_none(val)
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        try:
            return float(str(val).strip())
        except Exception:
            return None


def _to_int(val: Any) -> Optional[int]:
    val = _blank_to_none(val)
    if val is None:
        return None
    try:
        return int(val)
    except Exception:
        try:
            return int(float(str(val).strip()))
        except Exception:
            return None


def _split_keys(val: Any) -> Optional[List[str]]:
    """
    Split a cell value into a list of strings, using commas or semicolons as delimiters.
    For example: "key1, key2; key3" -> ["key1", "key2", "key3"].
    """
    val = _blank_to_none(val)
    if val is None:
        return None
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    text = str(val)
    parts = [p.strip() for p in text.replace(";", ",").split(",")]
    out = [p for p in parts if p]
    return out if out else None


def _to_date_iso(val: Any) -> Optional[str]:
    val = _blank_to_none(val)
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.date().isoformat() if isinstance(val, datetime) else val.isoformat()
    s = str(val).strip()
    if not s:
        return None
    iso_like = len(s) == 10 and s[4] == "-" and s[7] == "-" and s[:4].isdigit() and s[5:7].isdigit() and s[8:].isdigit()
    try:
        return datetime.fromisoformat(s).date().isoformat()
    except Exception:
        if not iso_like:
            logger.warning("opt_reader.date_parse_failed", extra={"value": s})
        return s  # Leave as-is; upstream can validate


def _parse_json(val: Any) -> Optional[Any]:
    val = _blank_to_none(val)
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(str(val))
    except Exception:
        return str(val)


def _build_alias_lookup(header_map: Dict[str, List[str]]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for field, aliases in header_map.items():
        for a in aliases:
            lookup[normalize_header(a)] = field
    return lookup


def _row_to_dict(header: List[Any], row_cells: List[Any], lookup: Dict[str, str]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for idx, col_name in enumerate(header):
        nh = normalize_header(str(col_name))
        if nh not in lookup:
            continue
        field = lookup[nh]
        row[field] = row_cells[idx] if idx < len(row_cells) else None
    return row


class _BaseOptReader:
    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def _read_raw(self, spreadsheet_id: str, tab_name: str, header_row: int = 1) -> Tuple[List[Any], List[List[Any]]]:
        """Read header and data rows. Skips rows 2-3 (metadata)."""
        header_values = self.client.get_values(spreadsheet_id, f"{tab_name}!{header_row}:{header_row}")
        if not header_values or not header_values[0]:
            return [], []
        header = header_values[0]
        end_col_letter = _col_index_to_a1(len(header))
        # Read all rows from row 1 onwards, then manually skip rows 2-3
        # (If we start from A4, Google Sheets skips empty rows, causing row number misalignment)
        data_range = f"{tab_name}!A1:{end_col_letter}"
        all_rows = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=data_range,
            value_render_option="UNFORMATTED_VALUE",
        )
        # Skip header (row 1) and metadata (rows 2-3), keep rows 4+
        data_rows = all_rows[3:] if len(all_rows) > 3 else []
        return header, data_rows


class CandidatesReader(_BaseOptReader):
    def get_rows(self, spreadsheet_id: str, tab_name: str) -> List[Tuple[int, OptCandidateRow]]:
        header, data_rows = self._read_raw(spreadsheet_id, tab_name)
        if not header:
            return []
        lookup = _build_alias_lookup(OPT_CANDIDATES_HEADER_MAP)
        rows: List[Tuple[int, OptCandidateRow]] = []
        row_num = 4  # Data starts at row 4 (1=header, 2-3=metadata)
        blank_run = 0
        blank_run_cutoff = 50
        for row_cells in data_rows:
            rd = _row_to_dict(header, row_cells, lookup)
            rd["engineering_tokens"] = _to_float(rd.get("engineering_tokens"))
            rd["active_overall_score"] = _to_float(rd.get("active_overall_score"))
            rd["north_star_contribution"] = _to_float(rd.get("north_star_contribution"))
            rd["is_mandatory"] = _to_bool(rd.get("is_mandatory"))
            rd["is_selected_for_run"] = _to_bool(rd.get("is_selected_for_run"))
            rd["prerequisite_keys"] = _split_keys(rd.get("prerequisite_keys"))
            rd["exclusion_keys"] = _split_keys(rd.get("exclusion_keys"))
            rd["synergy_group_keys"] = _split_keys(rd.get("synergy_group_keys"))
            rd["deadline_date"] = _to_date_iso(rd.get("deadline_date"))
            # strategic_kpi_contributions must be string (for JSON), but may come as number from sheets
            if rd.get("strategic_kpi_contributions") is not None and not isinstance(rd.get("strategic_kpi_contributions"), str):
                rd["strategic_kpi_contributions"] = str(rd["strategic_kpi_contributions"])
            for k in list(rd.keys()):
                rd[k] = _blank_to_none(rd.get(k))
            key_val = rd.get("initiative_key")
            has_values = any(v is not None for v in rd.values())
            if not has_values:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
                row_num += 1
                continue
            try:
                rows.append((row_num, OptCandidateRow(**rd)))
            except Exception as e:
                key = rd.get("initiative_key")
                logger.warning(
                    "opt_reader.row_parse_failed",
                    extra={"tab": tab_name, "row": row_num, "key": key, "error": str(e)[:200]},
                )
            row_num += 1
            if not key_val:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
            else:
                blank_run = 0
        return rows


class ScenarioConfigReader(_BaseOptReader):
    def get_rows(self, spreadsheet_id: str, tab_name: str) -> List[Tuple[int, OptScenarioConfigRow]]:
        header, data_rows = self._read_raw(spreadsheet_id, tab_name)
        if not header:
            return []
        lookup = _build_alias_lookup(OPT_SCENARIO_CONFIG_HEADER_MAP)
        rows: List[Tuple[int, OptScenarioConfigRow]] = []
        row_num = 4  # Data starts at row 4 (1=header, 2-3=metadata)
        blank_run = 0
        blank_run_cutoff = 50
        for row_cells in data_rows:
            rd = _row_to_dict(header, row_cells, lookup)
            rd["capacity_total_tokens"] = _to_float(rd.get("capacity_total_tokens"))
            rd["objective_weights_json"] = _parse_json(rd.get("objective_weights_json"))
            for k in list(rd.keys()):
                rd[k] = _blank_to_none(rd.get(k))
            key_val = rd.get("scenario_name")
            has_values = any(v is not None for v in rd.values())
            if not has_values:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
                row_num += 1
                continue
            try:
                rows.append((row_num, OptScenarioConfigRow(**rd)))
            except Exception as e:
                key = rd.get("scenario_name")
                logger.warning(
                    "opt_reader.row_parse_failed",
                    extra={"tab": tab_name, "row": row_num, "key": key, "error": str(e)[:200]},
                )
            row_num += 1
            if not key_val:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
            else:
                blank_run = 0
        return rows


class ConstraintsReader(_BaseOptReader):
    def get_rows(self, spreadsheet_id: str, tab_name: str) -> List[Tuple[int, OptConstraintRow]]:
        header, data_rows = self._read_raw(spreadsheet_id, tab_name)
        if not header:
            return []
        lookup = _build_alias_lookup(OPT_CONSTRAINTS_HEADER_MAP)
        rows: List[Tuple[int, OptConstraintRow]] = []
        row_num = 4  # Data starts at row 4 (1=header, 2-3=metadata)
        blank_run = 0
        blank_run_cutoff = 50
        for row_cells in data_rows:
            rd = _row_to_dict(header, row_cells, lookup)
            rd["min_tokens"] = _to_float(rd.get("min_tokens"))
            rd["max_tokens"] = _to_float(rd.get("max_tokens"))
            rd["target_value"] = _to_float(rd.get("target_value"))
            for k in list(rd.keys()):
                rd[k] = _blank_to_none(rd.get(k))
            key_val = (rd.get("constraint_type") or "") + (rd.get("dimension") or "")
            has_values = any(v is not None for v in rd.values())
            if not has_values:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
                row_num += 1
                continue
            try:
                rows.append((row_num, OptConstraintRow(**rd)))
            except Exception as e:
                key = rd.get("constraint_type") or rd.get("dimension")
                logger.warning(
                    "opt_reader.row_parse_failed",
                    extra={"tab": tab_name, "row": row_num, "key": key, "error": str(e)[:200]},
                )
            row_num += 1
            if not key_val:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
            else:
                blank_run = 0
        return rows


class TargetsReader(_BaseOptReader):
    def get_rows(self, spreadsheet_id: str, tab_name: str) -> List[Tuple[int, OptTargetRow]]:
        header, data_rows = self._read_raw(spreadsheet_id, tab_name)
        if not header:
            return []
        lookup = _build_alias_lookup(OPT_TARGETS_HEADER_MAP)
        rows: List[Tuple[int, OptTargetRow]] = []
        row_num = 4  # Data starts at row 4 (1=header, 2-3=metadata)
        blank_run = 0
        blank_run_cutoff = 50
        for row_cells in data_rows:
            rd = _row_to_dict(header, row_cells, lookup)
            rd["target_value"] = _to_float(rd.get("target_value"))
            for k in list(rd.keys()):
                rd[k] = _blank_to_none(rd.get(k))
            key_val = (rd.get("market") or "") + (rd.get("kpi_key") or "")
            has_values = any(v is not None for v in rd.values())
            if not has_values:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
                row_num += 1
                continue
            try:
                rows.append((row_num, OptTargetRow(**rd)))
            except Exception as e:
                key = rd.get("market") or rd.get("kpi_key")
                logger.warning(
                    "opt_reader.row_parse_failed",
                    extra={"tab": tab_name, "row": row_num, "key": key, "error": str(e)[:200]},
                )
            row_num += 1
            if not key_val:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
            else:
                blank_run = 0
        return rows


class RunsReader(_BaseOptReader):
    def get_rows(self, spreadsheet_id: str, tab_name: str) -> List[Tuple[int, OptRunRow]]:
        header, data_rows = self._read_raw(spreadsheet_id, tab_name)
        if not header:
            return []
        lookup = _build_alias_lookup(OPT_RUNS_HEADER_MAP)
        rows: List[Tuple[int, OptRunRow]] = []
        row_num = 4  # Data starts at row 4 (1=header, 2-3=metadata)
        blank_run = 0
        blank_run_cutoff = 50
        for row_cells in data_rows:
            rd = _row_to_dict(header, row_cells, lookup)
            rd["selected_count"] = _to_int(rd.get("selected_count"))
            rd["total_objective"] = _to_float(rd.get("total_objective"))
            rd["capacity_used"] = _to_float(rd.get("capacity_used"))
            rd["created_at"] = _to_date_iso(rd.get("created_at"))
            rd["finished_at"] = _to_date_iso(rd.get("finished_at"))
            for k in list(rd.keys()):
                rd[k] = _blank_to_none(rd.get(k))
            key_val = rd.get("run_id")
            has_values = any(v is not None for v in rd.values())
            if not has_values:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
                row_num += 1
                continue
            try:
                rows.append((row_num, OptRunRow(**rd)))
            except Exception as e:
                key = rd.get("run_id")
                logger.warning(
                    "opt_reader.row_parse_failed",
                    extra={"tab": tab_name, "row": row_num, "key": key, "error": str(e)[:200]},
                )
            row_num += 1
            if not key_val:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
            else:
                blank_run = 0
        return rows


class ResultsReader(_BaseOptReader):
    def get_rows(self, spreadsheet_id: str, tab_name: str) -> List[Tuple[int, OptResultRow]]:
        header, data_rows = self._read_raw(spreadsheet_id, tab_name)
        if not header:
            return []
        lookup = _build_alias_lookup(OPT_RESULTS_HEADER_MAP)
        rows: List[Tuple[int, OptResultRow]] = []
        row_num = 4  # Data starts at row 4 (1=header, 2-3=metadata)
        blank_run = 0
        blank_run_cutoff = 50
        for row_cells in data_rows:
            rd = _row_to_dict(header, row_cells, lookup)
            rd["selected"] = _to_bool(rd.get("selected"))
            rd["allocated_tokens"] = _to_float(rd.get("allocated_tokens"))
            rd["north_star_gain"] = _to_float(rd.get("north_star_gain"))
            rd["active_overall_score"] = _to_float(rd.get("active_overall_score"))
            for k in list(rd.keys()):
                rd[k] = _blank_to_none(rd.get(k))
            key_val = rd.get("initiative_key")
            has_values = any(v is not None for v in rd.values())
            if not has_values:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
                row_num += 1
                continue
            try:
                rows.append((row_num, OptResultRow(**rd)))
            except Exception as e:
                key = rd.get("initiative_key")
                logger.warning(
                    "opt_reader.row_parse_failed",
                    extra={"tab": tab_name, "row": row_num, "key": key, "error": str(e)[:200]},
                )
            row_num += 1
            if not key_val:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
            else:
                blank_run = 0
        return rows


class GapsAlertsReader(_BaseOptReader):
    def get_rows(self, spreadsheet_id: str, tab_name: str) -> List[Tuple[int, OptGapAlertRow]]:
        header, data_rows = self._read_raw(spreadsheet_id, tab_name)
        if not header:
            return []
        lookup = _build_alias_lookup(OPT_GAPS_ALERTS_HEADER_MAP)
        rows: List[Tuple[int, OptGapAlertRow]] = []
        row_num = 4  # Data starts at row 4 (1=header, 2-3=metadata)
        blank_run = 0
        blank_run_cutoff = 50
        for row_cells in data_rows:
            rd = _row_to_dict(header, row_cells, lookup)
            rd["target"] = _to_float(rd.get("target"))
            rd["achieved"] = _to_float(rd.get("achieved"))
            rd["gap"] = _to_float(rd.get("gap"))
            for k in list(rd.keys()):
                rd[k] = _blank_to_none(rd.get(k))
            key_val = (rd.get("market") or "") + (rd.get("kpi_key") or "")
            has_values = any(v is not None for v in rd.values())
            if not has_values:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
                row_num += 1
                continue
            try:
                rows.append((row_num, OptGapAlertRow(**rd)))
            except Exception as e:
                key = rd.get("market") or rd.get("kpi_key")
                logger.warning(
                    "opt_reader.row_parse_failed",
                    extra={"tab": tab_name, "row": row_num, "key": key, "error": str(e)[:200]},
                )
            row_num += 1
            if not key_val:
                blank_run += 1
                if blank_run >= blank_run_cutoff:
                    break
            else:
                blank_run = 0
        return rows


__all__ = [
    "CandidatesReader",
    "ScenarioConfigReader",
    "ConstraintsReader",
    "TargetsReader",
    "RunsReader",
    "ResultsReader",
    "GapsAlertsReader",
]
