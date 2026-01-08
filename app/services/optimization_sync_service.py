#productroadmap_sheet_project/app/services/optimization_sync_service.py
"""Optimization Center sync orchestration.

This module reads from sheets, calls the pure compiler, and persists to DB.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy.orm import Session

from app.db.models.optimization import OrganizationMetricConfig, OptimizationConstraintSet, OptimizationScenario
from app.db.session import SessionLocal
from app.schemas.optimization_center import (
    CapacityCap,
    CapacityFloor,
    TargetConstraint,
    ValidationMessage,
)
from app.sheets.client import SheetsClient
from app.sheets.optimization_center_readers import ConstraintsReader, TargetsReader
from app.services.optimization_compiler import compile_constraint_sets

logger = logging.getLogger(__name__)


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
        return persisted, messages
    finally:
        if created_session:
            db.close()
