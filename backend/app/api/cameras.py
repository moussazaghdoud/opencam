import cv2
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.camera import Camera
from app.schemas.camera import CameraCreate, CameraUpdate, CameraOut
from app.services.stream_processor import stream_manager

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("/", response_model=list[CameraOut])
def list_cameras(db: Session = Depends(get_db)):
    return db.query(Camera).order_by(Camera.id).all()


@router.post("/", response_model=CameraOut)
async def create_camera(data: CameraCreate, db: Session = Depends(get_db)):
    camera = Camera(**data.model_dump())
    db.add(camera)
    db.commit()
    db.refresh(camera)

    if camera.enabled:
        await stream_manager.start_camera(camera.id, camera.rtsp_url, camera.name)

    return camera


@router.get("/{camera_id}", response_model=CameraOut)
def get_camera(camera_id: int, db: Session = Depends(get_db)):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(404, "Camera not found")
    return camera


@router.patch("/{camera_id}", response_model=CameraOut)
async def update_camera(camera_id: int, data: CameraUpdate, db: Session = Depends(get_db)):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(404, "Camera not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(camera, key, value)
    db.commit()
    db.refresh(camera)

    # Restart stream if URL or enabled changed
    if "rtsp_url" in update_data or "enabled" in update_data:
        await stream_manager.stop_camera(camera_id)
        if camera.enabled:
            await stream_manager.start_camera(camera.id, camera.rtsp_url, camera.name)

    return camera


@router.delete("/{camera_id}")
async def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(404, "Camera not found")

    await stream_manager.stop_camera(camera_id)
    db.delete(camera)
    db.commit()
    return {"ok": True}


@router.get("/{camera_id}/snapshot")
def get_snapshot(camera_id: int):
    """Get current frame as JPEG."""
    frame = stream_manager.get_frame(camera_id)
    if frame is None:
        raise HTTPException(404, "No frame available")

    _, buffer = cv2.imencode(".jpg", frame)
    return StreamingResponse(
        io.BytesIO(buffer.tobytes()),
        media_type="image/jpeg",
    )


@router.get("/{camera_id}/detections")
def get_detections(camera_id: int):
    """Get latest detections for a camera."""
    return stream_manager.get_detections(camera_id)


@router.post("/{camera_id}/start")
async def start_camera_stream(camera_id: int, db: Session = Depends(get_db)):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(404, "Camera not found")
    ok = await stream_manager.start_camera(camera.id, camera.rtsp_url, camera.name)
    if not ok:
        raise HTTPException(500, "Failed to start camera stream")
    return {"ok": True}


@router.post("/{camera_id}/stop")
async def stop_camera_stream(camera_id: int):
    await stream_manager.stop_camera(camera_id)
    return {"ok": True}
