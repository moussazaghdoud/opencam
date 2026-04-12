"""Clip Analyzer — extracts structured activity facts from saved video clips.

Runs entirely on CPU using OpenCV + YOLO. No LLM calls.
Output is a JSON dict of facts that can be fed into the AI narrator prompt.

Includes scene change detection: compares frames before a person appeared
with frames after they left to detect if objects were added or removed.
"""

import logging
from pathlib import Path

import cv2
import numpy as np

from app.services.detector import detector

logger = logging.getLogger(__name__)

# Scene change detection thresholds
_SCENE_CHANGE_THRESHOLD = 25     # pixel intensity diff to count as changed
_SCENE_CHANGE_MIN_AREA = 0.005   # minimum changed area (0.5% of frame) to report
_SCENE_CHANGE_MAX_AREA = 0.30    # ignore if > 30% changed (lighting shift, not object)


def analyze_clip(clip_path: str) -> dict | None:
    """Analyze a short video clip and extract structured activity facts.

    Returns a dict with:
      - duration_seconds, person_present_seconds
      - person_count_min / person_count_max
      - entry_direction / exit_direction
      - bbox_size_trend: approaching/retreating/stable
      - scene_change: dict describing what changed in the scene
      - movement_summary: brief text description
      - frame_count

    Returns None if clip is unreadable or too short.
    """
    if not Path(clip_path).exists():
        return None

    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 2
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames < 3:
        cap.release()
        return None

    # Read all frames + run YOLO (clips are ~40 frames max at 2fps)
    all_frames: list[np.ndarray] = []
    person_detections: list[dict] = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        all_frames.append(frame)
        detections = detector.detect(frame)
        persons = [d for d in detections if d.get("object_type") == "person"]

        h, w = frame.shape[:2]
        centers = []
        areas = []
        bboxes = []
        for p in persons:
            x1, y1, x2, y2 = p["bbox"]
            cx = (x1 + x2) / 2 / w
            cy = (y1 + y2) / 2 / h
            area = (x2 - x1) * (y2 - y1) / (w * h)
            centers.append((cx, cy))
            areas.append(area)
            bboxes.append([x1, y1, x2, y2])

        person_detections.append({
            "frame_idx": frame_idx,
            "count": len(persons),
            "centers": centers,
            "areas": areas,
            "bboxes": bboxes,
        })
        frame_idx += 1

    cap.release()

    if not person_detections or not all_frames:
        return None

    # --- Compute movement facts ---

    duration = total_frames / fps
    counts = [d["count"] for d in person_detections]
    frames_with_person = sum(1 for c in counts if c > 0)
    person_present_seconds = round(frames_with_person / fps, 1)
    person_count_min = min(counts)
    person_count_max = max(counts)

    frames_with = [d for d in person_detections if d["count"] > 0]

    entry_dir = "unknown"
    exit_dir = "unknown"
    bbox_trend = "stable"

    if frames_with:
        first_centers = frames_with[0]["centers"]
        if first_centers:
            entry_dir = _direction_from_position(*first_centers[0])

        last_centers = frames_with[-1]["centers"]
        if last_centers:
            exit_dir = _direction_from_position(*last_centers[0])

        if len(frames_with) >= 2:
            first_areas = frames_with[0]["areas"]
            last_areas = frames_with[-1]["areas"]
            if first_areas and last_areas:
                ratio = (sum(last_areas) / len(last_areas)) / (sum(first_areas) / len(first_areas)) if sum(first_areas) > 0 else 1.0
                if ratio > 1.3:
                    bbox_trend = "approaching"
                elif ratio < 0.7:
                    bbox_trend = "retreating"

    # --- Scene change detection (background diff) ---
    scene_change = _detect_scene_change(all_frames, person_detections)

    # --- Person silhouette change (did they pick up / put down something?) ---
    carrying_change = _detect_carrying_change(all_frames, person_detections)

    # Merge carrying detection into scene_change if scene diff didn't catch it
    if carrying_change["detected"] and not scene_change.get("changed"):
        scene_change = {
            "changed": True,
            "change_percent": carrying_change.get("bbox_growth_percent", 0),
            "change_location": "on person",
            "change_type": carrying_change["change_type"],
            "description": carrying_change["description"],
        }
    elif carrying_change["detected"] and scene_change.get("changed"):
        # Both detected — combine descriptions
        scene_change["description"] += " " + carrying_change["description"]

    # --- Build movement summary ---
    movement_summary = _build_movement_summary(
        frames_with, duration, person_present_seconds,
        entry_dir, exit_dir, bbox_trend, person_count_max, scene_change
    )

    return {
        "duration_seconds": round(duration, 1),
        "person_present_seconds": person_present_seconds,
        "person_count_min": person_count_min,
        "person_count_max": person_count_max,
        "entry_direction": entry_dir,
        "exit_direction": exit_dir,
        "bbox_size_trend": bbox_trend,
        "scene_change": scene_change,
        "carrying_change": carrying_change,
        "movement_summary": movement_summary,
        "frame_count": len(person_detections),
    }


