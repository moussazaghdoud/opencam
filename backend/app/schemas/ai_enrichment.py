from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AIEnrichmentOut(BaseModel):
    event_id: int
    narration: str
    suspicion_score: float
    suspicion_label: str  # normal | noteworthy | unusual | suspicious
    suspicion_reason: Optional[str]
    powered_by: str  # "claude" | "rules"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AIBatchRequest(BaseModel):
    event_ids: list[int]
    max: int = 20
