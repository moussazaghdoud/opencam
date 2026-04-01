"""PPE Detection — checks if detected persons are wearing a safety jacket.

Uses color analysis on the upper body region to detect white/high-vis jackets.
Includes hysteresis to prevent flickering between states.
"""

import logging
import time
import numpy as np
import cv2

logger = logging.getLogger(__name__)

# Hysteresis state: prevent rapid flipping
_last_state: dict[int, bool] = {}  # camera_id -> last wearing_jacket state
_state_count: dict[int, int] = {}  # camera_id -> consecutive frames in current state
_CONFIRM_FRAMES = 5  # Need N consistent readings before changing state


def check_white_jacket(frame: np.ndarray, bbox: list[int], threshold: float = 0.20) -> dict:
    """Check if a person is wearing a white jacket.

    Uses multiple methods for robustness:
    1. HSV white/light pixel ratio
    2. Average brightness of torso
    3. Comparison to dark clothing baseline
    """
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]

    x1 = max(0, int(x1))
    y1 = max(0, int(y1))
    x2 = min(w, int(x2))
    y2 = min(h, int(y2))

    person_h = y2 - y1
    person_w = x2 - x1
    if person_h < 20 or person_w < 20:
        return {"wearing_jacket": False, "white_ratio": 0.0, "confidence": 0.0}

    # Extract TORSO region — larger area for stability
    # Skip head (top 20%) and legs (bottom 35%)
    torso_y1 = y1 + int(person_h * 0.20)
    torso_y2 = y1 + int(person_h * 0.65)
    torso_x1 = x1 + int(person_w * 0.10)
    torso_x2 = x2 - int(person_w * 0.10)

    torso = frame[torso_y1:torso_y2, torso_x1:torso_x2]
    if torso.size == 0:
        return {"wearing_jacket": False, "white_ratio": 0.0, "confidence": 0.0}

    # Method 1: HSV white/light detection (very permissive for distance)
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)

    # Broad white/light detection — catches white even in shadow
    lower_light = np.array([0, 0, 120])
    upper_light = np.array([180, 100, 255])
    light_mask = cv2.inRange(hsv, lower_light, upper_light)

    total_pixels = torso.shape[0] * torso.shape[1]
    light_pixels = cv2.countNonZero(light_mask)
    light_ratio = light_pixels / total_pixels

    # Method 2: Average brightness of torso
    gray = cv2.cvtColor(torso, cv2.COLOR_BGR2GRAY)
    avg_brightness = float(np.mean(gray))
    # White jacket: avg brightness typically > 150
    # Dark clothing: avg brightness typically < 100
    brightness_score = min(1.0, max(0.0, (avg_brightness - 80) / 120))

    # Method 3: Check if torso is significantly brighter than dark reference
    # Dark clothing (black/navy) has brightness < 80
    is_bright = avg_brightness > 130

    # Combined score
    combined_score = (light_ratio * 0.5) + (brightness_score * 0.5)
    wearing = combined_score >= threshold or (is_bright and light_ratio > 0.15)

    confidence = min(1.0, combined_score / threshold) if wearing else min(1.0, (threshold - combined_score) / threshold)

    return {
        "wearing_jacket": wearing,
        "white_ratio": round(light_ratio, 3),
        "brightness": round(avg_brightness, 1),
        "combined_score": round(combined_score, 3),
        "confidence": round(confidence, 3),
    }


def check_persons_ppe(frame: np.ndarray, detections: list[dict], camera_id: int = 0) -> list[dict]:
    """Check all detected persons for PPE compliance with hysteresis."""
    results = []
    persons = [d for d in detections if d.get("object_type") == "person"]

    if not persons:
        return results

    # Check the primary (largest) person
    raw_results = []
    for det in persons:
        ppe = check_white_jacket(frame, det["bbox"])
        raw_results.append({
            "bbox": det["bbox"],
            "confidence": det.get("confidence", 0),
            "wearing_jacket": ppe["wearing_jacket"],
            "white_ratio": ppe["white_ratio"],
            "brightness": ppe.get("brightness", 0),
            "ppe_confidence": ppe["confidence"],
        })

    # Apply hysteresis on the primary detection (largest bbox)
    if raw_results:
        primary = max(raw_results, key=lambda r: (r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1]))
        current_raw = primary["wearing_jacket"]

        last = _last_state.get(camera_id)
        count = _state_count.get(camera_id, 0)

        if last is None:
            # First reading
            _last_state[camera_id] = current_raw
            _state_count[camera_id] = 1
        elif current_raw == last:
            # Same state — reset counter
            _state_count[camera_id] = 0
        else:
            # Different state — increment counter
            _state_count[camera_id] = count + 1
            if _state_count[camera_id] >= _CONFIRM_FRAMES:
                # Confirmed state change
                _last_state[camera_id] = current_raw
                _state_count[camera_id] = 0

        # Use the confirmed state (not raw)
        confirmed = _last_state.get(camera_id, False)
        for r in raw_results:
            r["wearing_jacket"] = confirmed

    return raw_results
