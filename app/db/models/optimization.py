# productroadmap_sheet_project/app/db/models/optimization.py

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class OrganizationMetricConfig(Base):
    """Authoritative KPI registry from ProductOps Metrics_Config."""

    __tablename__ = "organization_metric_configs"

    id = Column(Integer, primary_key=True, index=True)
    kpi_key = Column(String(100), nullable=False, unique=True, index=True)
    kpi_name = Column(String(255), nullable=False)
    kpi_level = Column(String(50), nullable=False)  # north_star or strategic
    unit = Column(String(50), nullable=True)
    metadata_json = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OptimizationScenario(Base):
    """Scenario config for optimization runs."""

    __tablename__ = "optimization_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    period_key = Column(String(100), nullable=True, index=True)
    objective_mode = Column(String(50), nullable=False)
    objective_weights_json = Column(JSON, nullable=True)

    capacity_total_tokens = Column(Float, nullable=True)
    capacity_by_market_json = Column(JSON, nullable=True)
    capacity_by_department_json = Column(JSON, nullable=True)

    created_by_user_id = Column(String(100), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    constraint_sets = relationship(
        "OptimizationConstraintSet", back_populates="scenario", cascade="all, delete-orphan"
    )
    runs = relationship("OptimizationRun", back_populates="scenario")
    portfolios = relationship("Portfolio", back_populates="scenario")


class OptimizationConstraintSet(Base):
    """Compiled constraints and targets for a scenario."""

    __tablename__ = "optimization_constraint_sets"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("optimization_scenarios.id"), nullable=True)
    name = Column(String(255), nullable=False)

    floors_json = Column(JSON, nullable=True)
    caps_json = Column(JSON, nullable=True)
    targets_json = Column(JSON, nullable=True)
    mandatory_initiatives_json = Column(JSON, nullable=True)
    bundles_json = Column(JSON, nullable=True)
    exclusions_json = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    scenario = relationship("OptimizationScenario", back_populates="constraint_sets")
    runs = relationship("OptimizationRun", back_populates="constraint_set")


class OptimizationRun(Base):
    """Execution record for optimization jobs."""

    __tablename__ = "optimization_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), nullable=False, unique=True, index=True)

    scenario_id = Column(Integer, ForeignKey("optimization_scenarios.id"), nullable=False)
    constraint_set_id = Column(Integer, ForeignKey("optimization_constraint_sets.id"), nullable=True)

    status = Column(String(20), nullable=False, default="pending", index=True)
    requested_by_email = Column(String(255), nullable=True)
    requested_by_ui = Column(String(50), nullable=True)

    inputs_snapshot_json = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=True)
    solver_name = Column(String(50), nullable=True)
    solver_version = Column(String(50), nullable=True)
    error_text = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    scenario = relationship("OptimizationScenario", back_populates="runs")
    constraint_set = relationship("OptimizationConstraintSet", back_populates="runs")
    portfolio = relationship("Portfolio", back_populates="run", uselist=False)


class Portfolio(Base):
    """Persisted portfolio results for a scenario/run."""

    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("optimization_scenarios.id"), nullable=False)
    optimization_run_id = Column(Integer, ForeignKey("optimization_runs.id"), nullable=True)

    name = Column(String(255), nullable=False)
    is_baseline = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    scenario = relationship("OptimizationScenario", back_populates="portfolios")
    run = relationship("OptimizationRun", back_populates="portfolio")
    items = relationship("PortfolioItem", back_populates="portfolio", cascade="all, delete-orphan")
    published_roadmaps = relationship("Roadmap", back_populates="source_portfolio", cascade="all, delete-orphan")


class PortfolioItem(Base):
    """Membership of initiatives in a portfolio."""

    __tablename__ = "portfolio_items"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "initiative_id", name="uq_portfolio_items_portfolio_initiative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False, index=True)

    selected = Column(Boolean, nullable=False, default=False)
    allocated_tokens = Column(Float, nullable=True)
    rank = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    source = Column(String(50), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    portfolio = relationship("Portfolio", back_populates="items")
    published_roadmap_entries = relationship("RoadmapEntry", back_populates="source_portfolio_item")
    initiative = relationship("Initiative", back_populates="portfolio_items")

