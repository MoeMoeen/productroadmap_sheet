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
    "kpi_contribution_computed_json": [
        "kpi_contribution_computed_json",
        "KPI Contribution Computed JSON",
        "computed_contributions",
        "Computed Contributions",
        "system_computed",
    ],
    "kpi_contribution_source": [
        "kpi_contribution_source",
        "KPI Contribution Source",
        "contribution_source",
        "Source",
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

# Optimization Center header maps (ProductOps Optimization Center sheet)
# Candidates tab: Read-only reference view + minimal editable fields
# Constraint columns (is_mandatory, bundle_key, etc.) are DISPLAY-ONLY, derived from Constraints tab
OPT_CANDIDATES_HEADER_MAP: Dict[str, List[str]] = {
    "initiative_key": ["initiative_key", "Initiative Key", "key"],
    "title": ["title", "Title"],
    "country": ["country", "Country"],
    "department": ["department", "Department"],
    "category": ["category", "Category"],
    "engineering_tokens": ["engineering_tokens", "Engineering Tokens", "capacity_tokens", "Capacity Tokens"],
    "deadline_date": ["deadline_date", "Deadline Date", "deadline"],
    # Display-only constraint indicators (derived from Constraints tab compiled JSON):
    "is_mandatory": ["is_mandatory", "Is Mandatory", "mandatory"],
    "mandate_reason": ["mandate_reason", "Mandate Reason", "mandatory_reason"],
    "bundle_key": ["bundle_key", "Bundle Key", "bundle"],
    "prerequisite_keys": ["prerequisite_keys", "Prerequisite Keys", "prerequisites"],
    "exclusion_keys": ["exclusion_keys", "Exclusion Keys", "exclusions"],
    "program_key": ["program_key", "Program Key"],
    "synergy_group_keys": ["synergy_group_keys", "Synergy Group Keys", "synergy_groups"],
    "active_scoring_framework": ["active_scoring_framework", "Active Scoring Framework"],
    "active_overall_score": ["active_overall_score", "Active Overall Score"],
    "north_star_contribution": ["north_star_contribution", "North Star Contribution", "north_star"],
    "strategic_kpi_contributions": ["strategic_kpi_contributions", "Strategic KPI Contributions"],
    "immediate_kpi_key": ["immediate_kpi_key", "Immediate KPI Key"],
    "lifecycle_status": ["lifecycle_status", "Lifecycle Status"],
    "notes": ["notes", "Notes"],
    "is_selected_for_run": ["is_selected_for_run", "Is Selected For Run", "selected"],
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}

OPT_SCENARIO_CONFIG_HEADER_MAP: Dict[str, List[str]] = {
    "scenario_name": ["scenario_name", "Scenario Name", "scenario"],
    "period_key": ["period_key", "Period Key", "period"],
    "capacity_total_tokens": ["capacity_total_tokens", "Capacity Total Tokens", "capacity", "total_tokens"],
    "objective_mode": ["objective_mode", "Objective Mode"],
    "objective_weights_json": ["objective_weights_json", "Objective Weights JSON", "objective_weights"],
    "notes": ["notes", "Notes"],
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}

OPT_CONSTRAINTS_HEADER_MAP: Dict[str, List[str]] = {
    "scenario_name": ["scenario_name", "Scenario Name", "scenario"],
    "constraint_set_name": ["constraint_set_name", "Constraint Set Name", "constraint_set", "set"],
    "constraint_type": ["constraint_type", "Constraint Type", "type"],
    "dimension": ["dimension", "Dimension"],
    "dimension_key": ["dimension_key", "Dimension Key", "key", "Key"],
    "min_tokens": ["min_tokens", "Min Tokens", "min"],
    "max_tokens": ["max_tokens", "Max Tokens", "max"],
    "bundle_member_keys": ["bundle_member_keys", "Bundle Member Keys", "bundle_members"],
    "prereq_member_keys": ["prereq_member_keys", "Prereq Member Keys", "prerequisite_keys", "prerequisites"],
    "notes": ["notes", "Notes"],
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}

OPT_TARGETS_HEADER_MAP: Dict[str, List[str]] = {
    "scenario_name": ["scenario_name", "Scenario Name", "scenario"],
    "constraint_set_name": ["constraint_set_name", "Constraint Set Name", "constraint_set", "set"],
    "dimension": ["dimension", "Dimension"],
    "dimension_key": ["dimension_key", "Dimension Key", "country", "Country", "market", "Market"],
    "kpi_key": ["kpi_key", "KPI Key"],
    "target_value": ["target_value", "Target Value"],
    "floor_or_goal": ["floor_or_goal", "Floor Or Goal", "floor_goal"],
    "notes": ["notes", "Notes"],
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}

OPT_RUNS_HEADER_MAP: Dict[str, List[str]] = {
    "run_id": ["run_id", "Run Id", "run"],
    "scenario_name": ["scenario_name", "Scenario Name"],
    "period_key": ["period_key", "Period Key", "period"],
    "optimization_db_status": ["db_status", "db status", "optimization_db_status", "Optimization DB Status"],
    "created_at": ["created_at", "Created At"],
    "started_at": ["started_at", "Started At"],
    "finished_at": ["finished_at", "Finished At"],
    "selected_count": ["selected_count", "Selected Count"],
    "capacity_used": ["capacity_used", "Capacity Used"],
    "total_objective_raw": ["total_objective_raw", "Total Objective Raw"],
    "total_objective": ["total_objective", "Total Objective"],
    "gap_summary": ["gap_summary", "Gap Summary"],
    "results_tab_ref": ["results_tab_ref", "Results Tab Ref"],
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}

OPT_RESULTS_HEADER_MAP: Dict[str, List[str]] = {
    "run_id": ["run_id", "Run Id", "run"],
    "initiative_key": ["initiative_key", "Initiative Key", "key"],
    "selected": ["selected", "Selected"],
    "allocated_tokens": ["allocated_tokens", "Allocated Tokens", "tokens"],
    # Frozen dimension snapshot from candidate
    "country": ["market", "Market", "country", "Country"],
    "department": ["department", "Department"],
    "category": ["category", "Category"],
    "program": ["program", "Program"],
    "product": ["product", "Product"],
    "segment": ["segment", "Segment"],
    # Objective attribution
    "objective_mode": ["objective_mode", "Objective Mode"],
    "objective_contribution": ["objective_contribution", "Objective Contribution"],
    "north_star_gain": ["north_star_gain", "North Star Gain"],
    # Display fields
    "active_overall_score": ["active_overall_score", "Active Overall Score"],
    "dependency_status": ["dependency_status", "Dependency Status"],
    "notes": ["notes", "Notes"],
    # System
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}

OPT_GAPS_ALERTS_HEADER_MAP: Dict[str, List[str]] = {
    "run_id": ["run_id", "Run Id", "run"],
    "dimension": ["dimension", "Dimension"],
    "dimension_key": ["dimension_key", "Dimension Key"],
    "kpi_key": ["kpi_key", "KPI Key"],
    "target": ["target", "Target"],
    "achieved": ["achieved", "Achieved"],
    "gap": ["gap", "Gap"],
    "severity": ["severity", "Severity"],
    "notes": ["notes", "Notes"],
    "recommendation": ["recommendation", "Recommendation"],
    "run_status": RUN_STATUS_ALIASES,
    "updated_source": UPDATED_SOURCE_ALIASES,
    "updated_at": UPDATED_AT_ALIASES,
}
# Editable fields: PM can edit only these fields on Candidates tab
# Constraint fields (is_mandatory, bundle_key, etc.) are DISPLAY-ONLY on Candidates
# Entry surface for constraints is exclusively the Constraints tab
OPT_CANDIDATES_EDITABLE_FIELDS: List[str] = [
    "engineering_tokens",
    "deadline_date",
    "category",  # PM input: work type (UX Enhancement, Tech Debt, New Feature, etc.)
    "program_key",  # PM input: assign to cross-functional program (optional)
    "notes",
    "is_selected_for_run",
]
# Editable fields means PM-editable in the sheet; others are system-managed.
OPT_SCENARIO_CONFIG_EDITABLE_FIELDS: List[str] = [
    "scenario_name",
    "period_key",
    "capacity_total_tokens",
    "objective_mode",
    "objective_weights_json",
    "notes",
]
# Editable fields means PM-editable in the sheet; others are system-managed.
OPT_CONSTRAINTS_EDITABLE_FIELDS: List[str] = [
    "constraint_type",
    "dimension",
    "dimension_key",
    "min_tokens",
    "max_tokens",
    "bundle_member_keys",
    "prereq_member_keys",
    "notes",
]
# Editable fields means PM-editable in the sheet; others are system-managed.
OPT_TARGETS_EDITABLE_FIELDS: List[str] = [
    "dimension",
    "dimension_key",
    "kpi_key",
    "target_value",
    "floor_or_goal",
    "notes",
]
# Editable fields means PM-editable in the sheet; others are system-managed.
OPT_RESULTS_EDITABLE_FIELDS: List[str] = ["notes"]

# Editable fields means PM-editable in the sheet; others are system-managed.
OPT_GAPS_ALERTS_EDITABLE_FIELDS: List[str] = ["notes", "recommendation"]

# Output fields means these are written by the system, during the optimization execution, to the sheet, not by PMs.
OPT_RUNS_OUTPUT_FIELDS: List[str] = [
    "run_id",
    "scenario_name",
    "period_key",
    "optimization_db_status",
    "created_at",
    "started_at",
    "finished_at",
    "selected_count",
    "capacity_used",
    "total_objective_raw",
    "total_objective",
    "gap_summary",
    "results_tab_ref",
]
# Output fields means these are written by the system, during the optimization execution, to the sheet, not by PMs.
OPT_RESULTS_OUTPUT_FIELDS: List[str] = [
    "run_id",
    "initiative_key",
    "selected",
    "allocated_tokens",
    "country",
    "department",
    "category",
    "program",
    "product",
    "segment",
    "objective_mode",
    "objective_contribution",
    "north_star_gain",
    "active_overall_score",
    "dependency_status",
]
# Output fields means these are written by the system, during the optimization execution, to the sheet, not by PMs.
OPT_GAPS_ALERTS_OUTPUT_FIELDS: List[str] = [
    "run_id",
    "dimension",
    "dimension_key",
    "kpi_key",
    "target",
    "achieved",
    "gap",
    "severity",
]

# ProductOps MathModels tab columns and header aliases
MATHMODELS_HEADER_MAP = {
    "initiative_key": ["initiative_key"],
    "model_name": ["model_name", "Model Name"],
    "target_kpi_key": ["target_kpi_key", "Target KPI Key", "target_kpi", "Target KPI"],
    "immediate_kpi_key": ["immediate_kpi_key", "Immediate KPI Key", "immediate kpi key"],
    "metric_chain_text": ["metric_chain_text", "Metric Chain", "metric chain"],
    "formula_text": ["formula_text", "formula_text_final", "formula"],
    "assumptions_text": ["assumptions_text", "assumptions", "notes"],
    "is_primary": ["is_primary", "Is Primary", "primary", "Primary"],
    "computed_score": ["computed_score", "Computed Score", "score", "Score"],
    "suggested_by_llm": ["suggested_by_llm", "llm_suggested"],
    "approved_by_user": ["approved_by_user", "approved"],
    "llm_suggested_formula_text": ["llm_suggested_formula_text", "formula_suggestion"],
    "llm_suggested_metric_chain_text": ["llm_suggested_metric_chain_text", "metric_chain_llm_suggestion", "LLM Suggested Metric Chain"],
    "llm_notes": ["llm_notes", "assumptions_suggestion", "llm_assumptions"],
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
    "department": ["Department", "department", "dept", "Dept"],
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
    "Department",
    "Lifecycle Status",
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
    "Lifecycle Status": "lifecycle_status",
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
    "OPT_CANDIDATES_HEADER_MAP",
    "OPT_SCENARIO_CONFIG_HEADER_MAP",
    "OPT_CONSTRAINTS_HEADER_MAP",
    "OPT_TARGETS_HEADER_MAP",
    "OPT_RUNS_HEADER_MAP",
    "OPT_RESULTS_HEADER_MAP",
    "OPT_GAPS_ALERTS_HEADER_MAP",
    "OPT_CANDIDATES_EDITABLE_FIELDS",
    "OPT_SCENARIO_CONFIG_EDITABLE_FIELDS",
    "OPT_CONSTRAINTS_EDITABLE_FIELDS",
    "OPT_TARGETS_EDITABLE_FIELDS",
    "OPT_RUNS_OUTPUT_FIELDS",
    "OPT_RESULTS_OUTPUT_FIELDS",
    "OPT_GAPS_ALERTS_OUTPUT_FIELDS",
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
    "OptCandidateRow",
    "OptScenarioConfigRow",
    "OptConstraintRow",
    "OptTargetRow",
    "OptRunRow",
    "OptResultRow",
    "OptGapAlertRow",
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
    kpi_contribution_computed_json: Optional[Any] = None
    kpi_contribution_source: Optional[str] = None
    notes: Optional[str] = None


class MathModelRow(BaseModel):
    """Represents a single row from MathModels tab in ProductOps sheet.
    
    Columns:
    - initiative_key (str): Initiative key (PM-friendly identifier)
    - model_name (str): PM-provided name for the model
    - target_kpi_key (str): Which KPI this model targets (for 1:N multi-model aggregation)
    - model_description_free_text (str): PM-authored description
    - model_prompt_to_llm (str): PM extra prompt
    - immediate_kpi_key (str): KPI anchor
    - metric_chain_text (str/JSON): PM-provided metric chain
    - llm_suggested_metric_chain_text (str): LLM suggestion for metric chain
    - formula_text (str): The approved/final formula definition
    - approved_by_user (bool): Has user approved?
    - is_primary (bool): Is this the primary/representative model?
    - computed_score (float): Calculated impact score for this specific model
    - llm_suggested_formula_text (str): LLM suggestion for formula (separate column)
    - llm_notes (str): LLM notes column
    - assumptions_text (str): Assumptions/notes (PM-owned)
    - suggested_by_llm (bool): Was this suggested by LLM?
    """
    
    model_config = ConfigDict(extra="ignore")
    
    initiative_key: str
    model_name: Optional[str] = None
    target_kpi_key: Optional[str] = None
    formula_text: Optional[str] = None
    assumptions_text: Optional[str] = None
    is_primary: Optional[bool] = None
    computed_score: Optional[float] = None
    suggested_by_llm: Optional[bool] = None
    approved_by_user: Optional[bool] = None
    llm_suggested_formula_text: Optional[str] = None
    llm_notes: Optional[str] = None
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


class OptCandidateRow(BaseModel):
    """Optimization Center Candidates tab row."""

    model_config = ConfigDict(extra="ignore")

    initiative_key: str
    title: Optional[str] = None
    country: Optional[str] = None
    department: Optional[str] = None
    category: Optional[str] = None
    engineering_tokens: Optional[float] = None
    deadline_date: Optional[str] = None
    is_mandatory: Optional[bool] = None
    mandate_reason: Optional[str] = None
    bundle_key: Optional[str] = None
    prerequisite_keys: Optional[List[str]] = None
    exclusion_keys: Optional[List[str]] = None
    program_key: Optional[str] = None
    synergy_group_keys: Optional[List[str]] = None
    active_scoring_framework: Optional[str] = None
    active_overall_score: Optional[float] = None
    north_star_contribution: Optional[float] = None
    strategic_kpi_contributions: Optional[str] = None
    immediate_kpi_key: Optional[str] = None
    lifecycle_status: Optional[str] = None
    notes: Optional[str] = None
    is_selected_for_run: Optional[bool] = None
    run_status: Optional[str] = None
    updated_source: Optional[str] = None
    updated_at: Optional[str] = None


class OptScenarioConfigRow(BaseModel):
    """Optimization Center Scenario_Config tab row."""

    model_config = ConfigDict(extra="ignore")

    scenario_name: str
    period_key: Optional[str] = None
    capacity_total_tokens: Optional[float] = None
    objective_mode: Optional[str] = None
    objective_weights_json: Optional[Any] = None
    notes: Optional[str] = None
    run_status: Optional[str] = None
    updated_source: Optional[str] = None
    updated_at: Optional[str] = None


class OptConstraintRow(BaseModel):
    """Optimization Center Constraints tab row."""

    model_config = ConfigDict(extra="ignore")

    scenario_name: str
    constraint_set_name: str
    constraint_type: str
    dimension: str
    dimension_key: Optional[str] = None
    min_tokens: Optional[float] = None
    max_tokens: Optional[float] = None
    bundle_member_keys: Optional[str] = None
    prereq_member_keys: Optional[str] = None
    notes: Optional[str] = None
    run_status: Optional[str] = None
    updated_source: Optional[str] = None
    updated_at: Optional[str] = None


class OptTargetRow(BaseModel):
    """Optimization Center Targets tab row."""

    model_config = ConfigDict(extra="ignore")

    scenario_name: str
    constraint_set_name: str
    dimension: Optional[str] = "country"
    dimension_key: str
    kpi_key: str
    target_value: Optional[float] = None
    floor_or_goal: Optional[str] = None
    notes: Optional[str] = None
    run_status: Optional[str] = None
    updated_source: Optional[str] = None
    updated_at: Optional[str] = None


class OptRunRow(BaseModel):
    """Optimization Center Runs tab row."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    scenario_name: Optional[str] = None
    period_key: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    finished_at: Optional[str] = None
    selected_count: Optional[int] = None
    total_objective: Optional[float] = None
    capacity_used: Optional[float] = None
    gap_summary: Optional[str] = None
    results_tab_ref: Optional[str] = None
    run_status: Optional[str] = None
    updated_source: Optional[str] = None
    updated_at: Optional[str] = None


class OptResultRow(BaseModel):
    """Optimization Center Results tab row."""

    model_config = ConfigDict(extra="ignore")

    initiative_key: str
    selected: Optional[bool] = None
    allocated_tokens: Optional[float] = None
    country: Optional[str] = None
    department: Optional[str] = None
    category: Optional[str] = None
    north_star_gain: Optional[float] = None
    active_overall_score: Optional[float] = None
    mandate_reason: Optional[str] = None
    bundle_key: Optional[str] = None
    dependency_status: Optional[str] = None
    notes: Optional[str] = None
    run_status: Optional[str] = None
    updated_source: Optional[str] = None
    updated_at: Optional[str] = None


class OptGapAlertRow(BaseModel):
    """Optimization Center Gaps_and_alerts tab row."""

    model_config = ConfigDict(extra="ignore")

    country: str
    kpi_key: str
    target: Optional[float] = None
    achieved: Optional[float] = None
    gap: Optional[float] = None
    severity: Optional[str] = None
    notes: Optional[str] = None
    recommendation: Optional[str] = None
    run_status: Optional[str] = None
    updated_source: Optional[str] = None
    updated_at: Optional[str] = None


# Central Backlog PM-editable columns mapping (used by protected ranges logic)
# Keys are exact header names in CENTRAL_BACKLOG_HEADER that are editable by users.
CENTRAL_EDITABLE_FIELDS: List[str] = [
    "Title",
    "Requesting Team",
    "Requester Name",
    "Requester Email",
    "Country",
    "Product Area",
    "Department",
    "Lifecycle Status",
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
