# productroadmap_sheet_project/app/sheets/models.py

"""Pydantic models for sheet row representations."""

from __future__ import annotations

from typing import Any, Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator


# Common alias sets (used across tabs)
UPDATED_SOURCE_ALIASES = [
    "updated_source",
    "Updated Source",
    "UPDATED SOURCE",
    "UpdatedSource",
    "last_updated_source",
    "Last Updated Source",
]

UPDATED_AT_ALIASES = [
    "updated_at",
    "Updated At",
    "UPDATED AT",
    "UpdatedAt",
    "last_updated_at",
    "Last Updated At",
]

RUN_STATUS_ALIASES = [
    "run_status",
    "Run Status",
    "RUN STATUS",
    "status",
    "Status",
    "STATUS",
    "last_run_status",
    "Last Run Status",
]


# ProductOps Metrics_Config tab header aliases
METRICS_CONFIG_HEADER_MAP = {
    "kpi_key": ["kpi_key", "KPI Key", "kpi", "KPI", "metric_key", "Metric Key"],
    "kpi_name": ["kpi_name", "KPI Name", "kpi title", "KPI Title", "metric_name", "Metric Name"],
    "kpi_level": ["kpi_level", "KPI Level", "level", "Level", "metric_level", "Metric Level"],
    "unit": ["unit", "Unit", "units", "Units"],
    "description": ["description", "Description", "desc", "Desc"],
    "is_active": ["is_active", "Is Active", "active", "Active", "enabled", "Enabled"],
    "notes": ["notes", "Notes", "comment", "Comment", "comments", "Comments"],

    # system / read-only surfaces
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}

# ProductOps KPI_Contributions tab header aliases
KPI_CONTRIBUTIONS_HEADER_MAP = {
    "initiative_key": ["initiative_key", "Initiative Key", "initiative id", "Initiative ID", "key", "Key"],
    "kpi_contribution_json": [
        "kpi_contribution_json",
        "KPI Contribution JSON",
        "kpi_contributions",
        "KPI Contributions",
        "contributions",
        "Contributions",
    ],
    "notes": ["notes", "Notes"],

    # system / read-only
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}


# Centralized header mapping: canonical field name -> list of accepted aliases

# ProductOps allowlists
METRICS_CONFIG_EDITABLE_FIELDS: List[str] = [
    "kpi_key",
    "kpi_name",
    "kpi_level",
    "unit",
    "description",
    "is_active",
    "notes",
]

KPI_CONTRIBUTIONS_EDITABLE_FIELDS: List[str] = [
    "kpi_contribution_json",
    "notes",
]

# ProductOps MathModels tab columns and header aliases
MATHMODELS_HEADER_MAP = {
    "initiative_key": ["initiative_key"],
    "immediate_kpi_key": ["immediate_kpi_key", "Immediate KPI Key", "immediate kpi key"],
    "metric_chain_text": ["metric_chain_text", "Metric Chain", "metric chain"],
    "formula_text": ["formula_text", "formula_text_final", "formula"],
    "assumptions_text": ["assumptions_text", "assumptions", "notes"],
    "suggested_by_llm": ["suggested_by_llm", "llm_suggested"],
    "approved_by_user": ["approved_by_user", "approved"],
    "llm_suggested_formula_text": ["llm_suggested_formula_text", "formula_suggestion"],
    "llm_suggested_metric_chain_text": ["llm_suggested_metric_chain_text", "metric_chain_llm_suggestion", "LLM Suggested Metric Chain"],
    "llm_notes": ["llm_notes", "assumptions_suggestion", "llm_assumptions"],
    "model_name": ["model_name"],
    "model_description_free_text": ["model_description_free_text", "model_description", "description"],
    "model_prompt_to_llm": ["model_prompt_to_llm", "prompt_to_llm", "llm_prompt"],
    # Metadata/provenance (optional columns)
    "updated_source": ["updated_source", "Updated Source"],
    "updated_at": ["updated_at", "Updated At", "updated at"],
}

# ProductOps Params tab columns and header aliases
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
    "updated_at": ["updated_at", "Updated At", "updated at"],
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

# Mapping from score field names to possible header aliases used in ProductOps sheet Scoring_inputs tab
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
    "Customer Segment",
    "Initiative Type",
    "Hypothesis",
    "Problem Statement",
    "Immediate KPI Key",
    "Metric Chain JSON",
    "Is Optimization Candidate",
    "Candidate Period Key",
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
    # Metadata
    "Updated At",
    "Updated Source",
]

