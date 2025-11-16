from typing import Optional
from pydantic import BaseModel


class RoadmapEntryBase(BaseModel):
    roadmap_id: int
    initiative_id: int

    priority_rank: Optional[int] = None
    planned_quarter: Optional[str] = None
    planned_year: Optional[int] = None

    is_selected: bool = False
    is_locked_in: bool = False
    is_mandatory_in_this_roadmap: bool = False

    value_score_used: Optional[float] = None
    effort_score_used: Optional[float] = None
    overall_score_used: Optional[float] = None

    optimization_run_id: Optional[str] = None
    scenario_label: Optional[str] = None


class RoadmapEntryCreate(RoadmapEntryBase):
    pass


class RoadmapEntryRead(RoadmapEntryBase):
    id: int

    model_config = {"from_attributes": True}