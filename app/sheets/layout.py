# productroadmap_sheet_project/app/sheets/layout.py
"""Sheet layout configuration — single source of truth for reserved rows per tab.

All readers/writers MUST use these helpers instead of hardcoding row offsets.
Changing reserved rows (e.g., adding/removing meta rows) is a config change here only.

Convention (default):
    Row 1        = Header row (column names)
    Rows 2..N-1  = Meta/reserved rows (source mapping, notes, etc.)
    Row N        = First data row

By default, N = 4 (header + 2 meta rows, data starts at row 4).
Per-tab overrides are supported via TAB_LAYOUT.
"""

from __future__ import annotations

from typing import Dict


# ---------------------------------------------------------------------------
# Central layout registry
# ---------------------------------------------------------------------------

DEFAULT_DATA_START_ROW: int = 4   # 1-indexed
DEFAULT_HEADER_ROW: int = 1      # 1-indexed

# Per-tab overrides.  Key = **exact sheet tab name**, lowercased and stripped.
# For example, if the Google Sheet tab is called "Scoring_Inputs", use:
#   "scoring_inputs": 5
# NOT a logical alias like "scoring" — the key must match the tab_name string
# passed to readers/writers (which is always the literal sheet tab name).
# Example:
#   "candidates": 5,   # if we ever add an instructions row
TAB_LAYOUT: Dict[str, int] = {
    # Optimization Center: reserve row 4 for instructions (data starts row 5)
    "candidates": 5,
    "scenario_config": 5,
    "constraints": 5,
    "targets": 5,
    "runs": 5,
    "results": 5,
    "gaps_and_alerts": 5,

    # Product Ops: reserve row 4 for instructions (data starts row 5)
    "scoring_inputs": 5,
    "mathmodels": 5,
    "params": 5,
    "metrics_config": 5,
    "kpi_contributions": 5,
    "config": 5,
}


# ---------------------------------------------------------------------------
# Public API — used by all readers / writers
# ---------------------------------------------------------------------------

def data_start_row(tab: str = "") -> int:
    """Return the 1-indexed row where real data begins for a given tab.

    Falls back to DEFAULT_DATA_START_ROW if no per-tab override exists.
    """
    key = (tab or "").strip().lower()
    return TAB_LAYOUT.get(key, DEFAULT_DATA_START_ROW)


def header_row(tab: str = "") -> int:
    """Return the 1-indexed header row for a given tab."""
    # Currently always row 1; parameterized for future flexibility.
    return DEFAULT_HEADER_ROW


def meta_rows_count(tab: str = "") -> int:
    """Return the number of meta/reserved rows between header and data.

    meta_rows_count = data_start_row - header_row - 1
    e.g. default = 4 - 1 - 1 = 2 meta rows.
    """
    return data_start_row(tab) - header_row(tab) - 1


def data_row_index(tab: str = "") -> int:
    """Return the 0-indexed list position where data begins in a full-sheet values array.

    Useful for slicing: ``data_rows = all_values[data_row_index(tab):]``
    """
    return data_start_row(tab) - 1
