from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RuleCreate(BaseModel):
    zone_id: int
    name: str
    object_type: str = "person"
    trigger: str = "enter"
    threshold: int = 1
    schedule_start: Optional[str] = None
    schedule_end: Optional[str] = None
    schedule_days: list[int] = [0, 1, 2, 3, 4, 5, 6]
    alert_email: Optional[str] = None
    alert_webhook: Optional[str] = None
    enabled: bool = True
    cooldown_seconds: int = 60


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    object_type: Optional[str] = None
    trigger: Optional[str] = None
    threshold: Optional[int] = None
    schedule_start: Optional[str] = None
    schedule_end: Optional[str] = None
    schedule_days: Optional[list[int]] = None
    alert_email: Optional[str] = None
    alert_webhook: Optional[str] = None
    enabled: Optional[bool] = None
    cooldown_seconds: Optional[int] = None


class RuleOut(BaseModel):
    id: int
    zone_id: int
    name: str
    object_type: str
    trigger: str
    threshold: int
    schedule_start: Optional[str]
    schedule_end: Optional[str]
    schedule_days: list[int]
    alert_email: Optional[str]
    alert_webhook: Optional[str]
    enabled: bool
    cooldown_seconds: int
    created_at: datetime

    class Config:
        from_attributes = True
