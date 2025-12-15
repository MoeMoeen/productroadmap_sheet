# productroadmap_sheet_project/app/llm/models.py

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


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
