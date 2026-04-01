from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    name = Column(String, nullable=False)
    object_type = Column(String, default="person")  # person, vehicle, any
    trigger = Column(String, default="enter")  # enter, exit, loiter, count_above
    threshold = Column(Integer, default=1)  # For count-based or loiter seconds
    schedule_start = Column(String, nullable=True)  # HH:MM format
    schedule_end = Column(String, nullable=True)  # HH:MM format
    schedule_days = Column(JSON, default=[0, 1, 2, 3, 4, 5, 6])  # 0=Mon, 6=Sun
    alert_email = Column(String, nullable=True)
    alert_webhook = Column(String, nullable=True)
    enabled = Column(Boolean, default=True)
    cooldown_seconds = Column(Integer, default=60)
    created_at = Column(DateTime, server_default=func.now())

    zone = relationship("Zone", back_populates="rules")
