import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.face import KnownFace
from app.services.face_recognizer import face_recognizer
from app.services.stream_processor import stream_manager

router = APIRouter(prefix="/api/faces", tags=["faces"])

FACES_DIR = Path("faces")
FACES_DIR.mkdir(exist_ok=True)


@router.get("/")
def list_faces(db: Session = Depends(get_db)):
    faces = db.query(KnownFace).order_by(KnownFace.id).all()
    return [
        {
            "id": f.id,
            "name": f.name,
            "role": f.role,
            "photo_path": f.photo_path,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in faces
    ]


@router.post("/register")
async def register_face(
    name: str = Form(...),
    role: str = Form(""),
    photo: UploadFile = File(None),
    camera_id: int = Form(None),
    db: Session = Depends(get_db),
):
    """Register a face. Either upload a photo or capture from a camera."""
    photo_path = str(FACES_DIR / f"{name.lower().replace(' ', '_')}.jpg")

    if photo:
        # Upload photo
        with open(photo_path, "wb") as f:
            content = await photo.read()
            f.write(content)
    elif camera_id:
        # Capture from camera
        import cv2
        frame = stream_manager.get_frame(camera_id)
        if frame is None:
            raise HTTPException(400, "No frame available from camera")
        cv2.imwrite(photo_path, frame)
    else:
        raise HTTPException(400, "Provide either a photo or camera_id")

    # Save to DB
    face = KnownFace(name=name, role=role, photo_path=photo_path)
    db.add(face)
    db.commit()
    db.refresh(face)

    # Register in recognizer
    face_recognizer.add_face(name, photo_path, role)

    return {"id": face.id, "name": name, "role": role, "photo_path": photo_path}


@router.get("/{face_id}/photo")
def get_face_photo(face_id: int, db: Session = Depends(get_db)):
    face = db.query(KnownFace).filter(KnownFace.id == face_id).first()
    if not face:
        raise HTTPException(404, "Face not found")
    path = Path(face.photo_path)
    if not path.exists():
        raise HTTPException(404, "Photo not found")
    return FileResponse(path, media_type="image/jpeg")


@router.delete("/{face_id}")
def delete_face(face_id: int, db: Session = Depends(get_db)):
    face = db.query(KnownFace).filter(KnownFace.id == face_id).first()
    if not face:
        raise HTTPException(404, "Face not found")

    face_recognizer.remove_face(face.name)

    # Remove photo file
    try:
        Path(face.photo_path).unlink(missing_ok=True)
    except OSError:
        pass

    db.delete(face)
    db.commit()
    return {"ok": True}


@router.post("/recognize")
def recognize_from_camera(camera_id: int, db: Session = Depends(get_db)):
    """Run face recognition on current frame from a camera."""
    frame = stream_manager.get_frame(camera_id)
    if frame is None:
        raise HTTPException(400, "No frame available")

    results = face_recognizer.recognize(frame)
    return {"faces": results}
