import asyncio
import cv2
import base64
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.config import settings
from app.services.stream_processor import stream_manager
from app.services.counter import get_tracker
from app.services.ppe_detector import check_persons_ppe
from app.services.heatmap import heatmap_accumulator

router = APIRouter()

# Global toggles
_privacy_mode: dict[int, bool] = {}  # camera_id -> enabled
_heatmap_mode: dict[int, bool] = {}  # camera_id -> enabled


@router.post("/api/privacy/{camera_id}")
def toggle_privacy(camera_id: int, enabled: bool = True):
    """Toggle live face blur for a camera."""
    _privacy_mode[camera_id] = enabled
    return {"camera_id": camera_id, "privacy_mode": enabled}


@router.get("/api/privacy/{camera_id}")
def get_privacy(camera_id: int):
    return {"camera_id": camera_id, "privacy_mode": _privacy_mode.get(camera_id, False)}


@router.post("/api/heatmap-overlay/{camera_id}")
def toggle_heatmap_overlay(camera_id: int, enabled: bool = True):
    """Toggle heatmap overlay on live feed."""
    _heatmap_mode[camera_id] = enabled
    return {"camera_id": camera_id, "heatmap_overlay": enabled}


@router.get("/api/heatmap-overlay/{camera_id}")
def get_heatmap_overlay(camera_id: int):
    return {"camera_id": camera_id, "heatmap_overlay": _heatmap_mode.get(camera_id, False)}


def _blur_faces(frame, detections, faces):
    """Apply Gaussian blur to faces. Uses face detection if available, falls back to person center."""
    blurred = frame.copy()
    h, w = frame.shape[:2]
    blurred_regions = set()

    # Method 1: Blur actual detected faces (most accurate when available)
    for face in faces:
        x1, y1, x2, y2 = face["bbox"]
        # Expand face bbox by 30% for safety margin
        fw, fh = x2 - x1, y2 - y1
        x1 = max(0, int(x1 - fw * 0.3))
        y1 = max(0, int(y1 - fh * 0.3))
        x2 = min(w, int(x2 + fw * 0.3))
        y2 = min(h, int(y2 + fh * 0.3))
        if x2 > x1 and y2 > y1:
            roi = blurred[y1:y2, x1:x2]
            blurred[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (99, 99), 30)
            blurred_regions.add("face")

    # Method 2: For any person detection without a face match, blur the center-upper area
    if not blurred_regions:
        for det in detections:
            if det.get("object_type") != "person":
                continue
            x1, y1, x2, y2 = det["bbox"]
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(w, int(x2)), min(h, int(y2))
            person_h = y2 - y1
            person_w = x2 - x1
            # Center of person (where face typically is)
            center_y = y1 + int(person_h * 0.3)
            center_x = x1 + int(person_w * 0.5)
            # Blur a square around the estimated face position
            face_size = max(int(person_h * 0.25), int(person_w * 0.3))
            bx1 = max(0, center_x - face_size)
            by1 = max(0, center_y - face_size)
            bx2 = min(w, center_x + face_size)
            by2 = min(h, center_y + face_size)
            if bx2 > bx1 and by2 > by1:
                roi = blurred[by1:by2, bx1:bx2]
                blurred[by1:by2, bx1:bx2] = cv2.GaussianBlur(roi, (99, 99), 30)

    return blurred


@router.websocket("/ws/camera/{camera_id}")
async def camera_feed(websocket: WebSocket, camera_id: int):
    """WebSocket endpoint for live camera feed with detections + face overlay."""
    await websocket.accept()

    try:
        while True:
            frame = stream_manager.get_frame(camera_id)
            if frame is None:
                await asyncio.sleep(0.5)
                continue

            detections = stream_manager.get_detections(camera_id)
            faces = stream_manager.get_faces(camera_id)
            privacy = _privacy_mode.get(camera_id, False)

            # Draw on frame
            annotated = frame.copy()

            # Apply face blur FIRST if privacy mode is on
            if privacy and (detections or faces):
                annotated = _blur_faces(annotated, detections, faces)

            h, w = annotated.shape[:2]

            # Draw counting lines
            tracker = get_tracker(camera_id)
            for cl in tracker._counting_lines:
                pt_a = (int(cl.point_a[0] * w), int(cl.point_a[1] * h))
                pt_b = (int(cl.point_b[0] * w), int(cl.point_b[1] * h))
                cv2.line(annotated, pt_a, pt_b, (0, 255, 255), 2)
                counts = tracker.get_counts()
                cv2.putText(annotated, f"IN:{counts['in']} OUT:{counts['out']}", (pt_a[0] + 5, pt_a[1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            # Draw object detections
            for det in detections:
                x1, y1, x2, y2 = det["bbox"]
                color = (0, 255, 0) if det["object_type"] == "person" else (255, 165, 0)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                label = f"{det['label']} {det['confidence']:.0%}"
                cv2.putText(
                    annotated, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,
                )

            # People counter badge (bottom-left corner) — count actual persons in frame
            person_count = sum(1 for d in detections if d.get("object_type") == "person")
            counter_label = f"People: {person_count}"
            (tw, th), _ = cv2.getTextSize(counter_label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            pad = 8
            cv2.rectangle(annotated, (10, h - th - pad * 2 - 10), (10 + tw + pad * 2, h - 10), (30, 30, 30), -1)
            cv2.putText(annotated, counter_label, (10 + pad, h - 10 - pad),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # Draw face recognitions (label only, face already blurred if privacy on)
            for face in faces:
                x1, y1, x2, y2 = face["bbox"]
                if privacy:
                    # Just show "BLURRED" label
                    cv2.putText(annotated, "PRIVACY", (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 128, 128), 2)
                else:
                    if face["known"]:
                        color = (0, 200, 0)
                        label = f"{face['name']} ({face['role']})"
                    else:
                        color = (0, 0, 255)
                        label = "UNKNOWN"
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    cv2.rectangle(annotated, (x1, y1 - th - 10), (x1 + tw, y1), color, -1)
                    cv2.putText(annotated, label, (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # PPE check — detect yellow safety jacket (if enabled)
            safety_jacket_detected = False
            ppe_results = check_persons_ppe(frame, detections, camera_id=camera_id) if settings.ENABLE_PPE_DETECTION else []
            for ppe in ppe_results:
                px1, py1, px2, py2 = ppe["bbox"]
                if ppe["wearing_jacket"]:
                    cv2.putText(annotated, "SAFETY JACKET", (px1, py2 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    cv2.rectangle(annotated, (px1, py1), (px2, py2), (0, 255, 0), 2)
                    safety_jacket_detected = True

            # Heatmap overlay (toggled via API, only if module enabled)
            if settings.ENABLE_HEATMAP and _heatmap_mode.get(camera_id, False):
                heatmap_img = heatmap_accumulator.get_heatmap_image(camera_id, w, h)
                heatmap_bgr = heatmap_img[:, :, :3]
                mask = heatmap_img[:, :, 3] > 0
                annotated[mask] = cv2.addWeighted(annotated, 0.6, heatmap_bgr, 0.4, 0)[mask]

            # Encode and send
            _, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
            b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")

            await websocket.send_json({
                "frame": b64,
                "detections": detections,
                "safety_jacket_detected": safety_jacket_detected,
                "faces": faces,
                "privacy_mode": privacy,
                "camera_id": camera_id,
                "person_count": person_count,
            })

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        pass
    except Exception:
        await websocket.close()
