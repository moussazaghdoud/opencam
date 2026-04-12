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
    """Register a face with multi-angle capture for better recognition.

    Camera capture mode: takes 30 frames over 6 seconds to capture
    different angles and expressions. Returns quality report.
    """
    photo_path = str(FACES_DIR / f"{name.lower().replace(' ', '_')}.jpg")

    quality_report = {
        "total_frames": 0,
        "faces_detected": 0,
        "embeddings_generated": 0,
        "angles_covered": [],
        "quality": "unknown",
    }

    if photo:
        # Upload photo
        with open(photo_path, "wb") as f:
            content = await photo.read()
            f.write(content)
        quality_report["total_frames"] = 1
        quality_report["faces_detected"] = 1
    elif camera_id:
        # Multi-angle capture: 30 frames over 6 seconds for angle coverage
        import asyncio, cv2
        frames = []
        face_frames = []
        face_positions = []  # track face position for angle estimation

        for i in range(30):
            f = stream_manager.get_fresh_frame(camera_id)
            if f is not None:
                frames.append(f)
                detected = []
                if face_recognizer.det_session:
                    try:
                        detected = face_recognizer._detect_faces_retinaface(f, threshold=0.5)
                    except Exception:
                        pass
                if not detected:
                    detected = face_recognizer._detect_faces_haar(f)
                if detected:
                    face_frames.append(f)
                    # Track face bbox center for angle diversity
                    bbox = detected[0]["bbox"]
                    cx = (bbox[0] + bbox[2]) / 2
                    cy = (bbox[1] + bbox[3]) / 2
                    fw = bbox[2] - bbox[0]
                    fh = bbox[3] - bbox[1]
                    face_positions.append({"cx": cx, "cy": cy, "w": fw, "h": fh, "idx": len(face_frames) - 1})
            await asyncio.sleep(0.2)  # 200ms intervals = 6 seconds total

        if not frames:
            raise HTTPException(400, "No frame available from camera")

        registration_frames = face_frames if face_frames else frames

        # Select diverse frames — pick frames where face position varies most
        if len(face_positions) > 5:
            selected_indices = _select_diverse_frames(face_positions, max_frames=10)
            diverse_frames = [face_frames[i] for i in selected_indices]
            registration_frames = diverse_frames

        # Save the best quality frame as profile photo (largest face)
        if face_positions:
            best_idx = max(face_positions, key=lambda p: p["w"] * p["h"])["idx"]
            cv2.imwrite(photo_path, face_frames[best_idx])
        else:
            cv2.imwrite(photo_path, registration_frames[len(registration_frames) // 2])

        # Estimate angles covered
        angles = _estimate_angles(face_positions)
        quality_report["total_frames"] = len(frames)
        quality_report["faces_detected"] = len(face_frames)
        quality_report["angles_covered"] = angles
    else:
        raise HTTPException(400, "Provide either a photo or camera_id")

    # Save to DB
    face = KnownFace(name=name, role=role, photo_path=photo_path)
    db.add(face)
    db.commit()
    db.refresh(face)

    # Register embeddings
    if camera_id:
        extra = registration_frames[1:] if len(registration_frames) > 1 else []
    else:
        extra = []
    face_recognizer.add_face(name, photo_path, role, extra_frames=extra)

    # Quality report
    emb_count = len(face_recognizer.known_faces.get(name, {}).get("embeddings", []))
    quality_report["embeddings_generated"] = emb_count
    if emb_count >= 8:
        quality_report["quality"] = "excellent"
    elif emb_count >= 5:
        quality_report["quality"] = "good"
    elif emb_count >= 2:
        quality_report["quality"] = "fair"
    elif emb_count >= 1:
        quality_report["quality"] = "poor"
    else:
        quality_report["quality"] = "failed"

    return {
        "id": face.id,
        "name": name,
        "role": role,
        "photo_path": photo_path,
        "quality": quality_report,
    }


def _select_diverse_frames(positions: list[dict], max_frames: int = 10) -> list[int]:
    """Select the most diverse frames based on face position variance.

    Picks frames where the face is at different positions/sizes,
    which correlates with different angles.
    """
    if len(positions) <= max_frames:
        return [p["idx"] for p in positions]

    # Normalize positions
    cxs = [p["cx"] for p in positions]
    cys = [p["cy"] for p in positions]
    cx_range = max(cxs) - min(cxs) if len(set(cxs)) > 1 else 1
    cy_range = max(cys) - min(cys) if len(set(cys)) > 1 else 1

    # Greedy furthest-point sampling
    selected = [0]
    for _ in range(max_frames - 1):
        best_dist = -1
        best_idx = -1
        for i, p in enumerate(positions):
            if i in selected:
                continue
            min_dist = float("inf")
            for s in selected:
                sp = positions[s]
                dx = (p["cx"] - sp["cx"]) / max(cx_range, 1)
                dy = (p["cy"] - sp["cy"]) / max(cy_range, 1)
                dw = (p["w"] - sp["w"]) / max(sp["w"], 1)
                dist = (dx ** 2 + dy ** 2 + dw ** 2) ** 0.5
                min_dist = min(min_dist, dist)
            if min_dist > best_dist:
                best_dist = min_dist
                best_idx = i
        if best_idx >= 0:
            selected.append(best_idx)

    return [positions[i]["idx"] for i in selected]


def _estimate_angles(positions: list[dict]) -> list[str]:
    """Estimate which face angles were captured based on position variance."""
    if not positions:
        return []

    angles = ["frontal"]
    cxs = [p["cx"] for p in positions]
    widths = [p["w"] for p in positions]

    cx_range = max(cxs) - min(cxs)
    w_range = max(widths) - min(widths) if widths else 0

    # Horizontal movement = left/right angle
    if cx_range > 30:
        angles.append("left")
        angles.append("right")

    # Face width change = angle change (narrower = more angled)
    if w_range > 15:
        angles.append("angled")

    # Multiple face sizes = distance variation
    if w_range > 30:
        angles.append("near")
        angles.append("far")

    return angles


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
async def recognize_from_camera(camera_id: int, db: Session = Depends(get_db)):
    """Run face recognition — tries up to 5 frames to find the best pose."""
    import asyncio

    frame = stream_manager.get_frame(camera_id)
    if frame is None:
        raise HTTPException(400, "No frame available")

    results = []
    for _ in range(5):
        frame = stream_manager.get_frame(camera_id)
        if frame is not None:
            results = face_recognizer.recognize(frame)
            if results:
                break
        await asyncio.sleep(0.15)

    return {"faces": results}
