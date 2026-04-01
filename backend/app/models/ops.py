from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, JSON, func

from app.core.database import Base


class CountingLineModel(Base):
    __tablename__ = "counting_lines"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    name = Column(String, nullable=False)
    point_a = Column(JSON, nullable=False)  # [x, y] normalized 0-1
    point_b = Column(JSON, nullable=False)  # [x, y] normalized 0-1
    direction = Column(String, default="down_is_in")  # down_is_in, up_is_in, left_is_in, right_is_in
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class CountingRecord(Base):
    __tablename__ = "counting_records"

    id = Column(Integer, primary_key=True, index=True)
    line_id = Column(Integer, ForeignKey("counting_lines.id"), nullable=False)
    direction = Column(String, nullable=False)  # "in" or "out"
    object_type = Column(String, default="person")
    timestamp = Column(DateTime, server_default=func.now())


class DockSession(Base):
    __tablename__ = "dock_sessions"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    zone_name = Column(String, nullable=False)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    peak_workers = Column(Integer, default=0)
    status = Column(String, default="active")  # active, completed
