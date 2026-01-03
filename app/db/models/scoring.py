# productroadmap_sheet_project/app/db/models/scoring.py

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

    framework = Column(String(50), nullable=False, default="MATH_MODEL", index=True)
    model_name = Column(String(150), nullable=True)
    formula_text = Column(Text, nullable=False)
    parameters_json = Column(JSON, nullable=True)  # e.g. {"traffic": {...}, "uplift": {...}}
    assumptions_text = Column(Text, nullable=True)
    model_description_free_text = Column(Text, nullable=True)

    suggested_by_llm = Column(Boolean, nullable=False, default=False)
    approved_by_user = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    initiative = relationship(
        "Initiative",
        back_populates="math_model",
        uselist=False,
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


class InitiativeParam(Base):
    """
    Normalized parameter table: one row per (initiative, framework, param_name).
    Supports RICE/WSJF/MATH_MODEL frameworks uniformly.
    """

    __tablename__ = "initiative_params"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False, index=True)

    framework = Column(String(50), nullable=False, index=True)  # e.g., "MATH_MODEL", "RICE"
    param_name = Column(String(100), nullable=False, index=True)  # internal snake_case

    # Display & metadata
    param_display = Column(String(150), nullable=True)
    description = Column(Text, nullable=True)
    unit = Column(String(50), nullable=True)

    # Values and ranges
    value = Column(Float, nullable=True)
    min = Column(Float, nullable=True)
    max = Column(Float, nullable=True)

    source = Column(String(50), nullable=True)  # PM, Analytics, Finance, Eng, LLM
    approved = Column(Boolean, nullable=False, default=False)
    is_auto_seeded = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    initiative = relationship("Initiative", back_populates="params")