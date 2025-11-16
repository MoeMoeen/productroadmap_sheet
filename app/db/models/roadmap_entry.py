from sqlalchemy import Column, Float, ForeignKey, Integer, String, Boolean
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

    # Priority and scheduling info for this roadmap
    priority_rank = Column(Integer, nullable=True)  # 1 = highest priority
    planned_quarter = Column(String(20), nullable=True)  # e.g. "2025-Q1"
    planned_year = Column(Integer, nullable=True)

    # Flags for optimization decisions
    is_selected = Column(Boolean, nullable=False, default=False)
    is_locked_in = Column(Boolean, nullable=False, default=False)
    is_mandatory_in_this_roadmap = Column(Boolean, nullable=False, default=False)

    # Scores used in THIS roadmap
    value_score_used = Column(Float, nullable=True)
    effort_score_used = Column(Float, nullable=True)
    overall_score_used = Column(Float, nullable=True)

    # Optimization provenance
    optimization_run_id = Column(String(100), nullable=True)
    scenario_label = Column(String(100), nullable=True)

    roadmap = relationship("Roadmap", back_populates="entries")
    initiative = relationship("Initiative", back_populates="roadmap_entries")