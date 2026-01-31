#productroadmap_sheet_project/app/services/optimization_sync_service.py
"""Optimization Center sync orchestration.

This module reads from sheets, calls the pure compiler, and persists to DB.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.db.models.optimization import (
    OrganizationMetricConfig,
    OptimizationConstraintSet,
    OptimizationScenario,
    OptimizationRun,
    Portfolio,
)
from app.db.session import SessionLocal
from app.schemas.optimization_center import (
    CapacityCap,
    CapacityFloor,
    TargetConstraint,
    ValidationMessage,
)
from app.sheets.client import SheetsClient
from app.sheets.optimization_center_readers import CandidatesReader, ConstraintsReader, ScenarioConfigReader, TargetsReader
from app.services.optimization.optimization_compiler import compile_constraint_sets
from app.utils.provenance import Provenance, token

logger = logging.getLogger(__name__)


def sync_scenarios_from_sheet(
    sheets_client: SheetsClient,
    spreadsheet_id: str,
    scenario_config_tab: str,
    session: Optional[Session] = None,
) -> Tuple[List[OptimizationScenario], List[str]]:
    """Read Scenario_Config tab and upsert OptimizationScenario rows.
    
    Args:
        sheets_client: Sheets API client
        spreadsheet_id: Optimization Center spreadsheet ID
        scenario_config_tab: Tab name (e.g., "Scenario_Config")
        session: Optional DB session (creates new if None)
    
    Returns:
        Tuple of (synced_scenarios, errors)
    """
    db: Session = session or SessionLocal()
    created_session = session is None
    
    try:
        reader = ScenarioConfigReader(sheets_client)
        rows = reader.get_rows(spreadsheet_id, scenario_config_tab)
        logger.info("opt_sync.scenarios_loaded", extra={"count": len(rows)})
        
        synced: List[OptimizationScenario] = []
        errors: List[str] = []
        
        for row_num, scenario_row in rows:
            if not scenario_row.scenario_name or not str(scenario_row.scenario_name).strip():
                errors.append(f"Row {row_num}: Missing scenario_name")
                continue
            
            scenario_name = str(scenario_row.scenario_name).strip()
            
            try:
                # Check if scenario exists
                existing = db.query(OptimizationScenario).filter(
                    OptimizationScenario.name == scenario_name
                ).first()
                
                if existing:
                    # Update existing scenario
                    setattr(existing, "period_key", scenario_row.period_key)
                    setattr(existing, "capacity_total_tokens", scenario_row.capacity_total_tokens)
                    setattr(existing, "objective_mode", scenario_row.objective_mode)
                    setattr(existing, "objective_weights_json", scenario_row.objective_weights_json)
                    logger.info(
                        "opt_sync.scenario_updated",
                        extra={"scenario": scenario_name, "id": existing.id}
                    )
                    synced.append(existing)
                else:
                    # Create new scenario
                    new_scenario = OptimizationScenario(
                        name=scenario_name,
                        period_key=scenario_row.period_key,
                        capacity_total_tokens=scenario_row.capacity_total_tokens,
                        objective_mode=scenario_row.objective_mode,
                        objective_weights_json=scenario_row.objective_weights_json,
                    )
                    db.add(new_scenario)
                    db.flush()  # Get the ID
                    logger.info(
                        "opt_sync.scenario_created",
                        extra={"scenario": scenario_name, "id": new_scenario.id}
                    )
                    synced.append(new_scenario)
            
            except Exception as e:
                logger.exception("opt_sync.scenario_sync_failed")
                errors.append(f"Row {row_num} ({scenario_name}): {str(e)[:100]}")
                continue
        

        if synced:
            db.commit()
        # Mirror behavior: remove any DB scenarios for which there is no sheet row
        # SAFETY: Only perform mirroring when sheet read returned rows; skip if empty to avoid accidental mass-deletes.
        if not rows:
            logger.warning(
                "opt_sync.scenario_mirror_skipped_empty_sheet",
                extra={"reason": "no rows read from sheet; skipping mirror deletions"},
            )
            return synced, errors
        # Build set of scenario names from the sheet
        sheet_names = {str(r[1].scenario_name).strip() for r in rows if r[1].scenario_name}
        # Find DB scenarios not present on sheet and delete only if safe
        db_scenarios = db.query(OptimizationScenario).all()
        to_delete: list[OptimizationScenario] = []
        for s in db_scenarios:
            if s.name not in sheet_names:
                runs_count = db.query(OptimizationRun).filter(OptimizationRun.scenario_id == s.id).count()
                # Count portfolios referencing this scenario via their runs (safer than assuming Portfolio.scenario_id exists)
                portfolios_count = (
                    db.query(Portfolio)
                    .join(OptimizationRun, Portfolio.optimization_run_id == OptimizationRun.id)
                    .filter(OptimizationRun.scenario_id == s.id)
                    .count()
                )
                if runs_count == 0 and portfolios_count == 0:
                    to_delete.append(s)
                else:
                    logger.warning(
                        "opt_sync.scenario_skip_delete_has_dependents",
                        extra={"scenario": s.name, "runs": runs_count, "portfolios": portfolios_count},
                    )

        if to_delete:
            for s in to_delete:
                logger.info("opt_sync.scenario_deleting", extra={"scenario": s.name, "id": s.id})
                db.delete(s)
            db.commit()

        logger.info(
            "opt_sync.scenarios_complete",
            extra={"synced": len(synced), "errors": len(errors)}
        )

        return synced, errors
    
    finally:
        if created_session:
            db.close()


def _capacity_to_json(items: Sequence[CapacityFloor | CapacityCap], value_attr: str) -> Dict[str, Dict[str, float]]:
    data: Dict[str, Dict[str, float]] = {}
    for item in items:
        val = getattr(item, value_attr, None)
        if val is None:
            continue
        dimension = str(item.dimension)
        dimension_key = str(item.dimension_key)
        data.setdefault(dimension, {})[dimension_key] = float(val)
    return data


def _targets_to_json(targets: List[TargetConstraint]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Convert targets to JSON structure: {dimension: {dimension_key: {kpi_key: {type, value, notes?}}}}"""
    data: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for tgt in targets:
        dimension = str(tgt.dimension)
        dimension_key = str(tgt.dimension_key)
        kpi = str(tgt.kpi_key)
        data.setdefault(dimension, {}).setdefault(dimension_key, {})[kpi] = {
            "type": tgt.floor_or_goal,
            "value": tgt.target_value
        }
        if tgt.notes:
            data[dimension][dimension_key][kpi]["notes"] = tgt.notes
    return data


