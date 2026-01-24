# productroadmap_sheet_project/app/db/models/scoring.py

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship
from app.db.base import Base


class InitiativeMathModel(Base):
    """
    Stores mathematical models for initiatives.
    Multiple models per initiative supported (1:N relationship).
    Each model can target a specific KPI via target_kpi_key.
    """

    __tablename__ = "initiative_math_models"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id", ondelete="CASCADE"), nullable=False, index=True)

    framework = Column(String(50), nullable=False, default="MATH_MODEL", index=True)
    model_name = Column(String(150), nullable=True)
    formula_text = Column(Text, nullable=False)
    metric_chain_text = Column(Text, nullable=True)
    metric_chain_json = Column(JSON, nullable=True)  # Parsed version of metric_chain_text
    parameters_json = Column(JSON, nullable=True)  # e.g. {"traffic": {...}, "uplift": {...}}
    assumptions_text = Column(Text, nullable=True)
    model_description_free_text = Column(Text, nullable=True)

    # Multi-model support fields
    target_kpi_key = Column(String(100), nullable=True)  # Which KPI this model targets
    is_primary = Column(Boolean, nullable=False, default=False)  # Representative score for displays
    computed_score = Column(Float, nullable=True)  # Score computed by this model

    suggested_by_llm = Column(Boolean, nullable=False, default=False)
    approved_by_user = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    initiative = relationship(
        "Initiative",
        back_populates="math_models",
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