from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EventOut(BaseModel):
    id: int
    camera_id: int
    rule_id: Optional[int]
    event_type: str
    object_type: str
    confidence: float
    snapshot_path: Optional[str]
    clip_path: Optional[str]
    bbox: Optional[list[float]]
    zone_name: Optional[str]
    acknowledged: bool
    false_alarm: bool
    created_at: datetime

    class Config:
        from_attributes = True


class EventAcknowledge(BaseModel):
    acknowledged: bool = True
    false_alarm: bool = False
