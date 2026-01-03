# productroadmap_sheet_project/app/db/models/roadmap.py

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class Roadmap(Base):
    __tablename__ = "roadmaps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    timeframe_label = Column(String(100), nullable=True)  # e.g., "2025 H1"
    owner_team = Column(String(100), nullable=True)

    # Portfolio lineage (roadmap was published from this portfolio)
    source_portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=True)

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

    entries = relationship("RoadmapEntry", back_populates="roadmap", cascade="all, delete-orphan")
    source_portfolio = relationship("Portfolio")