# Mapping from Central Backlog header names to model field names
CENTRAL_HEADER_TO_FIELD: Dict[str, str] = {
    "Initiative Key": "initiative_key",
    "Title": "title",
    "Requesting Team": "requesting_team",
    "Requester Name": "requester_name",
    "Requester Email": "requester_email",
    "Country": "country",
    "Product Area": "product_area",
    "Status": "status",
    "Customer Segment": "customer_segment",
    "Initiative Type": "initiative_type",
    "Hypothesis": "hypothesis",
    "Problem Statement": "problem_statement",
    "Immediate KPI Key": "immediate_kpi_key",
    "Metric Chain JSON": "metric_chain_json",
    "Is Optimization Candidate": "is_optimization_candidate",
    "Candidate Period Key": "candidate_period_key",
    "Value Score": "value_score",
    "Effort Score": "effort_score",
    "Overall Score": "overall_score",
    "Active Scoring Framework": "active_scoring_framework",
    "Use Math Model": "use_math_model",
    "Dependencies Initiatives": "dependencies_initiatives",
    "Dependencies Others": "dependencies_others",
    "LLM Summary": "llm_summary",
    "Updated At": "updated_at",
    "Updated Source": "updated_source",
}

__all__ = [
    "UPDATED_SOURCE_ALIASES",
    "UPDATED_AT_ALIASES",
    "RUN_STATUS_ALIASES",
    "METRICS_CONFIG_HEADER_MAP",
    "METRICS_CONFIG_EDITABLE_FIELDS",
    "KPI_CONTRIBUTIONS_HEADER_MAP",
    "KPI_CONTRIBUTIONS_EDITABLE_FIELDS",
    "MATHMODELS_HEADER_MAP",
    "PARAMS_HEADER_MAP",
    "INTAKE_HEADER_MAP",
    "PRODUCTOPS_SCORE_OUTPUT_COLUMNS",
    "SCORE_FIELD_TO_HEADERS",
    "CENTRAL_BACKLOG_HEADER",
    "CENTRAL_HEADER_TO_FIELD",
    "CENTRAL_EDITABLE_FIELDS",
    "MetricsConfigRow",
    "KPIContributionRow",
    "MathModelRow",
    "ParamRow",
]


class MetricsConfigRow(BaseModel):
    """Represents a single row from ProductOps Metrics_Config tab."""

    model_config = ConfigDict(extra="ignore")

    kpi_key: str
    kpi_name: Optional[str] = None
    kpi_level: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    # Keep None so blank cells don't force True; sync layer applies defaults conditionally
    is_active: Optional[bool] = Field(default=None)
    notes: Optional[str] = None


class KPIContributionRow(BaseModel):
    """Represents a single row from ProductOps KPI_Contributions tab."""

    model_config = ConfigDict(extra="ignore")

    initiative_key: str
    kpi_contribution_json: Optional[Any] = None
    notes: Optional[str] = None


class MathModelRow(BaseModel):
    """Represents a single row from MathModels tab in ProductOps sheet.
    
    Columns:
    - initiative_key (str): Initiative key (PM-friendly identifier)
    - model_name (str): PM-provided name for the model
    - model_description_free_text (str): PM-authored description
    - model_prompt_to_llm (str): PM extra prompt
    - immediate_kpi_key (str): KPI anchor
    - metric_chain_text (str/JSON): PM-provided metric chain
    - llm_suggested_metric_chain_text (str): LLM suggestion for metric chain
    - formula_text (str): The approved/final formula definition
    - approved_by_user (bool): Has user approved?
    - llm_suggested_formula_text (str): LLM suggestion for formula (separate column)
    - llm_notes (str): LLM notes column
    - assumptions_text (str): Assumptions/notes (PM-owned)
    - suggested_by_llm (bool): Was this suggested by LLM?
    """
    
    model_config = ConfigDict(extra="ignore")
    
    initiative_key: str
    formula_text: Optional[str] = None
    assumptions_text: Optional[str] = None
    suggested_by_llm: Optional[bool] = None
    approved_by_user: Optional[bool] = None
    llm_suggested_formula_text: Optional[str] = None
    llm_notes: Optional[str] = None
    model_name: Optional[str] = None
    model_description_free_text: Optional[str] = None
    model_prompt_to_llm: Optional[str] = None
    immediate_kpi_key: Optional[str] = None
    metric_chain_text: Optional[str] = None
    llm_suggested_metric_chain_text: Optional[str] = None


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
    "Customer Segment",
    "Initiative Type",
    "Hypothesis",
    "Problem Statement",
    "Dependencies Initiatives",
    "Dependencies Others",
    "LLM Summary",
    "Is Optimization Candidate",
    "Candidate Period Key",
]
