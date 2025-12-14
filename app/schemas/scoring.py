# productroadmap_sheet_project/app/schemas/scoring.py

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class InitiativeMathModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    framework: str
    formula_text: str
    parameters_json: Optional[dict] = None
    assumptions_text: Optional[str] = None
    suggested_by_llm: bool
    approved_by_user: bool
    created_at: datetime
    updated_at: datetime


class InitiativeParamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    initiative_id: int
    framework: str
    param_name: str
    param_display: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    value: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    source: Optional[str] = None
    approved: bool
    is_auto_seeded: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class InitiativeMathModelBase(BaseModel):
    framework: str = "MATH_MODEL"
    formula_text: str
    parameters_json: Optional[Any] = None
    assumptions_text: Optional[str] = None
    suggested_by_llm: bool = False
    approved_by_user: bool = False


class InitiativeScoreRead(BaseModel):
    id: int
    initiative_id: int
    framework_name: str
    value_score: Optional[float] = None
    effort_score: Optional[float] = None
    overall_score: Optional[float] = None
    inputs_json: Optional[Any] = None
    llm_suggested: bool = False
    approved_by_user: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}