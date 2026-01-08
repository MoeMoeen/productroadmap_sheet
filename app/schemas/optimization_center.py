# productroadmap_sheet_project/app/schemas/optimization_center.py
"""Pydantic schemas + validation helpers for Optimization Center sheets.

This module formalizes:
- Row-level shapes for constraints, targets, scenarios (sheet -> schema).
- Column-to-field maps for Constraints, Targets, Scenario_Config tabs.
- Validation helpers that produce structured row feedback (errors/warnings).

No sheet or DB I/O lives here; sync services can import these helpers.
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator, model_validator
from typing_extensions import Literal


# Column -> schema field mappings (sheet columns may be aliases; readers resolve to these)
CONSTRAINTS_SHEET_FIELD_MAP: Dict[str, str] = {
    "scenario_name": "scenario_name",
    "constraint_set_name": "constraint_set_name",
    "constraint_type": "constraint_type",
    "dimension": "dimension",
    "dimension_key": "dimension_key",
    "min_tokens": "min_tokens",
    "max_tokens": "max_tokens",
    "bundle_member_keys": "bundle_member_keys",
    "notes": "notes",
}

TARGETS_SHEET_FIELD_MAP: Dict[str, str] = {
    "scenario_name": "scenario_name",
    "constraint_set_name": "constraint_set_name",
    "dimension": "dimension",
    "dimension_key": "dimension_key",  # country, product, segment, or composite key
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
        total = sum(cleaned.values())
        if total == 0:
            raise ValueError("objective_weights_json must not sum to zero")
        return cleaned


class ConstraintRowBase(BaseModel):
    scenario_name: str
    constraint_set_name: str
    constraint_type: "ConstraintType | str"
    dimension: "Dimension"
    dimension_key: Optional[str] = None
    min_tokens: Optional[float] = None
    max_tokens: Optional[float] = None
    bundle_member_keys: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("constraint_type", "dimension", "scenario_name", "constraint_set_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if v is None or str(v).strip() == "":
            raise ValueError("must not be blank")
        return str(v).strip()

    @field_validator("min_tokens", "max_tokens", mode="before")
    @classmethod
    def to_float(cls, v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"invalid number: {v}") from e

    @field_validator("min_tokens", "max_tokens")
    @classmethod
    def non_negative(cls, v):
        if v is None:
            return None
        if v < 0:
            raise ValueError("value must be >= 0")
        return v

    @field_validator("constraint_type", mode="before")
    @classmethod
    def normalize_type(cls, v: str) -> str:
        return str(v).strip().lower()

    @field_validator("dimension", mode="before")
    @classmethod
    def normalize_dimension(cls, v: str) -> str:
        return str(v).strip().lower()

    @field_validator("constraint_set_name", mode="before")
    @classmethod
    def normalize_constraint_set(cls, v: str) -> str:
        return str(v).strip()

    @field_validator("dimension_key")
    @classmethod
    def normalize_dimension_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        sv = str(v).strip()
        return sv if sv else None

    @model_validator(mode="after")
    def forbid_bundle_members_for_non_bundle(self):
        if self.bundle_member_keys and str(self.constraint_type).strip() != "bundle_all_or_nothing":
            raise ValueError("bundle_member_keys is only valid for bundle_all_or_nothing")
        return self


ConstraintType = Literal[
    "capacity_floor",
    "capacity_cap",
    "mandatory",
    "bundle_all_or_nothing",
    "exclude_pair",
    "exclude_initiative",
    "require_prereq",
    "synergy_bonus",
]

# Capacity-relevant dimensions only (for capacity_floor, capacity_cap)
CapacityDimension = Literal[
    "all",
    "country",
    "region",
    "segment",
    "product",
    "category",
    "program",
    "department",
]

# All constraint dimensions (includes initiative, bundle for other constraint types)
Dimension = Literal[
    "initiative",
    "country",
    "segment",
    "region",
    "product",
    "bundle",
    "program",
    "category",
    "department",
    "all",
]

class CapacityFloorRowSchema(ConstraintRowBase):
    constraint_type: Literal["capacity_floor"]
    dimension: CapacityDimension

    @model_validator(mode="after")
    def validate_capacity_floor(self):
        if self.min_tokens is None:
            raise ValueError("capacity_floor requires min_tokens")
        if self.dimension == "all":
            self.dimension_key = self.dimension_key or "all"
        elif not self.dimension_key:
            raise ValueError("capacity_floor requires dimension_key for dimension")
        # max_tokens allowed but optional; no extra semantics
        return self


class CapacityCapRowSchema(ConstraintRowBase):
    constraint_type: Literal["capacity_cap"]
    dimension: CapacityDimension

    @model_validator(mode="after")
    def validate_capacity_cap(self):
        if self.max_tokens is None:
            raise ValueError("capacity_cap requires max_tokens")
        if self.dimension == "all":
            self.dimension_key = self.dimension_key or "all"
        elif not self.dimension_key:
            raise ValueError("capacity_cap requires dimension_key for dimension")
        # min_tokens allowed but optional; no extra semantics
        return self


class MandatoryRowSchema(ConstraintRowBase):
    constraint_type: Literal["mandatory"]
    dimension: Literal["initiative"]

    @model_validator(mode="after")
    def validate_mandatory(self):
        if not self.dimension_key:
            raise ValueError("mandatory constraint requires dimension_key (initiative)")
        return self


class BundleRowSchema(ConstraintRowBase):
    constraint_type: Literal["bundle_all_or_nothing"]
    dimension: Literal["bundle"]

    @model_validator(mode="after")
    def validate_bundle(self):
        if not self.dimension_key:
            raise ValueError("bundle_all_or_nothing requires bundle dimension_key")
        member_source = self.bundle_member_keys or ""
        members = [part.strip() for part in member_source.replace(";", "|").split("|") if part.strip()]
        if not members:
            raise ValueError("bundle_all_or_nothing requires at least one bundle_member_key")
        # Deduplicate while preserving order
        seen = set()
        unique_members = []
        for m in members:
            if m not in seen:
                seen.add(m)
                unique_members.append(m)
        self.dimension_key = str(self.dimension_key).strip()
        self.bundle_member_keys = "|".join(unique_members)
        return self


class ExcludePairRowSchema(ConstraintRowBase):
    constraint_type: Literal["exclude_pair"]
    dimension: Literal["initiative"]

    @model_validator(mode="after")
    def validate_exclude_pair(self):
        if not self.dimension_key or "|" not in self.dimension_key:
            raise ValueError("exclude_pair dimension_key must be 'INIT_A|INIT_B' (exactly two initiatives)")
        a, b, *rest = [part.strip() for part in self.dimension_key.split("|")]
        if rest:
            raise ValueError("exclude_pair must have exactly two initiatives")
        if not a or not b:
            raise ValueError("exclude_pair requires two non-empty initiative keys")
        if a == b:
            raise ValueError("exclude_pair cannot exclude an initiative from itself")
        # Normalize to sorted order to prevent A|B vs B|A duplicates
        sorted_pair = sorted([a, b])
        self.dimension_key = "|".join(sorted_pair)
        return self
            raise ValueError("exclude_pair requires two non-empty initiative keys")
        if a == b:
            raise ValueError("exclude_pair cannot exclude an initiative from itself")
        # Normalize to sorted order to prevent A|B vs B|A duplicates
        sorted_pair = sorted([a, b])
        self.dimension_key = "|".join(sorted_pair)
        return self
            raise ValueError("exclude_pair initiatives must be non-empty")
        if a == b:
            raise ValueError("exclude_pair initiatives must differ")
        return self


class ExcludeInitiativeRowSchema(ConstraintRowBase):
    constraint_type: Literal["exclude_initiative"]
    dimension: Literal["initiative"]

    @model_validator(mode="after")
    def validate_exclude(self):
        if not self.dimension_key:
            raise ValueError("exclude_initiative requires dimension_key")
        parts = [part.strip() for part in self.dimension_key.replace(";", ",").replace("|", ",").split(",") if part.strip()]
        if not parts:
            raise ValueError("exclude_initiative requires at least one initiative dimension_key")
        self.dimension_key = "|".join(parts)
        return self


class RequirePrereqRowSchema(ConstraintRowBase):
    constraint_type: Literal["require_prereq"]
    dimension: Literal["initiative"]

    @model_validator(mode="after")
    def validate_prereq(self):
        if not self.dimension_key or "|" not in self.dimension_key:
            raise ValueError("require_prereq requires dimension_key='INIT|PREREQ1|[PREREQ2|...]'")
        parts = [part.strip() for part in self.dimension_key.split("|") if part.strip()]
        if len(parts) < 2:
            raise ValueError("require_prereq needs at least one prereq after INIT")
        init = parts[0]
        prereqs = parts[1:]
        if not init:
            raise ValueError("require_prereq INIT must be non-empty")
        if any(p == init for p in prereqs):
            raise ValueError("require_prereq prereqs must differ from INIT")
        if len(set(prereqs)) != len(prereqs):
            raise ValueError("require_prereq prereqs must be unique")
        return self


class SynergyBonusRowSchema(ConstraintRowBase):
    constraint_type: Literal["synergy_bonus"]
    dimension: Literal["initiative"]

    @model_validator(mode="after")
    def validate_synergy(self):
        if not self.dimension_key or "|" not in self.dimension_key:
            raise ValueError("synergy_bonus dimension_key must be 'INIT_A|INIT_B' (two initiatives)")
        a, b, *rest = [part.strip() for part in self.dimension_key.split("|")]
        if rest:
            raise ValueError("synergy_bonus must have exactly two initiatives")
        if not a or not b:
            raise ValueError("synergy_bonus initiatives must be non-empty")
        if a == b:
            raise ValueError("synergy_bonus initiatives must differ")
        return self


ConstraintRow = Annotated[
    Union[
        CapacityFloorRowSchema,
        CapacityCapRowSchema,
        MandatoryRowSchema,
        BundleRowSchema,
        ExcludePairRowSchema,
        ExcludeInitiativeRowSchema,
        RequirePrereqRowSchema,
        SynergyBonusRowSchema,
    ],
    Field(discriminator="constraint_type"),
]


_CONSTRAINT_ROW_ADAPTER = TypeAdapter(ConstraintRow)


TargetDimension = Literal[
    "country",
    "product",
    "segment",
    "region",
    "department",
    "country_product",
    "all",
]


class TargetRowSchema(BaseModel):
    scenario_name: str
    constraint_set_name: str
    dimension: "TargetDimension" = "country"
    dimension_key: str
    kpi_key: str
    target_value: Optional[float] = None
    floor_or_goal: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("scenario_name", "constraint_set_name", "kpi_key", "dimension_key")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if v is None or str(v).strip() == "":
            raise ValueError("must not be blank")
        return str(v).strip()

    @field_validator("dimension", mode="before")
    @classmethod
    def normalize_dimension(cls, v: Optional[str]) -> str:
        if v is None or str(v).strip() == "":
            return "country"
        return str(v).strip().lower()

    @field_validator("dimension_key", mode="before")
    @classmethod
    def normalize_dimension_key(cls, v: Optional[str]) -> str:
        if v is None or str(v).strip() == "":
            return "all"
        return str(v).strip().lower()

    @model_validator(mode="after")
    def require_value_and_goal(self):
        if self.target_value is None:
            raise ValueError("target_value is required")
        if self.floor_or_goal is None:
            raise ValueError("floor_or_goal is required")
        # If dimension_key is 'all' or dimension is 'all', align both
        if self.dimension_key in {"all", "global", "total", "company"} or self.dimension == "all":
            self.dimension = "all"
            self.dimension_key = "all"
        return self

    @field_validator("target_value", mode="before")
    @classmethod
    def to_float(cls, v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"invalid number: {v}") from e

    @field_validator("target_value")
    @classmethod
    def non_negative(cls, v):
        if v is None:
            return None
        if v < 0:
            raise ValueError("target_value must be >= 0")
        return v

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
    bundles: List["BundleCompiled"] = Field(default_factory=list)
    exclusions_initiatives: List[str] = Field(default_factory=list)
    exclusions_pairs: List[List[str]] = Field(default_factory=list)
    prerequisites: List[List[str]] = Field(default_factory=list)
    synergy_bonuses: List[List[str]] = Field(default_factory=list)
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class BundleCompiled(BaseModel):
    bundle_key: str
    members: List[str]

    model_config = {"extra": "ignore"}


class CapacityFloor(BaseModel):
    dimension: str
    dimension_key: str
    min_tokens: float

    model_config = {"extra": "ignore"}


class CapacityCap(BaseModel):
    dimension: str
    dimension_key: str
    max_tokens: float

    model_config = {"extra": "ignore"}


class TargetConstraint(BaseModel):
    dimension: str
    dimension_key: str
    kpi_key: str
    floor_or_goal: str
    target_value: float
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


# Ensure forward refs resolve when imported elsewhere
ConstraintSetCompiled.model_rebuild()


def validate_constraint_row(row_num: int, data: dict) -> ValidationMessage:
    errors: List[str] = []
    warnings: List[str] = []
    # Normalize discriminator and dimension before union selection
    normalized = dict(data)
    if "constraint_type" in normalized:
        normalized["constraint_type"] = str(normalized["constraint_type"]).strip().lower().replace(" ", "_")
    if "dimension" in normalized:
        normalized["dimension"] = str(normalized["dimension"]).strip().lower()
    if "dimension_key" in normalized and normalized.get("dimension_key") is not None:
        normalized["dimension_key"] = str(normalized["dimension_key"]).strip()
    key = "|".join([
        str(normalized.get("scenario_name", "")).strip(),
        str(normalized.get("constraint_set_name", "")).strip(),
        str(normalized.get("constraint_type", "")).strip(),
        str(normalized.get("dimension", "")).strip(),
        str(normalized.get("dimension_key", "")).strip(),
    ]).strip("|")
    try:
        # Discriminated union enforces type-specific rules
        _CONSTRAINT_ROW_ADAPTER.validate_python(normalized)
    except ValidationError as ve:
        errors = [err['msg'] for err in ve.errors()]
    # Additional semantic check: min <= max when both present
    try:
        min_v = float(normalized["min_tokens"]) if normalized.get("min_tokens") not in (None, "") else None
        max_v = float(normalized["max_tokens"]) if normalized.get("max_tokens") not in (None, "") else None
        if min_v is not None and max_v is not None and min_v > max_v:
            errors.append("min_tokens cannot exceed max_tokens")
        if min_v is not None and min_v == 0:
            warnings.append("min_tokens is 0")
        if max_v is not None and max_v == 0:
            warnings.append("max_tokens is 0")
    except Exception:
        # numeric errors already captured
        pass
    return ValidationMessage(row_num=row_num, key=key, errors=errors, warnings=warnings)


def validate_target_row(row_num: int, data: dict, valid_kpis: Optional[set[str]] = None) -> ValidationMessage:
    errors: List[str] = []
    warnings: List[str] = []
    normalized = dict(data)
    if "dimension" in normalized:
        normalized["dimension"] = str(normalized.get("dimension", "country")).strip().lower()
    if "dimension_key" in normalized:
        normalized["dimension_key"] = str(normalized["dimension_key"]).strip().lower()
    if "kpi_key" in normalized and normalized.get("kpi_key") is not None:
        normalized["kpi_key"] = str(normalized["kpi_key"]).strip()
    key = "|".join([
        str(normalized.get("scenario_name", "")).strip(),
        str(normalized.get("constraint_set_name", "")).strip(),
        str(normalized.get("dimension", "")).strip(),
        str(normalized.get("dimension_key", "")).strip(),
        str(normalized.get("kpi_key", "")).strip(),
    ]).strip("|")
    try:
        TargetRowSchema(**normalized)
    except ValidationError as ve:
        errors = [err['msg'] for err in ve.errors()]
    if valid_kpis is not None:
        kpi = str(normalized.get("kpi_key", "")).strip()
        if kpi and kpi not in valid_kpis:
            errors.append("kpi_key not found in Metrics_Config")
    try:
        tv = float(normalized["target_value"]) if normalized.get("target_value") not in (None, "") else None
        if tv is not None and tv == 0:
            warnings.append("target_value is 0")
    except Exception:
        pass
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
    weights = data.get("objective_weights_json")
    if isinstance(weights, dict) and weights:
        try:
            total = float(sum(float(v) for v in weights.values()))
            if total != 0 and not (0.99 <= total <= 1.01):
                warnings.append("objective_weights_json does not sum to 1.0 (warning only)")
        except Exception:
            # shape errors are already caught in schema validation
            pass
    return ValidationMessage(row_num=row_num, key=key, errors=errors, warnings=warnings)


__all__ = [
    "CONSTRAINTS_SHEET_FIELD_MAP",
    "TARGETS_SHEET_FIELD_MAP",
    "SCENARIO_CONFIG_FIELD_MAP",
    "ValidationMessage",
    "ScenarioConfigSchema",
    "ConstraintRow",
    "TargetRowSchema",
    "CapacityFloor",
    "CapacityCap",
    "TargetConstraint",
    "ConstraintSetCompiled",
    "validate_constraint_row",
    "validate_target_row",
    "validate_scenario_config",
]
