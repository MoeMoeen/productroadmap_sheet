# productroadmap_sheet_project/app/sheets/models.py

"""Pydantic models for sheet row representations."""

from __future__ import annotations

from typing import Any, Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator


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
    "model_name": ["model_name"],
    "model_description_free_text": ["model_description_free_text", "model_description", "description"],
    "model_prompt_to_llm": ["model_prompt_to_llm", "prompt_to_llm", "llm_prompt"],
    # Metadata/provenance (optional columns)
    "updated_source": ["updated_source", "Updated Source"],
    "updated_at": ["updated_at", "Updated At"],
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
    # Metadata/provenance (optional columns)
    "updated_source": ["updated_source", "Updated Source"],
    "updated_at": ["updated_at", "Updated At"],
}

# Intake sheet header aliases (centralized)
# Only include well-known, stable fields here to avoid collisions.
INTAKE_HEADER_MAP: Dict[str, List[str]] = {
    "initiative_key": ["Initiative Key", "InitiativeKey", "initiative_key", "initiative key"],
    "updated_at": ["Updated At", "updated_at", "updated at"],
}

# ProductOps Scoring output columns and header aliases
# These are written by Flow 3 write-back stage. Keep aliases flexible for namespaced headers.
PRODUCTOPS_SCORE_OUTPUT_COLUMNS: List[str] = [
    "rice_value_score",
    "rice_effort_score",
    "rice_overall_score",
    "wsjf_value_score",
    "wsjf_effort_score",
    "wsjf_overall_score",
    "math_value_score",
    "math_effort_score",
    "math_overall_score",
    "math_warnings",
    "value_score",
    "effort_score",
    "overall_score",
]

SCORE_FIELD_TO_HEADERS: Dict[str, List[str]] = {
    "rice_value_score": ["rice_value_score", "rice: value score"],
    "rice_effort_score": ["rice_effort_score", "rice: effort score"],
    "rice_overall_score": ["rice_overall_score", "rice: overall score"],
    "wsjf_value_score": ["wsjf_value_score", "wsjf: value score"],
    "wsjf_effort_score": ["wsjf_effort_score", "wsjf: effort score"],
    "wsjf_overall_score": ["wsjf_overall_score", "wsjf: overall score"],
    "math_value_score": ["math_value_score", "math: value score", "math_model: value score"],
    "math_effort_score": ["math_effort_score", "math: effort score", "math_model: effort score"],
    "math_overall_score": ["math_overall_score", "math: overall score", "math_model: overall score"],
    "math_warnings": ["math_warnings", "math: warnings", "math_model: warnings", "math_error", "math_errors"],
    "value_score": ["active_value_score", "active: value score"],
    "effort_score": ["active_effort_score", "active: effort score"],
    "overall_score": ["active_overall_score", "active: overall score"],
}

# Central Backlog headers and field mapping used by backlog writer
CENTRAL_BACKLOG_HEADER: List[str] = [
    "Initiative Key",
    "Title",
    "Requesting Team",
    "Requester Name",
    "Requester Email",
    "Country",
    "Product Area",
    "Status",
    "Strategic Theme",
    "Customer Segment",
    "Initiative Type",
    "Hypothesis",
    "Problem Statement",
    # Scoring outputs
    "Value Score",
    "Effort Score",
    "Overall Score",
    "Active Scoring Framework",
    "Use Math Model",
    # Dependencies & LLM
    "Dependencies Initiatives",
    "Dependencies Others",
    "LLM Summary",
    "LLM Notes",
    # Strategic coefficient
    "Strategic Priority Coefficient",
    # Metadata
    "Updated At",
    "Updated Source",
]

CENTRAL_HEADER_TO_FIELD: Dict[str, str] = {
    "Initiative Key": "initiative_key",
    "Title": "title",
    "Requesting Team": "requesting_team",
    "Requester Name": "requester_name",
    "Requester Email": "requester_email",
    "Country": "country",
    "Product Area": "product_area",
    "Status": "status",
    "Strategic Theme": "strategic_theme",
    "Customer Segment": "customer_segment",
    "Initiative Type": "initiative_type",
    "Hypothesis": "hypothesis",
    "Problem Statement": "problem_statement",
    "Value Score": "value_score",
    "Effort Score": "effort_score",
    "Overall Score": "overall_score",
    "Active Scoring Framework": "active_scoring_framework",
    "Use Math Model": "use_math_model",
    "Dependencies Initiatives": "dependencies_initiatives",
    "Dependencies Others": "dependencies_others",
    "LLM Summary": "llm_summary",
    "LLM Notes": "llm_notes",
    "Strategic Priority Coefficient": "strategic_priority_coefficient",
    "Updated At": "updated_at",
    "Updated Source": "updated_source",
}

__all__ = [
    "MATHMODELS_HEADER_MAP",
    "PARAMS_HEADER_MAP",
    "INTAKE_HEADER_MAP",
    "PRODUCTOPS_SCORE_OUTPUT_COLUMNS",
    "SCORE_FIELD_TO_HEADERS",
    "CENTRAL_BACKLOG_HEADER",
    "CENTRAL_HEADER_TO_FIELD",
    "CENTRAL_EDITABLE_FIELDS",
]


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
    model_name: Optional[str] = None
    model_description_free_text: Optional[str] = None
    model_prompt_to_llm: Optional[str] = None


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
    # Back-compat alias expected by some tests/readers
    display: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    approved: Optional[bool] = None
    is_auto_seeded: Optional[bool] = None
    framework: Optional[str] = "MATH_MODEL"
    min: Optional[float] = None
    max: Optional[float] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _sync_display_aliases(self) -> "ParamRow":
        # Ensure back-compat: keep display and param_display in sync
        if self.display and not self.param_display:
            self.param_display = self.display
        elif self.param_display and not self.display:
            self.display = self.param_display
        return self


# Central Backlog editable columns mapping (used by protected ranges logic)
# Keys are exact header names in CENTRAL_BACKLOG_HEADER that are editable by users.
CENTRAL_EDITABLE_FIELDS: List[str] = [
    "Title",
    "Requesting Team",
    "Requester Name",
    "Requester Email",
    "Country",
    "Product Area",
    "Status",
    "Strategic Theme",
    "Customer Segment",
    "Initiative Type",
    "Hypothesis",
    "Problem Statement",
    "Dependencies Initiatives",
    "Dependencies Others",
    "LLM Summary",
    "LLM Notes",
]
