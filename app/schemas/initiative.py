from datetime import date, datetime
from typing import Optional, Any, List
from pydantic import BaseModel, Field


class InitiativeBase(BaseModel):
    title: str = Field(..., min_length=3)

    requesting_team: Optional[str] = None
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    country: Optional[str] = None
    product_area: Optional[str] = None

    problem_statement: Optional[str] = None
    current_pain: Optional[str] = None
    desired_outcome: Optional[str] = None
    target_metrics: Optional[str] = None
    hypothesis: Optional[str] = None

    strategic_theme: Optional[str] = None
    customer_segment: Optional[str] = None
    initiative_type: Optional[str] = None
    strategic_priority_coefficient: float = 1.0
    linked_objectives: Optional[Any] = None

    expected_impact_description: Optional[str] = None
    impact_metric: Optional[str] = None
    impact_unit: Optional[str] = None
    impact_low: Optional[float] = None
    impact_expected: Optional[float] = None
    impact_high: Optional[float] = None

    effort_tshirt_size: Optional[str] = None
    effort_engineering_days: Optional[float] = None
    effort_other_teams_days: Optional[float] = None
    infra_cost_estimate: Optional[float] = None
    total_cost_estimate: Optional[float] = None

    # Dependencies / risk
    dependencies_initiatives: Optional[List[str]] = None  # initiative_keys; switch to List[int] if using IDs
    dependencies_others: Optional[str] = None
    is_mandatory: bool = False
    risk_level: Optional[str] = None
    risk_description: Optional[str] = None
    time_sensitivity: Optional[str] = None
    deadline_date: Optional[date] = None

    status: str = "new"
    active_scoring_framework: Optional[str] = None

    value_score: Optional[float] = None
    effort_score: Optional[float] = None
    overall_score: Optional[float] = None
    score_llm_suggested: bool = False
    score_approved_by_user: bool = False

    use_math_model: bool = False
    llm_notes: Optional[str] = None


class InitiativeCreate(InitiativeBase):
    pass


class InitiativeUpdate(BaseModel):
    title: Optional[str] = None

    requesting_team: Optional[str] = None
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    country: Optional[str] = None
    product_area: Optional[str] = None

    problem_statement: Optional[str] = None
    current_pain: Optional[str] = None
    desired_outcome: Optional[str] = None
    target_metrics: Optional[str] = None
    hypothesis: Optional[str] = None

    strategic_theme: Optional[str] = None
    customer_segment: Optional[str] = None
    initiative_type: Optional[str] = None
    strategic_priority_coefficient: Optional[float] = None
    linked_objectives: Optional[Any] = None

    expected_impact_description: Optional[str] = None
    impact_metric: Optional[str] = None
    impact_unit: Optional[str] = None
    impact_low: Optional[float] = None
    impact_expected: Optional[float] = None
    impact_high: Optional[float] = None

    effort_tshirt_size: Optional[str] = None
    effort_engineering_days: Optional[float] = None
    effort_other_teams_days: Optional[float] = None
    infra_cost_estimate: Optional[float] = None
    total_cost_estimate: Optional[float] = None

    dependencies_initiatives: Optional[List[str]] = None
    dependencies_others: Optional[str] = None
    is_mandatory: Optional[bool] = None
    risk_level: Optional[str] = None
    risk_description: Optional[str] = None
    time_sensitivity: Optional[str] = None
    deadline_date: Optional[date] = None

    status: Optional[str] = None
    active_scoring_framework: Optional[str] = None

    value_score: Optional[float] = None
    effort_score: Optional[float] = None
    overall_score: Optional[float] = None
    score_llm_suggested: Optional[bool] = None
    score_approved_by_user: Optional[bool] = None

    use_math_model: Optional[bool] = None
    llm_notes: Optional[str] = None


class InitiativeRead(InitiativeBase):
    id: int
    initiative_key: str
    source_sheet_id: Optional[str] = None
    source_tab_name: Optional[str] = None
    source_row_number: Optional[int] = None

    llm_summary: Optional[str] = None
    missing_fields: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[str] = None
    math_model_id: Optional[int] = None

    model_config = {"from_attributes": True}