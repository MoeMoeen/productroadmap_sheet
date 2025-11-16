from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class RoadmapBase(BaseModel):
    name: str
    description: Optional[str] = None
    timeframe_label: Optional[str] = None
    owner_team: Optional[str] = None


class RoadmapCreate(RoadmapBase):
    pass


class RoadmapRead(RoadmapBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}