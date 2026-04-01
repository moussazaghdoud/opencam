from sqlalchemy import Column, Integer, String, DateTime, func
from app.core.database import Base


class KnownFace(Base):
    __tablename__ = "known_faces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    role = Column(String, default="")  # employee, vip, visitor, blocked
    photo_path = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
