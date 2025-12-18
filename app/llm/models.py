# productroadmap_sheet_project/app/llm/models.py

from __future__ import annotations

from typing import List, Optional, Any

from pydantic import BaseModel, model_validator


class MathModelPromptInput(BaseModel):
    initiative_key: str
    title: str
    problem_statement: Optional[str] = None
    desired_outcome: Optional[str] = None
    llm_summary: Optional[str] = None

    expected_impact_description: Optional[str] = None
    impact_metric: Optional[str] = None
    impact_unit: Optional[str] = None

    model_name: Optional[str] = None
    model_description_free_text: Optional[str] = None
    model_prompt_to_llm: Optional[str] = None


class MathModelSuggestion(BaseModel):
    formula_text: str
    assumptions: List[str]
    notes: Optional[str] = None


class ParamSuggestion(BaseModel):
    key: str  # identifier found in formula_text
    name: str  # human-friendly name
    description: Optional[str] = None
    unit: Optional[str] = None
    example_value: Optional[Any] = None  # keep string to allow ranges or enums
    source_hint: Optional[str] = None  # where to get data (system/team)

    @model_validator(mode="after")
    def _coerce_example_value(self) -> "ParamSuggestion":
        if self.example_value is None:
            return self
        # Convert numbers/bools/etc. to string
        self.example_value = str(self.example_value)
        return self

class ParamMetadataSuggestion(BaseModel):
    initiative_key: str
    identifiers: List[str]
    params: List[ParamSuggestion]