def sync_constraint_sets_from_sheets(
    sheets_client: SheetsClient,
    spreadsheet_id: str,
    constraints_tab: str,
    targets_tab: str,
    session: Optional[Session] = None,
) -> Tuple[List[OptimizationConstraintSet], List[ValidationMessage]]:
    """Read constraints/targets tabs, compile, and upsert OptimizationConstraintSet rows."""

    constraints_reader = ConstraintsReader(sheets_client)
    targets_reader = TargetsReader(sheets_client)
    constraint_rows = [(row_num, row.model_dump()) for row_num, row in constraints_reader.get_rows(spreadsheet_id, constraints_tab)]
    target_rows = [(row_num, row.model_dump()) for row_num, row in targets_reader.get_rows(spreadsheet_id, targets_tab)]
    logger.info(
        "opt_sync.rows_loaded", extra={"constraints": len(constraint_rows), "targets": len(target_rows)}
    )

    db: Session = session or SessionLocal()
    created_session = session is None

    try:
        valid_kpi_keys: Optional[set[str]] = None
        try:
            valid_kpi_keys = {row[0] for row in db.query(OrganizationMetricConfig.kpi_key).all()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("opt_sync.kpi_lookup_failed", extra={"error": str(exc)[:200]})

        compiled, messages = compile_constraint_sets(constraint_rows, target_rows, valid_kpis=valid_kpi_keys)

        persisted: List[OptimizationConstraintSet] = []
        for (scenario_name, constraint_set_name), compiled_set in compiled.items():
            scenario = (
                db.query(OptimizationScenario)
                .filter(OptimizationScenario.name == str(scenario_name).strip())
                .first()
            )
            if not scenario:
                logger.warning(
                    "opt_sync.missing_scenario",
                    extra={"scenario": scenario_name, "cset": constraint_set_name},
                )
                messages.append(
                    ValidationMessage(
                        row_num=0,
                        key=f"{scenario_name}|{constraint_set_name}",
                        errors=[f"Scenario not found: {scenario_name}"],
                        warnings=[],
                    )
                )
                continue

            existing = (
                db.query(OptimizationConstraintSet)
                .filter(
                    OptimizationConstraintSet.scenario_id == scenario.id,
                    OptimizationConstraintSet.name == str(constraint_set_name).strip(),
                )
                .first()
            )
            if existing is None:
                existing = OptimizationConstraintSet(
                    scenario_id=scenario.id,
                    name=str(constraint_set_name).strip(),
                )
                db.add(existing)

            existing_obj = cast(Any, existing)
            existing_obj.floors_json = _capacity_to_json(compiled_set.capacity_floors, "min_tokens") or None
            existing_obj.caps_json = _capacity_to_json(compiled_set.capacity_caps, "max_tokens") or None
            existing_obj.targets_json = _targets_to_json(compiled_set.targets) or None
            existing_obj.mandatory_initiatives_json = compiled_set.mandatory_initiatives or None
            existing_obj.bundles_json = [b.model_dump() for b in compiled_set.bundles] or None
            existing_obj.exclusions_initiatives_json = compiled_set.exclusions_initiatives or None
            existing_obj.exclusions_pairs_json = compiled_set.exclusions_pairs or None
            existing_obj.prerequisites_json = compiled_set.prerequisites or None
            existing_obj.synergy_bonuses_json = compiled_set.synergy_bonuses or None
            existing_obj.notes = compiled_set.notes

            persisted.append(existing)
            logger.info(
                "opt_sync.constraint_set_upserted",
                extra={"scenario": scenario.name, "cset": existing.name},
            )

        if persisted:
            db.commit()

        # Mirror constraint sets: remove any DB OptimizationConstraintSet rows
        # that are not present in the compiled sheet output for their scenario.
        # SAFETY: Only perform mirroring when compile produced results; skip if compiled is empty to avoid accidental mass-deletes.
        if not compiled:
            logger.warning(
                "opt_sync.constraint_set_mirror_skipped_empty_compile",
                extra={"reason": "compiled constraint sets empty; skipping mirror deletions"},
            )
            return persisted, messages
        # Build mapping: scenario_name -> set(constraint_set_names)
        compiled_by_scenario: Dict[str, set[str]] = {}
        for (sc_name, cs_name) in compiled.keys():
            compiled_by_scenario.setdefault(str(sc_name).strip(), set()).add(str(cs_name).strip())

        # For each scenario in DB, delete constraint sets not present in compiled_by_scenario
        db_scenarios = db.query(OptimizationScenario).all()
        deleted_any = False
        for sc in db_scenarios:
            allowed = compiled_by_scenario.get(str(sc.name).strip(), set())
            existing_sets = db.query(OptimizationConstraintSet).filter(OptimizationConstraintSet.scenario_id == sc.id).all()
            for es in existing_sets:
                if es.name not in allowed:
                    # Check dependent OptimizationRun referencing this constraint set
                    runs_count = db.query(OptimizationRun).filter(OptimizationRun.constraint_set_id == es.id).count()
                    # Also check for any persisted Portfolio that references a run tied to this constraint set
                    portfolios_count = (
                        db.query(Portfolio)
                        .join(OptimizationRun, Portfolio.optimization_run_id == OptimizationRun.id)
                        .filter(OptimizationRun.constraint_set_id == es.id)
                        .count()
                    )

                    if runs_count > 0 or portfolios_count > 0:
                        logger.warning(
                            "opt_sync.constraint_set_skip_delete_has_dependents",
                            extra={
                                "scenario": sc.name,
                                "cset": es.name,
                                "id": es.id,
                                "runs": runs_count,
                                "portfolios": portfolios_count,
                            },
                        )
                        continue

                    logger.info(
                        "opt_sync.constraint_set_deleting",
                        extra={"scenario": sc.name, "cset": es.name, "id": es.id},
                    )
                    db.delete(es)
                    deleted_any = True

        if deleted_any:
            db.commit()

        return persisted, messages
    finally:
        if created_session:
            db.close()


def sync_candidates_from_sheet(
    sheets_client: SheetsClient,
    spreadsheet_id: str,
    candidates_tab: str,
    initiative_keys: Optional[List[str]] = None,
    commit_every: int = 50,
    session: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Sync Optimization Candidates tab editable fields to Initiative DB records.
    
    Persists only DB-backed fields that PM can edit in Candidates tab:
    - engineering_tokens
    - deadline_date
    - category
    - program_key
    
    Sheet-only fields NOT persisted:
    - is_selected_for_run (ephemeral selection state)
    - notes (sheet-only commentary)
    
    Args:
        sheets_client: Sheets API client
        spreadsheet_id: Spreadsheet ID
        candidates_tab: Tab name (e.g., "Optimization Center - Candidates")
        initiative_keys: Optional filter for specific initiative keys
        commit_every: Batch commit interval
        session: Optional DB session (creates new if None)
    
    Returns:
        {
            "row_count": 10,
            "updated": 8,
            "skipped_no_key": 2,
            "errors": [],
        }
    """
    db: Session = session or SessionLocal()
    created_session = session is None
    
    try:
        reader = CandidatesReader(sheets_client)
        rows = reader.get_rows(spreadsheet_id, candidates_tab)
        original_row_count = len(rows)
        logger.info("opt_candidates_sync.rows_loaded", extra={"count": len(rows)})
        
        updated_count = 0
        skipped_no_key = 0
        errors: List[str] = []
        commit_counter = 0
        
        # Filter by scope if provided
        if initiative_keys:
            keys_set = {k.strip().lower() for k in initiative_keys if isinstance(k, str) and k.strip()}
            rows = [(row_num, row) for row_num, row in rows if row.initiative_key and row.initiative_key.lower() in keys_set]
            logger.info("opt_candidates_sync.filtered_by_scope", extra={"filtered_count": len(rows)})
        
        for row_num, row in rows:
            if not row.initiative_key or not str(row.initiative_key).strip():
                skipped_no_key += 1
                continue
            
            initiative_key = str(row.initiative_key).strip()
            
            try:
                initiative = (
                    db.query(Initiative)
                    .filter(Initiative.initiative_key == initiative_key)
                    .first()
                )
                
                if not initiative:
                    logger.warning(
                        "opt_candidates_sync.initiative_not_found",
                        extra={"key": initiative_key, "row": row_num},
                    )
                    errors.append(f"Row {row_num}: Initiative not found: {initiative_key}")
                    continue
                
                # Update DB-backed fields only
                if row.engineering_tokens is not None:
                    setattr(initiative, "engineering_tokens", float(row.engineering_tokens))
                
                if row.deadline_date is not None:
                    # Parse date with a forgiving strategy: try ISO, common formats, then dateutil if available
                    from datetime import datetime, date

                    def _parse_date_flexible(val) -> Optional[date]:
                        if isinstance(val, date):
                            return val
                        if not isinstance(val, str):
                            return None
                        s = val.strip()
                        # Try iso format first
                        try:
                            return datetime.fromisoformat(s).date()
                        except Exception:
                            pass
                        # Try common separators
                        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                            try:
                                return datetime.strptime(s, fmt).date()
                            except Exception:
                                pass
                        # Fallback to dateutil if available
                        try:
                            from dateutil import parser as _parser

                            return _parser.parse(s).date()
                        except Exception:
                            return None

                    parsed_date = _parse_date_flexible(row.deadline_date)
                    if parsed_date:
                        setattr(initiative, "deadline_date", parsed_date)
                    else:
                        logger.warning(
                            "opt_candidates_sync.invalid_date",
                            extra={"key": initiative_key, "date": row.deadline_date},
                        )
                
                if row.category is not None:
                    setattr(initiative, "category", str(row.category).strip() if row.category else None)
                
                if row.program_key is not None:
                    setattr(initiative, "program_key", str(row.program_key).strip() if row.program_key else None)
                
                # Set update source (use provenance token)
                setattr(initiative, "updated_source", token(Provenance.FLOW6_SYNC_OPT_CANDIDATES))
                
                updated_count += 1
                commit_counter += 1
                
                if commit_counter >= commit_every:
                    db.commit()
                    commit_counter = 0
                    logger.info(
                        "opt_candidates_sync.batch_committed",
                        extra={"updated_so_far": updated_count},
                    )
                
            except Exception as e:
                logger.exception("opt_candidates_sync.row_failed")
                errors.append(f"Row {row_num} ({initiative_key}): {str(e)[:100]}")
                continue
        
        # Final commit
        if commit_counter > 0:
            db.commit()
        
        logger.info(
            "opt_candidates_sync.complete",
            extra={
                "updated": updated_count,
                "skipped_no_key": skipped_no_key,
                "errors": len(errors),
            },
        )
        
        return {
            "original_row_count": original_row_count,
            "processed_row_count": len(rows),
            "updated": updated_count,
            "skipped_no_key": skipped_no_key,
            "errors": errors,
        }
    
    finally:
        if created_session:
            db.close()
