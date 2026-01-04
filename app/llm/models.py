# productroadmap_sheet_project/app/llm/models.py

from __future__ import annotations

from typing import List, Optional, Any

from pydantic import BaseModel, ConfigDict, Field, AliasChoices, model_validator


class MathModelPromptInput(BaseModel):
    initiative_key: str
    title: str
    problem_statement: Optional[str] = None
    desired_outcome: Optional[str] = None
    hypothesis: Optional[str] = None
    llm_summary: Optional[str] = None

    immediate_kpi_key: Optional[str] = None
    metric_chain_text: Optional[str] = None

    expected_impact_description: Optional[str] = None
    impact_metric: Optional[str] = None
    impact_unit: Optional[str] = None

    model_name: Optional[str] = None
    model_description_free_text: Optional[str] = None
    model_prompt_to_llm: Optional[str] = None
    assumptions_text: Optional[str] = None


class MathModelSuggestion(BaseModel):
    """LLM response for math-model suggestions.

    Uses aliases so legacy responses with formula_text/metric_chain_text/notes
    still parse, but new prompts should return the llm_* keys explicitly.
    """

    model_config = ConfigDict(populate_by_name=True)

    llm_suggested_formula_text: str = Field(
        alias="llm_suggested_formula_text",
        validation_alias=AliasChoices("llm_suggested_formula_text", "formula_text"),
    )
    llm_suggested_metric_chain_text: Optional[str] = Field(
        default=None,
        alias="llm_suggested_metric_chain_text",
        validation_alias=AliasChoices("llm_suggested_metric_chain_text", "metric_chain_text"),
    )
    llm_notes: Optional[str] = Field(
        default=None,
        alias="llm_notes",
        validation_alias=AliasChoices("llm_notes", "notes"),
    )

    @property
    def formula_text(self) -> str:
        return self.llm_suggested_formula_text

    @property
    def metric_chain_text(self) -> Optional[str]:
        return self.llm_suggested_metric_chain_text

    @property
    def notes(self) -> Optional[str]:
        return self.llm_notes


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
