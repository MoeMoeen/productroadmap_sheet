# productroadmap_sheet_project/app/db/models/roadmap_entry.py

from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class RoadmapEntry(Base):
    """
    Link between Roadmap and Initiative, with metadata per roadmap.
    """

    __tablename__ = "roadmap_entries"

    id = Column(Integer, primary_key=True, index=True)

    roadmap_id = Column(Integer, ForeignKey("roadmaps.id"), nullable=False, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False, index=True)
    source_portfolio_item_id = Column(Integer, ForeignKey("portfolio_items.id"), nullable=True, index=True)

    # Priority and scheduling info for this roadmap
    priority_rank = Column(Integer, nullable=True)  # 1 = highest priority
    planned_quarter = Column(String(20), nullable=True)  # e.g. "2025-Q1"
    planned_year = Column(Integer, nullable=True)

    # Roadmap-specific flags and notes
    is_locked_in = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)

    roadmap = relationship("Roadmap", back_populates="entries")
    initiative = relationship("Initiative", back_populates="roadmap_entries")
    source_portfolio_item = relationship("PortfolioItem")