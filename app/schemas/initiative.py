from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InitiativeBase(BaseModel):
    title: str = Field(..., min_length=3)

    source_sheet_id: str | None = None
    source_sheet_key: str | None = None
    source_tab_name: str | None = None
    source_row_number: int | None = None

    department: str | None = None
    requesting_team: str | None = None
    requester_name: str | None = None
    requester_email: str | None = None
    country: str | None = None
    product_area: str | None = None
    market: str | None = None
    category: str | None = None

    problem_statement: str | None = None
    hypothesis: str | None = None
    llm_summary: str | None = None
    llm_summary_json: Any | None = None

    customer_segment: str | None = None
    initiative_type: str | None = None
    strategic_priority_coefficient: float = 1.0

    immediate_kpi_key: str | None = None
    kpi_contribution_json: Any | None = None
    kpi_contribution_computed_json: Any | None = None
    kpi_contribution_source: str | None = None

    rice_reach: float | None = None
    rice_impact: float | None = None
    rice_confidence: float | None = None
    rice_effort: float | None = None
    wsjf_business_value: float | None = None
    wsjf_time_criticality: float | None = None
    wsjf_risk_reduction: float | None = None
    wsjf_job_size: float | None = None

    effort_tshirt_size: str | None = None
    effort_engineering_days: float | None = None
    effort_other_teams_days: float | None = None
    infra_cost_estimate: float | None = None
    engineering_tokens: float | None = None
    engineering_tokens_mvp: float | None = None
    engineering_tokens_full: float | None = None
    scope_mode: str | None = None

    dependencies_initiatives: list[str] | None = None
    dependencies_others: str | None = None
    program_key: str | None = None
    risk_level: str | None = None
    risk_description: str | None = None
    time_sensitivity_score: float | None = None
    earliest_start_date: date | None = None
    latest_finish_date: date | None = None
    deadline_date: date | None = None

    is_optimization_candidate: bool = False
    candidate_period_key: str | None = None

    status: str = "active"
    lifecycle_status: str = "new"
    is_archived: bool = False
    archived_at: datetime | None = None
    archived_reason: str | None = None
    updated_source: str | None = None
    scoring_updated_source: str | None = None
    scoring_updated_at: datetime | None = None
    created_by_user_id: str | None = None

    active_scoring_framework: str | None = None
    value_score: float | None = None
    effort_score: float | None = None
    overall_score: float | None = None
    rice_value_score: float | None = None
    rice_effort_score: float | None = None
    rice_overall_score: float | None = None
    wsjf_value_score: float | None = None
    wsjf_effort_score: float | None = None
    wsjf_overall_score: float | None = None
    math_value_score: float | None = None
    math_effort_score: float | None = None
    math_overall_score: float | None = None
    score_llm_suggested: bool = False
    score_approved_by_user: bool = False
    use_math_model: bool = False


class InitiativeCreate(InitiativeBase):
    pass


class InitiativeUpdate(BaseModel):
    title: str | None = None

    source_sheet_id: str | None = None
    source_sheet_key: str | None = None
    source_tab_name: str | None = None
    source_row_number: int | None = None

    department: str | None = None
    requesting_team: str | None = None
    requester_name: str | None = None
    requester_email: str | None = None
    country: str | None = None
    product_area: str | None = None
    market: str | None = None
    category: str | None = None

    problem_statement: str | None = None
    hypothesis: str | None = None
    llm_summary: str | None = None
    llm_summary_json: Any | None = None

    customer_segment: str | None = None
    initiative_type: str | None = None
    strategic_priority_coefficient: float | None = None

    immediate_kpi_key: str | None = None
    kpi_contribution_json: Any | None = None
    kpi_contribution_computed_json: Any | None = None
    kpi_contribution_source: str | None = None

    rice_reach: float | None = None
    rice_impact: float | None = None
    rice_confidence: float | None = None
    rice_effort: float | None = None
    wsjf_business_value: float | None = None
    wsjf_time_criticality: float | None = None
    wsjf_risk_reduction: float | None = None
    wsjf_job_size: float | None = None

    effort_tshirt_size: str | None = None
    effort_engineering_days: float | None = None
    effort_other_teams_days: float | None = None
    infra_cost_estimate: float | None = None
    engineering_tokens: float | None = None
    engineering_tokens_mvp: float | None = None
    engineering_tokens_full: float | None = None
    scope_mode: str | None = None

    dependencies_initiatives: list[str] | None = None
    dependencies_others: str | None = None
    program_key: str | None = None
    risk_level: str | None = None
    risk_description: str | None = None
    time_sensitivity_score: float | None = None
    earliest_start_date: date | None = None
    latest_finish_date: date | None = None
    deadline_date: date | None = None

    is_optimization_candidate: bool | None = None
    candidate_period_key: str | None = None

    status: str | None = None
    lifecycle_status: str | None = None
    is_archived: bool | None = None
    archived_at: datetime | None = None
    archived_reason: str | None = None
    updated_source: str | None = None
    scoring_updated_source: str | None = None
    scoring_updated_at: datetime | None = None
    created_by_user_id: str | None = None

    active_scoring_framework: str | None = None
    value_score: float | None = None
    effort_score: float | None = None
    overall_score: float | None = None
    rice_value_score: float | None = None
    rice_effort_score: float | None = None
    rice_overall_score: float | None = None
    wsjf_value_score: float | None = None
    wsjf_effort_score: float | None = None
    wsjf_overall_score: float | None = None
    math_value_score: float | None = None
    math_effort_score: float | None = None
    math_overall_score: float | None = None
    score_llm_suggested: bool | None = None
    score_approved_by_user: bool | None = None
    use_math_model: bool | None = None


class InitiativeRead(InitiativeBase):
    id: int
    initiative_key: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
