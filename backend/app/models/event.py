from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, JSON, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    rule_id = Column(Integer, nullable=True)
    event_type = Column(String, nullable=False)  # intrusion, zone_entry, loiter, count
    object_type = Column(String, default="person")
    confidence = Column(Float, default=0.0)
    snapshot_path = Column(String, nullable=True)
    clip_path = Column(String, nullable=True)
    bbox = Column(JSON, nullable=True)  # [x1, y1, x2, y2]
    zone_name = Column(String, nullable=True)
    acknowledged = Column(Boolean, default=False)
    false_alarm = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    camera = relationship("Camera", back_populates="events")
