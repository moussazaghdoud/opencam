from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    name = Column(String, nullable=False)
    zone_type = Column(String, default="restricted")  # restricted, counting, monitoring
    points = Column(JSON, nullable=False)  # List of [x, y] normalized coordinates
    color = Column(String, default="#ff0000")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    camera = relationship("Camera", back_populates="zones")
    rules = relationship("Rule", back_populates="zone", cascade="all, delete-orphan")
