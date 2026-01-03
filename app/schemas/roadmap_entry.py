from typing import Optional
from pydantic import BaseModel


class RoadmapEntryBase(BaseModel):
    roadmap_id: int
    initiative_id: int
    source_portfolio_item_id: Optional[int] = None

    priority_rank: Optional[int] = None
    planned_quarter: Optional[str] = None
    planned_year: Optional[int] = None

    is_locked_in: bool = False
    notes: Optional[str] = None


class RoadmapEntryCreate(RoadmapEntryBase):
    pass


class RoadmapEntryRead(RoadmapEntryBase):
    id: int

    model_config = {"from_attributes": True}