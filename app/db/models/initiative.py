from datetime import datetime
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

    # C. Problem & context
    problem_statement = Column(Text, nullable=True)
    current_pain = Column(Text, nullable=True)
    desired_outcome = Column(Text, nullable=True)
    target_metrics = Column(Text, nullable=True)
    hypothesis = Column(Text, nullable=True)
    llm_summary = Column(Text, nullable=True)

    # D. Strategic alignment & classification
    strategic_theme = Column(String(100), nullable=True)
    customer_segment = Column(String(100), nullable=True)
    initiative_type = Column(String(100), nullable=True)
    strategic_priority_coefficient = Column(Float, nullable=False, default=1.0)
    linked_objectives = Column(JSON, nullable=True)  # free-form for now

    # E. Impact & value modeling (high-level)
    expected_impact_description = Column(Text, nullable=True)
    impact_metric = Column(String(100), nullable=True)
    impact_unit = Column(String(20), nullable=True)
    impact_low = Column(Float, nullable=True)
    impact_expected = Column(Float, nullable=True)
    impact_high = Column(Float, nullable=True)

    # F. Effort & cost (high-level)
    effort_tshirt_size = Column(String(10), nullable=True)  # XS/S/M/L/XL
    effort_engineering_days = Column(Float, nullable=True)
    effort_other_teams_days = Column(Float, nullable=True)
    infra_cost_estimate = Column(Float, nullable=True)
    total_cost_estimate = Column(Float, nullable=True)

    # G. Risk, dependencies, constraints
    dependencies_initiatives = Column(JSON, nullable=True)  # list of initiative_keys (or ids)
    dependencies_others = Column(Text, nullable=True)
    is_mandatory = Column(Boolean, nullable=False, default=False)
    risk_level = Column(String(50), nullable=True)
    risk_description = Column(Text, nullable=True)
    time_sensitivity = Column(String(50), nullable=True)
    deadline_date = Column(Date, nullable=True)

    # H. Lifecycle & workflow
    status = Column(String(50), nullable=False, default="new")
    missing_fields = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Source that last updated this row (e.g., "intake", "backlog", "system")
    updated_source = Column(String(20), nullable=True)
    created_by_user_id = Column(String(100), nullable=True)

    # I. Scoring summary (framework-agnostic)
    active_scoring_framework = Column(String(50), nullable=True)
    value_score = Column(Float, nullable=True)
    effort_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    score_llm_suggested = Column(Boolean, nullable=False, default=False)
    score_approved_by_user = Column(Boolean, nullable=False, default=False)

    # J. LLM & math-model hooks
    use_math_model = Column(Boolean, nullable=False, default=False)
    math_model_id = Column(Integer, ForeignKey("initiative_math_models.id"), nullable=True)
    llm_notes = Column(Text, nullable=True)

    # Relationships
    math_model = relationship(
        "InitiativeMathModel",
        back_populates="initiative",
        uselist=False,
        primaryjoin="Initiative.math_model_id==InitiativeMathModel.id",
    )
    roadmap_entries = relationship("RoadmapEntry", back_populates="initiative")
    scores = relationship("InitiativeScore", back_populates="initiative")