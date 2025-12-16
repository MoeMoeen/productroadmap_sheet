# productroadmap_sheet_project/app/sheets/sheet_protection.py

"""Warning-only protected ranges for ProductOps tabs (MathModels, Params, Scoring_Inputs)."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.sheets.client import SheetsClient
from app.sheets.models import (
    MATHMODELS_HEADER_MAP,
    PARAMS_HEADER_MAP,
    SCORE_FIELD_TO_HEADERS,
)
from app.utils.header_utils import normalize_header

logger = logging.getLogger(__name__)


# Define which columns are "system" (warning-protected) vs "editable" per tab
MATHMODELS_SYSTEM_COLUMNS = [
    "initiative_key",
    "model_name",
    "suggested_by_llm",
    "llm_suggested_formula_text",
    "llm_notes",
]

MATHMODELS_EDITABLE_COLUMNS = [
    "formula_text",
    "approved_by_user",
    "model_description_free_text",
    "assumptions_text",
    "model_prompt_to_llm",
]

PARAMS_SYSTEM_COLUMNS = [
    "initiative_key",
    "framework",
    "param_name",
    "is_auto_seeded",
    "param_display",
    "description",
    "unit",
    "min",
    "max",
    "source",
]

PARAMS_EDITABLE_COLUMNS = [
    "value",
    "approved",
    "notes",
]

# For Scoring_Inputs: All input columns are editable; all output columns are system
SCORING_SYSTEM_COLUMNS = [
    # All score output columns
    "rice_value_score",
    "rice_effort_score",
    "rice_overall_score",
    "wsjf_value_score",
    "wsjf_effort_score",
    "wsjf_overall_score",
    "math_value_score",
    "math_effort_score",
    "math_overall_score",
    "math_warnings",
]

SCORING_EDITABLE_COLUMNS = [
    "initiative_key",
    "active_scoring_framework",
    "use_math_model",
    "rice_reach",
    "rice_impact",
    "rice_confidence",
    "rice_effort",
    "wsjf_business_value",
    "wsjf_time_criticality",
    "wsjf_risk_reduction",
    "wsjf_job_size",
    "strategic_priority_coefficient",
    "risk_level",
    "time_sensitivity",
]


def apply_warning_protections(
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str,
    system_columns: List[str],
    header_map: Optional[Dict[str, List[str]]] = None,
) -> None:
    """Apply warningOnly=True protections to system columns in a ProductOps tab.

    Args:
        client: SheetsClient instance
        spreadsheet_id: Google Sheets spreadsheet ID
        tab_name: Tab name (e.g., "MathModels", "Params", "Scoring_Inputs")
        system_columns: List of canonical column names to protect (warning-only)
        header_map: Optional header alias map for resolving column indices
    """
    logger.info(f"Applying warning protections to {tab_name}...")

    # Get sheet properties and current protections
    props = client.get_sheet_properties(spreadsheet_id, tab_name)
    if not props:
        logger.warning(f"Could not get sheet properties for {tab_name}")
        return

    # Extract sheet ID (handle multiple response shapes)
    sheet_id = _extract_sheet_id(props, tab_name)
    if sheet_id is None:
        logger.warning(f"Could not determine sheet ID for {tab_name}")
        return

    # Read current header row to map column names to indices
    values = client.get_values(spreadsheet_id, f"{tab_name}!A1:ZZ1")
    if not values or not values[0]:
        logger.warning(f"Could not read header row from {tab_name}")
        return

    header = values[0]

    # Map system columns to column indices
    protected_indices = []
    for canonical_name in system_columns:
        col_idx = _find_column_index(header, canonical_name, header_map)
        if col_idx is not None:
            protected_indices.append(col_idx)
        else:
            logger.debug(f"Column not found in {tab_name}: {canonical_name}")

    if not protected_indices:
        logger.info(f"No columns to protect in {tab_name}")
        return

    # Get existing protected ranges
    existing = _extract_protected_ranges(props)

    # Delete previously auto-added warning ranges for this tab
    to_delete_ids = [
        pr.get("protectedRangeId")
        for pr in existing
        if isinstance(pr, dict) and pr.get("description", "").startswith(f"AUTO_PROTECT_{tab_name.upper()}_")
    ]
    delete_requests = [
        {"deleteProtectedRange": {"protectedRangeId": rid}}
        for rid in to_delete_ids
        if rid is not None
    ]

    # Create new protected ranges for system columns
    add_requests = []
    for col_idx in protected_indices:
        add_requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,  # Skip header row (editable)
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "description": f"AUTO_PROTECT_{tab_name.upper()}_{col_idx}",
                        "warningOnly": True,
                    }
                }
            }
        )

    batch_requests = delete_requests + add_requests
    if batch_requests:
        client.batch_update(spreadsheet_id, batch_requests)
        logger.info(f"Protected {len(protected_indices)} columns in {tab_name} (warning-only)")
    else:
        logger.info(f"No protection changes needed for {tab_name}")


def apply_all_productops_protections(
    client: SheetsClient,
    spreadsheet_id: str,
    math_models_tab: str = "MathModels",
    params_tab: str = "Params",
    scoring_inputs_tab: str = "Scoring_Inputs",
) -> None:
    """Apply warning-only protections to all ProductOps tabs.

    Args:
        client: SheetsClient instance
        spreadsheet_id: Google Sheets spreadsheet ID
        math_models_tab: MathModels tab name (default: "MathModels")
        params_tab: Params tab name (default: "Params")
        scoring_inputs_tab: Scoring_Inputs tab name (default: "Scoring_Inputs")
    """
    logger.info(f"Applying protections to ProductOps sheet: {spreadsheet_id}")

    # Protect MathModels tab
    apply_warning_protections(
        client=client,
        spreadsheet_id=spreadsheet_id,
        tab_name=math_models_tab,
        system_columns=MATHMODELS_SYSTEM_COLUMNS,
        header_map=MATHMODELS_HEADER_MAP,
    )

    # Protect Params tab
    apply_warning_protections(
        client=client,
        spreadsheet_id=spreadsheet_id,
        tab_name=params_tab,
        system_columns=PARAMS_SYSTEM_COLUMNS,
        header_map=PARAMS_HEADER_MAP,
    )

    # Protect Scoring_Inputs tab
    apply_warning_protections(
        client=client,
        spreadsheet_id=spreadsheet_id,
        tab_name=scoring_inputs_tab,
        system_columns=SCORING_SYSTEM_COLUMNS,
        header_map=SCORE_FIELD_TO_HEADERS,
    )

    logger.info("ProductOps sheet protections applied successfully")


def _extract_sheet_id(props: dict, tab_name: str) -> Optional[int]:
    """Extract sheet ID from various response shapes."""
    # Shape A: {"properties": {"sheetId": X, ...}}
    if "properties" in props and isinstance(props["properties"], dict):
        sheet_id = props["properties"].get("sheetId")
        if sheet_id is not None:
            return sheet_id

    # Shape B: {"sheetId": X, "title": "..."}
    if "sheetId" in props:
        return props.get("sheetId")

    # Shape C: {"sheets": [{ "properties": {...}, ...}, ...]}
    if "sheets" in props:
        for s in props["sheets"]:
            p = s.get("properties", {})
            if p.get("title") == tab_name:
                return p.get("sheetId")

    return None


def _extract_protected_ranges(props: dict) -> List[dict]:
    """Extract existing protected ranges from various response shapes."""
    # Try top-level protectedRanges
    if "protectedRanges" in props:
        return props.get("protectedRanges", []) or []

    # Try inside properties
    if "properties" in props and isinstance(props["properties"], dict):
        if "protectedRanges" in props["properties"]:
            return props["properties"].get("protectedRanges", []) or []

    # Try inside sheets array
    if "sheets" in props:
        for s in props["sheets"]:
            if "protectedRanges" in s:
                return s.get("protectedRanges", []) or []

    return []


def _find_column_index(
    header: List[str],
    canonical_name: str,
    header_map: Optional[Dict[str, List[str]]] = None,
) -> Optional[int]:
    """Find column index by canonical name with alias support.

    Args:
        header: Header row from sheet
        canonical_name: Canonical column name (e.g., "initiative_key")
        header_map: Optional map of canonical -> aliases

    Returns:
        Column index (0-based) or None if not found
    """
    normalized_canonical = normalize_header(canonical_name)

    # Try direct match first
    for idx, col_name in enumerate(header):
        if normalize_header(col_name) == normalized_canonical:
            return idx

    # Try aliases if header_map provided
    if header_map and canonical_name in header_map:
        aliases = header_map[canonical_name]
        for alias in aliases:
            normalized_alias = normalize_header(alias)
            for idx, col_name in enumerate(header):
                if normalize_header(col_name) == normalized_alias:
                    return idx

    return None
