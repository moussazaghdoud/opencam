from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ZoneCreate(BaseModel):
    camera_id: int
    name: str
    zone_type: str = "restricted"
    points: list[list[float]]  # [[x, y], ...]
    color: str = "#ff0000"
    enabled: bool = True


class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    zone_type: Optional[str] = None
    points: Optional[list[list[float]]] = None
    color: Optional[str] = None
    enabled: Optional[bool] = None


class ZoneOut(BaseModel):
    id: int
    camera_id: int
    name: str
    zone_type: str
    points: list[list[float]]
    color: str
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True