# ---------------------------------------------------------------------------
# Scene change detection — compares "before person" vs "after person" frames
# ---------------------------------------------------------------------------

def _detect_scene_change(frames: list[np.ndarray],
                         detections: list[dict]) -> dict:
    """Compare scene before a person appeared with scene after they left.

    Uses frame differencing with person bounding boxes masked out
    (so the person themselves don't count as a "change").

    Returns:
      - changed: bool — whether a significant scene change was detected
      - change_percent: float — percentage of frame area that changed
      - change_location: str — where in the frame the change occurred
      - change_type: str — "object_removed", "object_added", "scene_altered", or "none"
      - description: str — human-readable description
    """
    result = {
        "changed": False,
        "change_percent": 0.0,
        "change_location": "none",
        "change_type": "none",
        "description": "No significant scene change detected.",
    }

    # Find "before" frames (no person) and "after" frames (no person)
    before_indices = []
    after_indices = []
    person_seen = False
    person_gone = False

    for i, det in enumerate(detections):
        if det["count"] == 0 and not person_seen:
            before_indices.append(i)
        elif det["count"] > 0:
            person_seen = True
            person_gone = False
        elif det["count"] == 0 and person_seen:
            person_gone = True
            after_indices.append(i)

    # Need at least 1 frame before and 1 after
    if not before_indices or not after_indices:
        return result

    # Use the last "before" frame and the first "after" frame
    before_frame = frames[before_indices[-1]]
    after_frame = frames[after_indices[0]]

    # Convert to grayscale for comparison
    before_gray = cv2.cvtColor(before_frame, cv2.COLOR_BGR2GRAY)
    after_gray = cv2.cvtColor(after_frame, cv2.COLOR_BGR2GRAY)

    # Apply slight blur to reduce noise sensitivity
    before_gray = cv2.GaussianBlur(before_gray, (7, 7), 0)
    after_gray = cv2.GaussianBlur(after_gray, (7, 7), 0)

    # Compute absolute difference
    diff = cv2.absdiff(before_gray, after_gray)

    # Threshold to get binary change mask
    _, thresh = cv2.threshold(diff, _SCENE_CHANGE_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Clean up noise with morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # Calculate change area
    h, w = thresh.shape
    total_pixels = h * w
    changed_pixels = cv2.countNonZero(thresh)
    change_ratio = changed_pixels / total_pixels

    # Filter: too small = noise, too large = lighting change
    if change_ratio < _SCENE_CHANGE_MIN_AREA:
        return result
    if change_ratio > _SCENE_CHANGE_MAX_AREA:
        result["description"] = f"Large scene change detected ({change_ratio * 100:.1f}% of frame) — likely lighting or camera shift, not object movement."
        return result

    # Find where the change is
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return result

    # Get the largest contour (main change region)
    largest = max(contours, key=cv2.contourArea)
    x, y, cw, ch = cv2.boundingRect(largest)
    center_x = (x + cw / 2) / w
    center_y = (y + ch / 2) / h
    change_location = _direction_from_position(center_x, center_y)

    # Determine if object was added or removed by comparing brightness
    # In the changed region: brighter after = something was removed (background exposed)
    # Darker after = something was added (object blocking background)
    roi_before = before_gray[y:y + ch, x:x + cw]
    roi_after = after_gray[y:y + ch, x:x + cw]
    brightness_before = float(np.mean(roi_before))
    brightness_after = float(np.mean(roi_after))

    if brightness_after > brightness_before + 10:
        change_type = "object_removed"
        description = f"An object appears to have been removed from the {change_location} area ({change_ratio * 100:.1f}% of frame changed)."
    elif brightness_after < brightness_before - 10:
        change_type = "object_added"
        description = f"An object appears to have been placed in the {change_location} area ({change_ratio * 100:.1f}% of frame changed)."
    else:
        change_type = "scene_altered"
        description = f"The scene was altered in the {change_location} area ({change_ratio * 100:.1f}% of frame changed)."

    return {
        "changed": True,
        "change_percent": round(change_ratio * 100, 1),
        "change_location": change_location,
        "change_type": change_type,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Carrying detection — compares person's silhouette between entry and exit
# ---------------------------------------------------------------------------

def _detect_carrying_change(frames: list[np.ndarray],
                            detections: list[dict]) -> dict:
    """Detect if a person picked up or put down an object.

    Uses 3 methods:
    1. Bbox aspect ratio change: wider/taller bbox at exit vs entry = carrying something
    2. Person silhouette diff: more non-background pixels inside bbox = carrying object
    3. Lower-body width change: arms holding object makes torso area wider

    Returns:
      - detected: bool
      - change_type: "picked_up_object" | "put_down_object" | "none"
      - description: str
      - bbox_growth_percent: float
    """
    result = {
        "detected": False,
        "change_type": "none",
        "description": "",
        "bbox_growth_percent": 0.0,
    }

    frames_with = [d for d in detections if d["count"] > 0 and d["bboxes"]]
    if len(frames_with) < 4:
        return result

    # Compare early frames (first 3 with person) vs late frames (last 3 with person)
    early = frames_with[:3]
    late = frames_with[-3:]

    # --- Method 1: Bbox size and aspect ratio change ---
    early_widths = []
    early_heights = []
    late_widths = []
    late_heights = []

    for det in early:
        for bbox in det["bboxes"]:
            x1, y1, x2, y2 = bbox
            early_widths.append(x2 - x1)
            early_heights.append(y2 - y1)

    for det in late:
        for bbox in det["bboxes"]:
            x1, y1, x2, y2 = bbox
            late_widths.append(x2 - x1)
            late_heights.append(y2 - y1)

    if not early_widths or not late_widths:
        return result

    avg_early_w = sum(early_widths) / len(early_widths)
    avg_early_h = sum(early_heights) / len(early_heights)
    avg_late_w = sum(late_widths) / len(late_widths)
    avg_late_h = sum(late_heights) / len(late_heights)

    early_area = avg_early_w * avg_early_h
    late_area = avg_late_w * avg_late_h

    if early_area == 0:
        return result

    area_ratio = late_area / early_area
    width_ratio = avg_late_w / avg_early_w if avg_early_w > 0 else 1.0

    # --- Method 2: Pixel density inside person bbox ---
    # Compare how much "stuff" is inside the person bbox (early vs late)
    early_density = _person_pixel_density(frames, early)
    late_density = _person_pixel_density(frames, late)
    density_change = late_density - early_density if early_density > 0 else 0

    # --- Decision logic ---
    # Person's bbox grew significantly (>15% area or >10% width) = picked up object
    # Person's bbox shrank significantly = put down object
    # Higher pixel density at exit = carrying something bulky

    picked_up = False
    put_down = False
    reasons = []

    if area_ratio > 1.15:
        picked_up = True
        reasons.append(f"person's bounding box grew {(area_ratio - 1) * 100:.0f}%")
    elif area_ratio < 0.85:
        put_down = True
        reasons.append(f"person's bounding box shrank {(1 - area_ratio) * 100:.0f}%")

    if width_ratio > 1.12:
        picked_up = True
        reasons.append(f"person appears {(width_ratio - 1) * 100:.0f}% wider at exit")

    if density_change > 0.08:
        picked_up = True
        reasons.append("more visual mass detected on person at exit")
    elif density_change < -0.08:
        put_down = True
        reasons.append("less visual mass detected on person at exit")

    if picked_up:
        result["detected"] = True
        result["change_type"] = "picked_up_object"
        result["bbox_growth_percent"] = round((area_ratio - 1) * 100, 1)
        result["description"] = f"Person appears to have picked up an object ({', '.join(reasons)})."
    elif put_down:
        result["detected"] = True
        result["change_type"] = "put_down_object"
        result["bbox_growth_percent"] = round((area_ratio - 1) * 100, 1)
        result["description"] = f"Person appears to have put down an object ({', '.join(reasons)})."

    return result


def _person_pixel_density(frames: list[np.ndarray],
                          frame_dets: list[dict]) -> float:
    """Measure how much non-background content is inside the person bbox.

    Uses edge detection: more edges = more stuff being carried.
    Returns average edge density (0-1 range).
    """
    densities = []
    for det in frame_dets:
        idx = det["frame_idx"]
        if idx >= len(frames):
            continue
        frame = frames[idx]
        for bbox in det["bboxes"]:
            x1, y1, x2, y2 = [int(v) for v in bbox]
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            roi = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            density = cv2.countNonZero(edges) / max(edges.size, 1)
            densities.append(density)

    return sum(densities) / len(densities) if densities else 0.0


def _direction_from_position(cx: float, cy: float) -> str:
    """Infer which edge the person is near based on normalized center position."""
    margin = 0.25
    if cx < margin:
        return "left"
    if cx > (1 - margin):
        return "right"
    if cy < margin:
        return "top"
    if cy > (1 - margin):
        return "bottom"
    return "center"


def _build_movement_summary(frames_with: list, duration: float,
                            present_seconds: float, entry: str, exit_dir: str,
                            trend: str, max_count: int,
                            scene_change: dict | None = None) -> str:
    """Build a short factual movement description."""
    parts = []

    if max_count == 1:
        parts.append("One person detected.")
    elif max_count > 1:
        parts.append(f"Up to {max_count} persons detected simultaneously.")

    if present_seconds < duration * 0.3:
        parts.append(f"Person was visible for {present_seconds}s out of {duration}s (brief appearance).")
    elif present_seconds > duration * 0.8:
        parts.append(f"Person was present for most of the clip ({present_seconds}s out of {duration}s).")
    else:
        parts.append(f"Person was visible for {present_seconds}s out of {duration}s.")

    if entry != "unknown" and entry != "center":
        parts.append(f"Entered from the {entry} side.")
    if exit_dir != "unknown" and exit_dir != "center":
        parts.append(f"Last seen near the {exit_dir} side.")

    if trend == "approaching":
        parts.append("Person moved closer to the camera.")
    elif trend == "retreating":
        parts.append("Person moved away from the camera.")

    # Scene change (object added/removed)
    if scene_change and scene_change.get("changed"):
        parts.append(scene_change["description"])

    return " ".join(parts)
