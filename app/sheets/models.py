# productroadmap_sheet_project/app/sheets/models.py

"""Pydantic models for sheet row representations."""

from __future__ import annotations

from typing import Any, Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# Centralized header mapping: canonical field name -> list of accepted aliases
MATHMODELS_HEADER_MAP = {
    "initiative_key": ["initiative_key"],
    "formula_text": ["formula_text", "formula_text_final", "formula"],
    "parameters_json": ["parameters_json", "parameters"],
    "assumptions_text": ["assumptions_text", "assumptions", "notes"],
    "suggested_by_llm": ["suggested_by_llm", "llm_suggested"],
    "approved_by_user": ["approved_by_user", "approved"],
    "llm_suggested_formula_text": ["llm_suggested_formula_text", "formula_suggestion"],
    "llm_notes": ["llm_notes", "assumptions_suggestion", "llm_assumptions"],
}

PARAMS_HEADER_MAP = {
    "initiative_key": ["initiative_key", "Initiative Key", "Initiative_Key", "initiative key"],
    "param_name": ["param_name", "parameter_name", "name"],
    "value": ["value"],
    "unit": ["unit"],
    "param_display": ["param_display", "display", "display_name"],
    "description": ["description"],
    "source": ["source"],
    "approved": ["approved"],
    "is_auto_seeded": ["is_auto_seeded", "auto_seeded"],
    "framework": ["framework"],
    "min": ["min", "min_value"],
    "max": ["max", "max_value"],
    "notes": ["notes", "param_notes"],
}


class MathModelRow(BaseModel):
    """Represents a single row from MathModels tab in ProductOps sheet.
    
    Columns:
    - initiative_key (str): Initiative key (PM-friendly identifier)
    - formula_text (str): The approved/final formula definition
    - parameters_json (str): JSON-serialized parameters
    - assumptions_text (str): Assumptions/notes
    - suggested_by_llm (bool): Was this suggested by LLM?
    - approved_by_user (bool): Has user approved?
    - llm_suggested_formula_text (str): LLM suggestion for formula (separate column)
    - llm_notes (str): LLM suggestion for assumptions (separate column)
    """
    
    model_config = ConfigDict(extra="ignore")
    
    initiative_key: str
    formula_text: Optional[str] = None
    parameters_json: Optional[str] = None
    assumptions_text: Optional[str] = None
    suggested_by_llm: Optional[bool] = None
    approved_by_user: Optional[bool] = None
    llm_suggested_formula_text: Optional[str] = None
    llm_notes: Optional[str] = None


class ParamRow(BaseModel):
    """Represents a single row from Params tab in ProductOps sheet.
    
    Columns:
    - initiative_key (str): Initiative key (PM-friendly identifier)
    - param_name (str): Name of parameter
    - value (str/float): Current parameter value
    - unit (str): Unit of measurement
    - param_display (str): Display name for UI
    - description (str): Description/notes
    - source (str): Where value came from (e.g., "analytics", "manual", "ai_suggested")
    - approved (bool): Has user approved this parameter?
    - is_auto_seeded (bool): Was this auto-seeded?
    - framework (str): Framework type (default "MATH_MODEL")
    - min/max (float): Optional bounds
    - notes (str): Optional notes
    """
    
    model_config = ConfigDict(extra="ignore")
    
    initiative_key: str
    param_name: str
    value: Optional[float | str] = None
    unit: Optional[str] = None
    param_display: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    approved: Optional[bool] = None
    is_auto_seeded: Optional[bool] = None
    framework: Optional[str] = "MATH_MODEL"
    min: Optional[float] = None
    max: Optional[float] = None
    notes: Optional[str] = None
