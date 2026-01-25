# productroadmap_sheet_project/app/sheets/optimization_candidates_writer.py
"""Writer for Optimization Candidates tab - populates from DB."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.db.models.optimization import OptimizationConstraintSet, OptimizationScenario, OrganizationMetricConfig
from app.sheets.client import SheetsClient
from app.sheets.optimization_center_readers import CandidatesReader
from app.utils.provenance import Provenance, token

logger = logging.getLogger(__name__)


def populate_candidates_from_db(
    db: Session,
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str,
    scenario_name: str,
    constraint_set_name: str,
    initiative_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Populate Optimization Candidates tab from DB.
    
    Column ownership logic:
    - FORMULA COLUMNS (skip always): initiative_key, title, country, department, immediate_kpi_key
    - PM INPUT COLUMNS (preserve for existing): engineering_tokens, deadline_date, category, program_key, notes, is_selected_for_run
    - DB-DERIVED COLUMNS (write always): north_star_contribution, strategic_kpi_contributions
    - CONSTRAINT-DERIVED COLUMNS (write always): is_mandatory, bundle_key, prerequisite_keys, exclusion_keys, synergy_group_keys
    - STATUS COLUMNS (write always): run_status, updated_source, updated_at
    
    For NEW initiatives: Write all columns (seed PM inputs from DB)
    For EXISTING initiatives: Skip PM input columns, only update derived/constraint/status
    
    Args:
        db: Database session
        client: Sheets client
        spreadsheet_id: Optimization Center spreadsheet ID
        tab_name: Candidates tab name
        scenario_name: Scenario name to load constraints for
        constraint_set_name: Constraint set name to load constraints for
        initiative_keys: Optional filter for specific initiative keys
    
    Returns:
        Dict with counts: {populated_count, skipped_no_key, failed_count}
    """
    logger.info(
        f"populate_candidates_from_db: tab={tab_name}, scenario={scenario_name}, "
        f"constraint_set={constraint_set_name}, filter={initiative_keys}"
    )
    
    # Step 1: Read existing sheet data ONCE to build row index map
    reader = CandidatesReader(client)
    existing_sheet_rows = reader.get_rows(spreadsheet_id, tab_name)
    
    # Build maps: initiative_key -> row_number, initiative_key -> set
    existing_row_map: Dict[str, int] = {}  # initiative_key -> 1-based row number
    existing_sheet_keys: Set[str] = set()
    
    for row_num, row in existing_sheet_rows:
        if row.initiative_key:
            existing_row_map[row.initiative_key] = row_num
            existing_sheet_keys.add(row.initiative_key)
    
    logger.info(f"Found {len(existing_sheet_keys)} existing initiatives on Candidates tab")
    
    # Step 2: Query initiatives from DB
    query = select(Initiative).where(Initiative.is_optimization_candidate)
    if initiative_keys:
        query = query.where(Initiative.initiative_key.in_(initiative_keys))
    
    initiatives = db.scalars(query).all()
    if not initiatives:
        logger.warning("No optimization candidates found in DB")
        return {"populated_count": 0, "skipped_no_key": 0, "failed_count": 0}
    
    logger.info(f"Found {len(initiatives)} optimization candidates in DB")
    
    # Step 3: Load KPI metadata from OrganizationMetricConfig to properly classify KPI levels
    kpi_configs = db.scalars(select(OrganizationMetricConfig)).all()
    kpi_level_map: Dict[str, str] = {}  # kpi_key -> kpi_level (north_star, strategic, immediate)
    for cfg in kpi_configs:
        kpi_key_val = cfg.kpi_key
        if kpi_key_val is not None:
            kpi_level_val = cfg.kpi_level
            kpi_level_map[str(kpi_key_val)] = str(kpi_level_val) if kpi_level_val is not None else "unknown"
    
    logger.info(f"Loaded {len(kpi_level_map)} KPI configurations from OrganizationMetricConfig")
    
    # Step 4: Load constraint set for the specified scenario + constraint_set_name
    scenario_stmt = (
        select(OptimizationScenario)
        .where(OptimizationScenario.name == scenario_name)
        .order_by(OptimizationScenario.id.desc())
        .limit(1)
    )
    scenario = db.scalars(scenario_stmt).first()
    
    if not scenario:
        logger.error(f"Scenario '{scenario_name}' not found")
        return {"populated_count": 0, "skipped_no_key": 0, "failed_count": 0, "error": "scenario_not_found"}
    
    constraint_set_stmt = (
        select(OptimizationConstraintSet)
        .where(
            OptimizationConstraintSet.scenario_id == scenario.id,
            OptimizationConstraintSet.name == constraint_set_name,
        )
        .order_by(OptimizationConstraintSet.id.desc())
        .limit(1)
    )
    constraint_set = db.scalars(constraint_set_stmt).first()
    
    if not constraint_set:
        logger.error(f"Constraint set '{constraint_set_name}' not found for scenario '{scenario_name}'")
        return {"populated_count": 0, "skipped_no_key": 0, "failed_count": 0, "error": "constraint_set_not_found"}
    
    logger.info(f"Loaded constraint set: {constraint_set.name} (id={constraint_set.id})")
    
    # Step 5: Parse constraints JSON with correct shapes
    mandatory_keys: Set[str] = set()
    bundle_map: Dict[str, str] = {}  # initiative_key -> bundle_key
    prerequisite_map: Dict[str, List[str]] = {}  # dependent_key -> [required_keys]
    exclusion_singles: Set[str] = set()
    exclusion_pairs_map: Dict[str, List[str]] = {}  # initiative_key -> [excluded_keys]
    synergy_map: Dict[str, List[str]] = {}  # initiative_key -> [synergy_partner_keys]
    
    # Mandatory: List[str]
    mandatory_json_val = constraint_set.mandatory_initiatives_json
    mandatory_list = mandatory_json_val if mandatory_json_val is not None else []
    if isinstance(mandatory_list, list):
        mandatory_keys = set(mandatory_list)
    
    # Bundles: List[{bundle_key, members}]
    bundles_json_val = constraint_set.bundles_json
    bundles_json = bundles_json_val if isinstance(bundles_json_val, list) else []
    for bundle in bundles_json:
        if isinstance(bundle, dict):
            bundle_key = bundle.get("bundle_key", "")
            members = bundle.get("members", [])
            if isinstance(members, list):
                for member in members:
                    bundle_map[str(member)] = str(bundle_key)
    
    # Prerequisites: Dict[str, List[str]] (dependent -> [required])
    prerequisites_json_val = constraint_set.prerequisites_json
    prerequisites_json = prerequisites_json_val if isinstance(prerequisites_json_val, dict) else {}
    for dependent_key, required_keys in prerequisites_json.items():
        if isinstance(required_keys, list):
            prerequisite_map[str(dependent_key)] = [str(k) for k in required_keys]
        else:
            prerequisite_map[str(dependent_key)] = [str(required_keys)]
    
    # Exclusions (singles): List[str]
    exclusions_initiatives_val = constraint_set.exclusions_initiatives_json
    exclusions_initiatives_json = exclusions_initiatives_val if exclusions_initiatives_val is not None else []
    if isinstance(exclusions_initiatives_json, list):
        exclusion_singles = set(str(k) for k in exclusions_initiatives_json)
    
    # Exclusions (pairs): List[List[str]] (e.g., [["INIT_A", "INIT_B"], ...])
    exclusions_pairs_val = constraint_set.exclusions_pairs_json
    exclusions_pairs_json = exclusions_pairs_val if isinstance(exclusions_pairs_val, list) else []
    for pair in exclusions_pairs_json:
        if isinstance(pair, list) and len(pair) == 2:
            key_a, key_b = str(pair[0]), str(pair[1])
            exclusion_pairs_map.setdefault(key_a, []).append(key_b)
            exclusion_pairs_map.setdefault(key_b, []).append(key_a)
    
    # Synergies: List[List[str]] (e.g., [["INIT_A", "INIT_B"], ...])
    synergies_json_val = getattr(constraint_set, "synergies_json", None)
    synergies_json = synergies_json_val if isinstance(synergies_json_val, list) else []
    for pair in synergies_json:
        if isinstance(pair, list) and len(pair) == 2:
            key_a, key_b = str(pair[0]), str(pair[1])
            synergy_map.setdefault(key_a, []).append(key_b)
            synergy_map.setdefault(key_b, []).append(key_a)
    
    logger.info(
        f"Parsed constraints: mandatory={len(mandatory_keys)}, bundles={len(bundle_map)}, "
        f"prerequisites={len(prerequisite_map)}, exclusion_singles={len(exclusion_singles)}, "
        f"exclusion_pairs={len(exclusion_pairs_map)}, synergies={len(synergy_map)}"
    )
    
    # Step 6: Build row data for batch update
    rows_to_write: List[Dict[str, Any]] = []
    populated_count = 0
    skipped_no_key = 0
    
    for initiative in initiatives:
        # Extract initiative_key as str (cast from Column)
        init_key_col = initiative.initiative_key
        init_key = str(init_key_col) if init_key_col is not None else None
        if not init_key:
            skipped_no_key += 1
            continue
        
        is_new = init_key not in existing_sheet_keys
        
        # Extract KPI contributions by properly querying OrganizationMetricConfig for kpi_level
        north_star_contrib = None
        strategic_kpi_contribs = {}
        
        kpi_json_val = initiative.kpi_contribution_json
        # SQLAlchemy JSON columns return dict or None
        kpi_json = kpi_json_val if isinstance(kpi_json_val, dict) else {}
        
        north_star_kpis = []
        strategic_kpis = []
        
        for kpi_key, contrib_val in kpi_json.items():
            kpi_level = kpi_level_map.get(kpi_key)
            
            if kpi_level == "north_star":
                north_star_kpis.append((kpi_key, contrib_val))
            elif kpi_level == "strategic":
                strategic_kpis.append((kpi_key, contrib_val))
            else:
                # KPI not found in config or has different level (immediate, unknown)
                logger.warning(
                    f"Initiative {init_key}: KPI {kpi_key} has level '{kpi_level}' (expected north_star or strategic)"
                )
        
        # Extract north_star contribution (should be exactly one)
        if len(north_star_kpis) == 1:
            north_star_contrib = north_star_kpis[0][1]
        elif len(north_star_kpis) > 1:
            logger.warning(
                f"Initiative {init_key}: Multiple north_star KPIs found: {[k for k, v in north_star_kpis]}. Using first."
            )
            north_star_contrib = north_star_kpis[0][1]
        else:
            logger.warning(f"Initiative {init_key}: No north_star KPI found in contributions")
        
        # Extract strategic KPI contributions
        for kpi_key, contrib_val in strategic_kpis:
            strategic_kpi_contribs[kpi_key] = contrib_val
        
        # Convert strategic KPIs to JSON string
        strategic_kpi_json_str = json.dumps(strategic_kpi_contribs) if strategic_kpi_contribs else ""
        
        # Constraint-derived fields
        is_mandatory_val = True if init_key in mandatory_keys else False
        bundle_key_val = bundle_map.get(init_key, "")
        prerequisite_keys_val = ", ".join(prerequisite_map.get(init_key, []))
        
        exclusion_keys_list = []
        if init_key in exclusion_singles:
            exclusion_keys_list.append(init_key)
        exclusion_keys_list.extend(exclusion_pairs_map.get(init_key, []))
        exclusion_keys_val = ", ".join(exclusion_keys_list) if exclusion_keys_list else ""
        
        synergy_partners = synergy_map.get(init_key, [])
        synergy_group_keys_val = ", ".join(synergy_partners) if synergy_partners else ""
        
        # Build row dict
        row_dict: Dict[str, Any] = {}
        
        # FORMULA COLUMNS - skip (PM formulas handle these)
        # initiative_key, title, country, department, immediate_kpi_key
        
        # PM INPUT COLUMNS - write only for NEW initiatives
        if is_new:
            eng_tokens_val = initiative.engineering_tokens
            row_dict["engineering_tokens"] = eng_tokens_val if eng_tokens_val is not None else ""
            deadline_val = initiative.deadline_date
            row_dict["deadline_date"] = deadline_val.isoformat() if deadline_val is not None else ""
            row_dict["category"] = initiative.category or ""
            row_dict["program_key"] = initiative.program_key or ""
        
        # DB-DERIVED COLUMNS - write always
        row_dict["north_star_contribution"] = north_star_contrib or ""
        row_dict["strategic_kpi_contributions"] = strategic_kpi_json_str
        
        # CONSTRAINT-DERIVED COLUMNS - write always
        row_dict["is_mandatory"] = is_mandatory_val
        row_dict["bundle_key"] = bundle_key_val
        row_dict["prerequisite_keys"] = prerequisite_keys_val
        row_dict["exclusion_keys"] = exclusion_keys_val
        row_dict["synergy_group_keys"] = synergy_group_keys_val
        
        # STATUS COLUMNS - write always
        row_dict["run_status"] = ""  # Cleared on populate (will be set by optimization run)
        row_dict["updated_source"] = token(Provenance.FLOW6_POPULATE_OPT_CANDIDATES)
        row_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Add initiative_key and row_number for batch write
        row_dict["_initiative_key"] = init_key
        row_dict["_row_number"] = existing_row_map.get(init_key, len(existing_sheet_rows) + 2 + populated_count)
        
        rows_to_write.append(row_dict)
        populated_count += 1
    
    # Step 7: Batch write to sheet
    if not rows_to_write:
        logger.warning("No rows to write to Candidates tab")
        return {"populated_count": 0, "skipped_no_key": skipped_no_key, "failed_count": 0}
    
    try:
        # Get header row ONCE to map column indices
        header_values = client.get_values(spreadsheet_id, f"{tab_name}!A1:Z1")
        header_row = header_values[0] if header_values else []
        
        if not header_row:
            logger.error("Could not read header row from Candidates tab")
            return {"populated_count": 0, "skipped_no_key": skipped_no_key, "failed_count": populated_count}
        
        # Build column index map (case-insensitive)
        col_index_map = {str(col).strip().lower().replace(" ", "_"): idx for idx, col in enumerate(header_row)}
        
        # Build batch update data: collect all updates as (range, values) pairs
        batch_data = []
        
        for row_dict in rows_to_write:
            init_key = row_dict.pop("_initiative_key")
            row_number = row_dict.pop("_row_number")
            
            # For each column to update, determine column letter and value
            for col_name, col_value in row_dict.items():
                col_name_normalized = col_name.lower().replace(" ", "_")
                col_idx = col_index_map.get(col_name_normalized)
                
                if col_idx is not None:
                    col_letter = _col_idx_to_letter(col_idx)
                    cell_range = f"{tab_name}!{col_letter}{row_number}"
                    batch_data.append((cell_range, [[col_value]]))
        
        # Execute batch update (sheets API allows batchUpdate with multiple ranges)
        if batch_data:
            # Optimize: group consecutive cells in same row into range updates
            # For simplicity now: use client.update_values per cell (can be optimized to batch API)
            for cell_range, values in batch_data:
                client.update_values(spreadsheet_id, cell_range, values)
        
        logger.info(f"Successfully populated {populated_count} candidates to sheet (batch writes: {len(batch_data)})")
        
    except Exception as e:
        logger.error(f"Failed to write candidates to sheet: {e}", exc_info=True)
        return {"populated_count": 0, "skipped_no_key": 0, "failed_count": populated_count}
    
    return {
        "populated_count": populated_count,
        "skipped_no_key": skipped_no_key,
        "failed_count": 0,
    }


def _col_idx_to_letter(idx: int) -> str:
    """Convert 0-based column index to A1 notation letter."""
    result = ""
    idx += 1  # Convert to 1-based
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result
