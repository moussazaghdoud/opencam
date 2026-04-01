from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CameraCreate(BaseModel):
    name: str
    rtsp_url: str
    location: str = ""
    enabled: bool = True


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    location: Optional[str] = None
    enabled: Optional[bool] = None


class CameraOut(BaseModel):
    id: int
    name: str
    rtsp_url: str
    location: str
    enabled: bool
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
