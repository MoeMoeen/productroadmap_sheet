from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class InitiativeMathModelBase(BaseModel):
    formula_text: str
    parameters_json: Optional[Any] = None
    assumptions_text: Optional[str] = None
    suggested_by_llm: bool = False
    approved_by_user: bool = False


class InitiativeMathModelCreate(InitiativeMathModelBase):
    pass


class InitiativeMathModelRead(InitiativeMathModelBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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