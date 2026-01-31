# productroadmap_sheet_project/app/services/optimization/optimization_compiler.py
"""Pure compilation logic for Optimization Center constraints.

This module contains zero I/O - no SheetsClient, no DB session management.
It only validates raw row dicts and produces ConstraintSetCompiled objects.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import TypeAdapter, ValidationError

from app.schemas.optimization_center import (
    BundleRowSchema,
    BundleCompiled,
    CapacityCap,
    CapacityCapRowSchema,
    CapacityFloor,
    CapacityFloorRowSchema,
    ConstraintRow,
    ConstraintSetCompiled,
    ExcludeInitiativeRowSchema,
    ExcludePairRowSchema,
    MandatoryRowSchema,
    RequirePrereqRowSchema,
    SynergyBonusRowSchema,
    TargetConstraint,
    TargetRowSchema,
    ValidationMessage,
    validate_constraint_row,
    validate_target_row,
)

logger = logging.getLogger(__name__)


_INIT_KEY_RE = re.compile(r"^\s*INIT[-_]?0*(\d+)\s*$", re.IGNORECASE)


def _normalize_initiative_key(key: str) -> str:
    """Normalize initiative key into canonical form `INIT-XXXX` where XXXX is zero-padded 4 digits.

    If the key doesn't match the expected pattern, return the stripped uppercased key unchanged.
    """
    if not key:
        return key
    s = str(key).strip()
    m = _INIT_KEY_RE.match(s)
    if m:
        try:
            n = int(m.group(1))
            return f"INIT-{n:04d}"
        except Exception:
            pass
    return s.upper()


def _normalize_key_list(keys: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for k in keys:
        nk = _normalize_initiative_key(k)
        if nk and nk not in seen:
            seen.add(nk)
            out.append(nk)
    return out

_CONSTRAINT_ADAPTER = TypeAdapter(ConstraintRow)
_TARGET_ADAPTER = TypeAdapter(TargetRowSchema)


def _bucket(compiled: Dict[Tuple[str, str], ConstraintSetCompiled], scenario: str, cset: str) -> ConstraintSetCompiled:
    key = (scenario.strip(), cset.strip())
    if key not in compiled:
        compiled[key] = ConstraintSetCompiled()
    return compiled[key]


def compile_constraint_sets(
    constraint_rows: List[Tuple[int, Dict[str, Any]]],
    target_rows: List[Tuple[int, Dict[str, Any]]],
    valid_kpis: Optional[set[str]] = None,
) -> Tuple[Dict[Tuple[str, str], ConstraintSetCompiled], List[ValidationMessage]]:
    """Validate and compile sheet rows into grouped ConstraintSetCompiled objects.

    Returns a tuple of (compiled_by_key, validation_messages).
    Rows with errors are skipped; warnings are preserved in the messages list.
    
    This is a pure function with no I/O dependencies.
    """

    messages: List[ValidationMessage] = []
    compiled: Dict[Tuple[str, str], ConstraintSetCompiled] = {}

    # Constraints first
    for row_num, raw in constraint_rows:
        msg = validate_constraint_row(row_num, raw)
        if msg.errors:
            logger.info("opt_compile.constraint_row_errors", extra={"row": row_num, "key": msg.key, "errors": msg.errors})
            messages.append(msg)
            continue
        if msg.warnings:
            logger.info(
                "opt_compile.constraint_row_warnings", extra={"row": row_num, "key": msg.key, "warnings": msg.warnings}
            )
            messages.append(msg)
        
        normalized = dict(raw)
        if "constraint_type" in normalized:
            normalized["constraint_type"] = str(normalized["constraint_type"]).strip().lower().replace(" ", "_")
        if "dimension" in normalized:
            normalized["dimension"] = str(normalized["dimension"]).strip().lower()
        if "dimension_key" in normalized and normalized.get("dimension_key") is not None:
            # Preserve case for free-text identifiers (bundles, bundle keys, etc.).
            # Only strip here; specific constraint handlers will normalize as appropriate.
            normalized["dimension_key"] = str(normalized["dimension_key"]).strip()
        
        try:
            parsed = _CONSTRAINT_ADAPTER.validate_python(normalized)
        except ValidationError as ve:
            logger.warning(
                "opt_compile.constraint_row_parse_failed",
                extra={"row": row_num, "key": msg.key, "errors": [err["msg"] for err in ve.errors()][:3]},
            )
            messages.append(
                ValidationMessage(
                    row_num=row_num,
                    key=msg.key,
                    errors=[err["msg"] for err in ve.errors()],
                    warnings=[],
                )
            )
            continue

        constraint_set = _bucket(compiled, str(parsed.scenario_name), str(parsed.constraint_set_name))

        if isinstance(parsed, CapacityFloorRowSchema):
            # Normalize capacity dimension_key to lowercase for consistent matching in solver
            dim_key = (parsed.dimension_key or "").strip().lower()
            constraint_set.capacity_floors.append(
                CapacityFloor(dimension=parsed.dimension, dimension_key=dim_key, min_tokens=cast(float, parsed.min_tokens))
            )
        elif isinstance(parsed, CapacityCapRowSchema):
            # Normalize capacity dimension_key to lowercase for consistent matching in solver
            dim_key = (parsed.dimension_key or "").strip().lower()
            constraint_set.capacity_caps.append(
                CapacityCap(dimension=parsed.dimension, dimension_key=dim_key, max_tokens=cast(float, parsed.max_tokens))
            )
        elif isinstance(parsed, MandatoryRowSchema):
            if parsed.dimension_key:
                constraint_set.mandatory_initiatives.append(_normalize_initiative_key(parsed.dimension_key))
        elif isinstance(parsed, BundleRowSchema):
            if parsed.dimension_key:
                members = [p.strip() for p in (parsed.bundle_member_keys or "").split("|") if p.strip()]
                members = _normalize_key_list(members)
                if members:
                    constraint_set.bundles.append(BundleCompiled(bundle_key=str(parsed.dimension_key), members=members))
        elif isinstance(parsed, ExcludePairRowSchema):
            parts = [p.strip() for p in (parsed.dimension_key or "").split("|") if p.strip()]
            if len(parts) >= 2:
                left = _normalize_initiative_key(parts[0])
                right = _normalize_initiative_key(parts[1])
                constraint_set.exclusions_pairs.append([left, right])
            else:
                logger.warning(
                    "opt_compile.exclude_pair_incomplete",
                    extra={"row": row_num, "key": msg.key, "raw": parsed.dimension_key},
                )
                messages.append(
                    ValidationMessage(
                        row_num=row_num,
                        key=msg.key,
                        errors=[],
                        warnings=["exclude_pair must contain two initiative keys separated by '|'"],
                    )
                )
        elif isinstance(parsed, ExcludeInitiativeRowSchema):
            if parsed.dimension_key:
                parts = [p.strip() for p in re.split(r"[|;,]", parsed.dimension_key) if p.strip()]
                parts = _normalize_key_list(parts)
                constraint_set.exclusions_initiatives.extend(parts)
        elif isinstance(parsed, RequirePrereqRowSchema):
            # dimension_key = dependent initiative, prereq_member_keys = pipe-separated prerequisites
            dependent = (parsed.dimension_key or "").strip()
            dependent = _normalize_initiative_key(dependent) if dependent else dependent
            prereq_keys = parsed.prereq_member_keys or ""
            prereqs = [p.strip() for p in prereq_keys.split("|") if p.strip()]
            prereqs = _normalize_key_list(prereqs)
            if dependent and prereqs:
                constraint_set.prerequisites[dependent] = prereqs
        elif isinstance(parsed, SynergyBonusRowSchema):
            parts = [p.strip() for p in (parsed.dimension_key or "").split("|") if p.strip()]
            parts = _normalize_key_list(parts)
            if len(parts) >= 2:
                constraint_set.synergy_bonuses.append(parts[:2])
        
        logger.debug(
            "opt_compile.constraint_appended",
            extra={
                "row": row_num,
                "scenario": parsed.scenario_name,
                "cset": parsed.constraint_set_name,
                "type": parsed.constraint_type,
            },
        )

    # Targets next
    for row_num, raw in target_rows:
        msg = validate_target_row(row_num, raw, valid_kpis=valid_kpis)
        if msg.errors:
            logger.info("opt_compile.target_row_errors", extra={"row": row_num, "key": msg.key, "errors": msg.errors})
            messages.append(msg)
            continue
        if msg.warnings:
            logger.info(
                "opt_compile.target_row_warnings", extra={"row": row_num, "key": msg.key, "warnings": msg.warnings}
            )
            messages.append(msg)
        
        normalized = dict(raw)
        if "dimension" in normalized and normalized.get("dimension") is not None:
            normalized["dimension"] = str(normalized["dimension"]).strip().lower()
        if "dimension_key" in normalized and normalized.get("dimension_key") is not None:
            normalized["dimension_key"] = str(normalized["dimension_key"]).strip().lower()
        if "kpi_key" in normalized and normalized.get("kpi_key") is not None:
            normalized["kpi_key"] = str(normalized["kpi_key"]).strip()
        
        try:
            parsed_target = _TARGET_ADAPTER.validate_python(normalized)
        except ValidationError as ve:
            logger.warning(
                "opt_compile.target_row_parse_failed",
                extra={"row": row_num, "key": msg.key, "errors": [err["msg"] for err in ve.errors()][:3]},
            )
            messages.append(
                ValidationMessage(
                    row_num=row_num,
                    key="|".join(
                        [
                            str(normalized.get("scenario_name", "")).strip(),
                            str(normalized.get("constraint_set_name", "")).strip(),
                            str(normalized.get("dimension_key", "")).strip(),
                            str(normalized.get("kpi_key", "")).strip(),
                        ]
                    ).strip("|"),
                    errors=[err["msg"] for err in ve.errors()],
                    warnings=[],
                )
            )
            continue

        constraint_set = _bucket(compiled, str(parsed_target.scenario_name), str(parsed_target.constraint_set_name))
        constraint_set.targets.append(
            TargetConstraint(
                dimension=parsed_target.dimension,
                dimension_key=str(parsed_target.dimension_key),
                kpi_key=parsed_target.kpi_key,
                floor_or_goal=cast(str, parsed_target.floor_or_goal),
                target_value=cast(float, parsed_target.target_value),
                notes=parsed_target.notes,
            )
        )
        logger.debug(
            "opt_compile.target_appended",
            extra={
                "row": row_num,
                "scenario": parsed_target.scenario_name,
                "cset": parsed_target.constraint_set_name,
                "dimension": parsed_target.dimension,
                "dimension_key": parsed_target.dimension_key,
            },
        )

    # Deduplicate lists before returning for cleaner JSON
    for constraint_set in compiled.values():
        if constraint_set.mandatory_initiatives:
            seen = set()
            deduped = []
            for init in constraint_set.mandatory_initiatives:
                if init not in seen:
                    seen.add(init)
                    deduped.append(init)
            constraint_set.mandatory_initiatives = deduped
        
        if constraint_set.exclusions_initiatives:
            seen = set()
            deduped = []
            for init in constraint_set.exclusions_initiatives:
                if init not in seen:
                    seen.add(init)
                    deduped.append(init)
            constraint_set.exclusions_initiatives = deduped
        
        if constraint_set.exclusions_pairs:
            seen = set()
            deduped = []
            for pair in constraint_set.exclusions_pairs:
                pair_tuple = tuple(pair)
                if pair_tuple not in seen:
                    seen.add(pair_tuple)
                    deduped.append(pair)
            constraint_set.exclusions_pairs = deduped
        
        if constraint_set.synergy_bonuses:
            seen = set()
            deduped = []
            for pair in constraint_set.synergy_bonuses:
                normalized_pair = tuple(sorted(pair))
                if normalized_pair not in seen:
                    seen.add(normalized_pair)
                    deduped.append(pair)
            constraint_set.synergy_bonuses = deduped

    return compiled, messages
