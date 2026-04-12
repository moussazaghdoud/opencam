"""AI Enrichment model — stores narration + suspicion data for events.

Separate table from events — the core events table is never modified.
This is a read-only enrichment layer.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class AIEnrichment(Base):
    __tablename__ = "ai_enrichments"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), unique=True, index=True, nullable=False)
    narration = Column(String, nullable=False)
    suspicion_score = Column(Float, default=0.0)
    suspicion_label = Column(String, default="normal")  # normal | noteworthy | unusual | suspicious
    suspicion_reason = Column(String, nullable=True)
    powered_by = Column(String, default="rules")  # "claude" | "rules"
    created_at = Column(DateTime, server_default=func.now())
