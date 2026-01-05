# productroadmap_sheet_project/app/schemas/optimization_center.py
"""Pydantic schemas + validation helpers for Optimization Center sheets.

This module formalizes:
- Row-level shapes for constraints, targets, scenarios (sheet -> schema).
- Column-to-field maps for Constraints, Targets, Scenario_Config tabs.
- Validation helpers that produce structured row feedback (errors/warnings).

No sheet or DB I/O lives here; sync services can import these helpers.
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator, model_validator
from typing_extensions import Literal


# Column -> schema field mappings (sheet columns may be aliases; readers resolve to these)
CONSTRAINTS_SHEET_FIELD_MAP: Dict[str, str] = {
    "scenario_name": "scenario_name",
    "constraint_set_name": "constraint_set_name",
    "constraint_type": "constraint_type",
    "dimension": "dimension",
    "key": "key",
    "min_tokens": "min_tokens",
    "max_tokens": "max_tokens",
    "target_kpi_key": "target_kpi_key",
    "target_value": "target_value",
    "notes": "notes",
}

TARGETS_SHEET_FIELD_MAP: Dict[str, str] = {
    "scenario_name": "scenario_name",
    "constraint_set_name": "constraint_set_name",
    "country": "country",  # header aliases: country|market
    "kpi_key": "kpi_key",
    "target_value": "target_value",
    "floor_or_goal": "floor_or_goal",
    "notes": "notes",
}

SCENARIO_CONFIG_FIELD_MAP: Dict[str, str] = {
    "scenario_name": "name",
    "period_key": "period_key",
    "capacity_total_tokens": "capacity_total_tokens",
    "objective_mode": "objective_mode",
    "objective_weights_json": "objective_weights_json",
    "notes": "notes",
}


class ValidationMessage(BaseModel):
    row_num: int
    key: str
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ScenarioConfigSchema(BaseModel):
    name: str
    period_key: Optional[str] = None
    capacity_total_tokens: Optional[float] = None
    objective_mode: Optional[str] = None
    objective_weights_json: Optional[dict] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("capacity_total_tokens", mode="before")
    @classmethod
    def to_float(cls, v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"invalid number: {v}") from e

    @field_validator("objective_weights_json")
    @classmethod
    def validate_weights(cls, v):
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("objective_weights_json must be a JSON object")
        cleaned: Dict[str, float] = {}
        for k, val in v.items():
            try:
                fval = float(val)
            except Exception as e:  # noqa: BLE001
                raise ValueError("objective_weights_json values must be numbers") from e
            if fval < 0:
                raise ValueError("objective_weights_json values must be >= 0")
            cleaned[str(k)] = fval
        return cleaned


class ConstraintRowBase(BaseModel):
    scenario_name: str
    constraint_set_name: str
    constraint_type: str
    dimension: str
    key: Optional[str] = None
    min_tokens: Optional[float] = None
    max_tokens: Optional[float] = None
    target_kpi_key: Optional[str] = None
    target_value: Optional[float] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("constraint_type", "dimension", "scenario_name", "constraint_set_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if v is None or str(v).strip() == "":
            raise ValueError("must not be blank")
        return str(v).strip()

    @field_validator("min_tokens", "max_tokens", "target_value", mode="before")
    @classmethod
    def to_float(cls, v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"invalid number: {v}") from e

    @field_validator("constraint_type")
    @classmethod
    def normalize_type(cls, v: str) -> str:
        return str(v).strip().lower()

    @field_validator("dimension")
    @classmethod
    def normalize_dimension(cls, v: str) -> str:
        return str(v).strip().lower()

    @field_validator("key")
    @classmethod
    def normalize_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        sv = str(v).strip()
        return sv if sv else None


class CapacityFloorRowSchema(ConstraintRowBase):
    constraint_type: Literal["capacity_floor"]

    @model_validator(mode="after")
    def validate_capacity_floor(self):
        if self.min_tokens is None and self.max_tokens is None:
            raise ValueError("capacity_floor requires min_tokens or max_tokens")
        return self


class CapacityCapRowSchema(ConstraintRowBase):
    constraint_type: Literal["capacity_cap"]

    @model_validator(mode="after")
    def validate_capacity_cap(self):
        if self.max_tokens is None and self.min_tokens is None:
            raise ValueError("capacity_cap requires max_tokens or min_tokens")
        return self


class MandatoryRowSchema(ConstraintRowBase):
    constraint_type: Literal["mandatory"]

    @model_validator(mode="after")
    def validate_mandatory(self):
        if not self.key:
            raise ValueError("mandatory constraint requires key (initiative)")
        return self


class BundleRowSchema(ConstraintRowBase):
    constraint_type: Literal["bundle_all_or_nothing"]

    @model_validator(mode="after")
    def validate_bundle(self):
        if not self.key:
            raise ValueError("bundle_all_or_nothing requires bundle key")
        return self


class ExcludeRowSchema(ConstraintRowBase):
    constraint_type: Literal["exclude"]

    @model_validator(mode="after")
    def validate_exclude(self):
        if not self.key:
            raise ValueError("exclude requires key")
        return self


class RequirePrereqRowSchema(ConstraintRowBase):
    constraint_type: Literal["require_prereq"]

    @model_validator(mode="after")
    def validate_prereq(self):
        if not self.key:
            raise ValueError("require_prereq requires key encoding dependency")
        return self


class TargetConstraintRowSchema(ConstraintRowBase):
    constraint_type: Literal["target"]

    @model_validator(mode="after")
    def validate_target_constraint(self):
        if not self.target_kpi_key or self.target_value is None:
            raise ValueError("target constraint requires target_kpi_key and target_value")
        return self


ConstraintRow = Annotated[
    Union[
        CapacityFloorRowSchema,
        CapacityCapRowSchema,
        MandatoryRowSchema,
        BundleRowSchema,
        ExcludeRowSchema,
        RequirePrereqRowSchema,
        TargetConstraintRowSchema,
    ],
    Field(discriminator="constraint_type"),
]

# Backwards compatibility for earlier imports
ConstraintRowSchema = ConstraintRow


_CONSTRAINT_ROW_ADAPTER = TypeAdapter(ConstraintRow)


class TargetRowSchema(BaseModel):
    scenario_name: str
    constraint_set_name: str
    country: str
    kpi_key: str
    target_value: Optional[float] = None
    floor_or_goal: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("scenario_name", "constraint_set_name", "country", "kpi_key")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if v is None or str(v).strip() == "":
            raise ValueError("must not be blank")
        return str(v).strip()

    @field_validator("target_value", mode="before")
    @classmethod
    def to_float(cls, v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"invalid number: {v}") from e

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str) -> str:
        return str(v).strip().lower()

    @field_validator("floor_or_goal")
    @classmethod
    def validate_floor_goal(cls, v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        val = str(v).strip().lower()
        if val not in {"floor", "goal"}:
            raise ValueError("floor_or_goal must be 'floor' or 'goal'")
        return val


class ConstraintSetCompiled(BaseModel):
    """Compiled, system-generated representation of a constraint set (not a sheet row)."""

    capacity_floors: List["CapacityFloor"] = Field(default_factory=list)
    capacity_caps: List["CapacityCap"] = Field(default_factory=list)
    targets: List["TargetConstraint"] = Field(default_factory=list)
    mandatory_initiatives: List[str] = Field(default_factory=list)
    bundles: List[List[str]] = Field(default_factory=list)
    exclusions: List[List[str]] = Field(default_factory=list)
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class CapacityFloor(BaseModel):
    dimension: str
    key: str
    min_tokens: float

    model_config = {"extra": "ignore"}


class CapacityCap(BaseModel):
    dimension: str
    key: str
    max_tokens: float

    model_config = {"extra": "ignore"}


class TargetConstraint(BaseModel):
    dimension: str
    key: str
    kpi_key: str
    floor_or_goal: str
    target_value: float
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


def validate_constraint_row(row_num: int, data: dict) -> ValidationMessage:
    errors: List[str] = []
    warnings: List[str] = []
    key = "|".join([
        str(data.get("scenario_name", "")).strip(),
        str(data.get("constraint_set_name", "")).strip(),
        str(data.get("constraint_type", "")).strip(),
        str(data.get("dimension", "")).strip(),
        str(data.get("key", "")).strip(),
    ]).strip("|")
    try:
        # Discriminated union enforces type-specific rules
        _CONSTRAINT_ROW_ADAPTER.validate_python(data)
    except ValidationError as ve:
        errors = [err['msg'] for err in ve.errors()]
    # Additional semantic check: min <= max when both present
    try:
        min_v = float(data["min_tokens"]) if data.get("min_tokens") not in (None, "") else None
        max_v = float(data["max_tokens"]) if data.get("max_tokens") not in (None, "") else None
        if min_v is not None and max_v is not None and min_v > max_v:
            errors.append("min_tokens cannot exceed max_tokens")
    except Exception:
        # numeric errors already captured
        pass
    return ValidationMessage(row_num=row_num, key=key, errors=errors, warnings=warnings)


def validate_target_row(row_num: int, data: dict, valid_kpis: Optional[set[str]] = None) -> ValidationMessage:
    errors: List[str] = []
    warnings: List[str] = []
    key = "|".join([
        str(data.get("scenario_name", "")).strip(),
        str(data.get("constraint_set_name", "")).strip(),
        str(data.get("country", "")).strip(),
        str(data.get("kpi_key", "")).strip(),
    ]).strip("|")
    try:
        TargetRowSchema(**data)
    except ValidationError as ve:
        errors = [err['msg'] for err in ve.errors()]
    if valid_kpis is not None:
        kpi = str(data.get("kpi_key", "")).strip()
        if kpi and kpi not in valid_kpis:
            errors.append("kpi_key not found in Metrics_Config")
    return ValidationMessage(row_num=row_num, key=key, errors=errors, warnings=warnings)


def validate_scenario_config(row_num: int, data: dict, allowed_objective_modes: Optional[set[str]] = None, weights_required_modes: Optional[set[str]] = None) -> ValidationMessage:
    errors: List[str] = []
    warnings: List[str] = []
    key = str(data.get("name", "")).strip()
    try:
        ScenarioConfigSchema(**data)
    except ValidationError as ve:
        errors = [err['msg'] for err in ve.errors()]
    if allowed_objective_modes is not None:
        mode = str(data.get("objective_mode", "")).strip()
        if mode and mode not in allowed_objective_modes:
            errors.append("objective_mode is not in allowed set")
        if weights_required_modes and mode in weights_required_modes:
            if data.get("objective_weights_json") in (None, {}, "", []):
                errors.append("objective_weights_json is required for this objective_mode")
    return ValidationMessage(row_num=row_num, key=key, errors=errors, warnings=warnings)


__all__ = [
    "CONSTRAINTS_SHEET_FIELD_MAP",
    "TARGETS_SHEET_FIELD_MAP",
    "SCENARIO_CONFIG_FIELD_MAP",
    "ValidationMessage",
    "ScenarioConfigSchema",
    "ConstraintRow",
    "ConstraintRowSchema",
    "TargetRowSchema",
    "CapacityFloor",
    "CapacityCap",
    "TargetConstraint",
    "ConstraintSetCompiled",
    "validate_constraint_row",
    "validate_target_row",
    "validate_scenario_config",
]
