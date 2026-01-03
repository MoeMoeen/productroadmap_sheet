# productroadmap_sheet_project/app/db/models/initiative.py

from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Initiative(Base):
    __tablename__ = "initiatives"

    id = Column(Integer, primary_key=True, index=True)

    # A. Identity & source
    initiative_key = Column(String(50), unique=True, index=True, nullable=False)
    source_sheet_id = Column(String(255), nullable=True)
    source_tab_name = Column(String(255), nullable=True)
    source_row_number = Column(Integer, nullable=True)

    # B. Ownership & requester
    title = Column(String(255), nullable=False)
    requesting_team = Column(String(100), nullable=True)
    requester_name = Column(String(255), nullable=True)
    requester_email = Column(String(255), nullable=True)
    country = Column(String(50), nullable=True)
    product_area = Column(String(100), nullable=True)
    market = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)

    # C. Problem & context
    problem_statement = Column(Text, nullable=True)
    hypothesis = Column(Text, nullable=True)
    llm_summary = Column(Text, nullable=True)

    # D. Strategic alignment & classification
    customer_segment = Column(String(100), nullable=True)
    initiative_type = Column(String(100), nullable=True)
    strategic_priority_coefficient = Column(Float, nullable=False, default=1.0)

    # D. KPI alignment and metric chain
    immediate_kpi_key = Column(String(100), nullable=True)
    metric_chain_json = Column(JSON, nullable=True)
    kpi_contribution_json = Column(JSON, nullable=True)

    # E. Framework-specific scoring parameters (unified naming: <framework>_<param>)
    # RICE framework parameters
    rice_reach = Column(Float, nullable=True)
    rice_impact = Column(Float, nullable=True)
    rice_confidence = Column(Float, nullable=True)
    rice_effort = Column(Float, nullable=True)
    
    # WSJF framework parameters
    wsjf_business_value = Column(Float, nullable=True)
    wsjf_time_criticality = Column(Float, nullable=True)
    wsjf_risk_reduction = Column(Float, nullable=True)
    wsjf_job_size = Column(Float, nullable=True)

    # F. Effort & cost (high-level)
    effort_tshirt_size = Column(String(10), nullable=True)  # XS/S/M/L/XL
    effort_engineering_days = Column(Float, nullable=True)  # Shared across frameworks
    effort_other_teams_days = Column(Float, nullable=True)
    infra_cost_estimate = Column(Float, nullable=True)
    engineering_tokens = Column(Float, nullable=True)
    engineering_tokens_mvp = Column(Float, nullable=True)
    engineering_tokens_full = Column(Float, nullable=True)
    scope_mode = Column(String(50), nullable=True)

    # G. Risk, dependencies, constraints
    dependencies_initiatives = Column(JSON, nullable=True)  # list of initiative_keys (or ids)
    dependencies_others = Column(Text, nullable=True)
    is_mandatory = Column(Boolean, nullable=False, default=False)
    mandate_reason = Column(Text, nullable=True)
    program_key = Column(String(100), nullable=True)
    bundle_key = Column(String(100), nullable=True)
    prerequisite_keys = Column(JSON, nullable=True)
    exclusion_keys = Column(JSON, nullable=True)
    synergy_group_keys = Column(JSON, nullable=True)
    risk_level = Column(String(50), nullable=True)
    risk_description = Column(Text, nullable=True)
    time_sensitivity_score = Column(Float, nullable=True)
    earliest_start_date = Column(Date, nullable=True)
    latest_finish_date = Column(Date, nullable=True)
    deadline_date = Column(Date, nullable=True)

    # H. Optimization eligibility
    is_optimization_candidate = Column(Boolean, nullable=False, default=False)
    candidate_period_key = Column(String(50), nullable=True, index=True)

    # I. Lifecycle & workflow
    status = Column(String(50), nullable=False, default="new")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    # Source that last updated this row (e.g., "intake", "backlog", "system")
    updated_source = Column(String(100), nullable=True)
    scoring_updated_source = Column(String(50), nullable=True)
    scoring_updated_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(100), nullable=True)

    # J. Scoring summary (framework-agnostic & per-framework)
    # Active framework scores (currently selected for display/use)
    active_scoring_framework = Column(String(50), nullable=True)
    value_score = Column(Float, nullable=True)
    effort_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    
    # Per-framework scores (stored for all frameworks; allow comparison and switching)
    # RICE framework scores
    rice_value_score = Column(Float, nullable=True)
    rice_effort_score = Column(Float, nullable=True)
    rice_overall_score = Column(Float, nullable=True)
    
    # WSJF framework scores
    wsjf_value_score = Column(Float, nullable=True)
    wsjf_effort_score = Column(Float, nullable=True)
    wsjf_overall_score = Column(Float, nullable=True)

    # Math Model framework scores
    math_value_score = Column(Float, nullable=True)
    math_effort_score = Column(Float, nullable=True)
    math_overall_score = Column(Float, nullable=True)
    
    score_llm_suggested = Column(Boolean, nullable=False, default=False)
    score_approved_by_user = Column(Boolean, nullable=False, default=False)

    # J. LLM & math-model hooks
    use_math_model = Column(Boolean, nullable=False, default=False)
    math_model_id = Column(Integer, ForeignKey("initiative_math_models.id"), nullable=True)

    # Relationships
    math_model = relationship(
        "InitiativeMathModel",
        back_populates="initiative",
        uselist=False,
    )
    roadmap_entries = relationship("RoadmapEntry", back_populates="initiative")
    scores = relationship("InitiativeScore", back_populates="initiative")
    params = relationship("InitiativeParam", back_populates="initiative")
    portfolio_items = relationship("PortfolioItem", back_populates="initiative")
