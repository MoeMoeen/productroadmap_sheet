from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship
from app.db.base import Base


class InitiativeMathModel(Base):
    """
    Stores the full mathematical model for an initiative.
    Relationship to Initiative is via Initiative.math_model_id -> InitiativeMathModel.id
    """

    __tablename__ = "initiative_math_models"

    id = Column(Integer, primary_key=True, index=True)

    formula_text = Column(Text, nullable=False)
    parameters_json = Column(JSON, nullable=True)  # e.g. {"traffic": {...}, "uplift": {...}}
    assumptions_text = Column(Text, nullable=True)

    suggested_by_llm = Column(Boolean, nullable=False, default=False)
    approved_by_user = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    initiative = relationship(
        "Initiative",
        back_populates="math_model",
        uselist=False,
        primaryjoin="Initiative.math_model_id==InitiativeMathModel.id",
    )


class InitiativeScore(Base):
    """
    Optional scoring history table (per framework / per run).
    """

    __tablename__ = "initiative_scores"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False, index=True)

    framework_name = Column(String(50), nullable=False)  # e.g., "RICE", "MATH_MODEL"
    value_score = Column(Float, nullable=True)
    effort_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)

    inputs_json = Column(JSON, nullable=True)  # raw inputs used to compute scores
    components_json = Column(JSON, nullable=True)  # intermediate components for audit
    warnings_json = Column(JSON, nullable=True)  # warnings from scoring engine
    llm_suggested = Column(Boolean, nullable=False, default=False)
    approved_by_user = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    initiative = relationship("Initiative", back_populates="scores")