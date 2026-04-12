"""Object Identifier — second YOLO pass using Open Images V7 (601 classes).

Runs SEPARATELY from the main detection pipeline (which uses COCO for person/vehicle).
This service identifies WHAT objects are in the scene — not WHO is there.

Used by the clip analyzer to detect what a person is carrying or what changed in the scene.
Never modifies the core detection pipeline.

Detection preferences are user-configurable at runtime via API.
"""

import json
import logging
import threading
from pathlib import Path

import numpy as np
from ultralytics import YOLO

from app.core.config import settings

logger = logging.getLogger(__name__)

# Default classes relevant to surveillance — subset of 601
DEFAULT_SURVEILLANCE_CLASSES = {
    15: "Backpack",
    57: "Bottle",
    62: "Box",
    82: "Camera",
    115: "Clothing",
    116: "Coat",
    164: "Door",
    217: "Glasses",
    237: "Handbag",
    238: "Handgun",
    243: "Hat",
    248: "Helmet",
    280: "Jacket",
    296: "Knife",
    304: "Laptop",
    318: "Luggage and bags",
    339: "Mobile phone",
    381: "Person",
    388: "Pillow",
    394: "Plastic bag",
    453: "Shelf",
    457: "Shotgun",
    502: "Suit",
    503: "Suitcase",
    516: "Tablet computer",
    541: "Tool",
    562: "Umbrella",
    580: "Weapon",
}

# High-alert objects — flag these prominently
DEFAULT_HIGH_ALERT = {"Handgun", "Knife", "Shotgun", "Weapon"}

# Preferences file path
_PREFS_PATH = Path("detection_prefs.json")


class DetectionPreferences:
    """User-configurable detection preferences. Persisted to disk as JSON."""

    def __init__(self):
        self._lock = threading.Lock()
        self.enabled_labels: set[str] = set(DEFAULT_SURVEILLANCE_CLASSES.values())
        self.high_alert_labels: set[str] = set(DEFAULT_HIGH_ALERT)
        self.announce_labels: set[str] = set(DEFAULT_SURVEILLANCE_CLASSES.values()) - {"Person", "Door", "Shelf", "Clothing"}
        self._load()

    def _load(self):
        if _PREFS_PATH.exists():
            try:
                data = json.loads(_PREFS_PATH.read_text())
                self.enabled_labels = set(data.get("enabled", self.enabled_labels))
                self.high_alert_labels = set(data.get("high_alert", self.high_alert_labels))
                self.announce_labels = set(data.get("announce", self.announce_labels))
                logger.info(f"Detection preferences loaded: {len(self.enabled_labels)} objects enabled, "
                            f"{len(self.announce_labels)} announced")
            except Exception as e:
                logger.warning(f"Failed to load detection prefs: {e}")

    def save(self):
        with self._lock:
            data = {
                "enabled": sorted(self.enabled_labels),
                "high_alert": sorted(self.high_alert_labels),
                "announce": sorted(self.announce_labels),
            }
            _PREFS_PATH.write_text(json.dumps(data, indent=2))

    def is_enabled(self, label: str) -> bool:
        return label in self.enabled_labels

    def is_high_alert(self, label: str) -> bool:
        return label in self.high_alert_labels

    def should_announce(self, label: str) -> bool:
        return label in self.announce_labels

    def to_dict(self) -> dict:
        return {
            "enabled": sorted(self.enabled_labels),
            "high_alert": sorted(self.high_alert_labels),
            "announce": sorted(self.announce_labels),
        }

    def update(self, enabled: list[str] | None = None,
               high_alert: list[str] | None = None,
               announce: list[str] | None = None):
        with self._lock:
            if enabled is not None:
                self.enabled_labels = set(enabled)
            if high_alert is not None:
                self.high_alert_labels = set(high_alert)
            if announce is not None:
                self.announce_labels = set(announce)
        self.save()


# Singleton
detection_prefs = DetectionPreferences()


class ObjectIdentifier:
    """Identifies objects in a frame using YOLOv8 Open Images V7."""

    def __init__(self):
        self.model: YOLO | None = None
        self._loaded = False
        self._all_class_names: dict[int, str] = {}  # populated after model load

    def load(self):
        if self._loaded:
            return
        if not settings.ENABLE_OBJECT_IDENTIFICATION:
            return
        logger.info("Loading YOLOv8 Open Images V7 model (601 classes)...")
        self.model = YOLO("yolov8n-oiv7.pt")
        self._all_class_names = dict(self.model.names)
        self._loaded = True
        logger.info(f"Object identification model loaded ({len(self.model.names)} classes)")

    def get_all_class_names(self) -> list[str]:
        """Return all 601 available class names."""
        if not self._loaded:
            self.load()
        return sorted(set(self._all_class_names.values()))

    def identify(self, frame: np.ndarray, confidence: float = 0.3) -> list[dict]:
        """Identify objects in a frame. Returns list of detected objects.

        Only returns objects that are enabled in detection preferences.
        """
        if not self._loaded or not self.model:
            self.load()
        if not self.model:
            return []

        results = self.model(frame, conf=confidence, verbose=False)
        objects = []

        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                label = self._all_class_names.get(cls_id)
                if not label:
                    continue
                # Only report objects the user has enabled
                if not detection_prefs.is_enabled(label):
                    continue

                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])

                objects.append({
                    "label": label,
                    "confidence": round(conf, 3),
                    "bbox": [round(x1), round(y1), round(x2), round(y2)],
                    "center": [round((x1 + x2) / 2), round((y1 + y2) / 2)],
                    "high_alert": detection_prefs.is_high_alert(label),
                    "announce": detection_prefs.should_announce(label),
                })

        # Sort by confidence descending
        objects.sort(key=lambda o: o["confidence"], reverse=True)
        return objects

    def identify_in_region(self, frame: np.ndarray, bbox: list[int],
                           padding: float = 0.1, confidence: float = 0.25) -> list[dict]:
        """Identify objects within a specific region (e.g., around a person).

        Crops the frame to the bbox + padding, runs identification,
        and adjusts coordinates back to full frame.
        """
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        bw, bh = x2 - x1, y2 - y1

        # Add padding
        px, py = int(bw * padding), int(bh * padding)
        rx1 = max(0, x1 - px)
        ry1 = max(0, y1 - py)
        rx2 = min(w, x2 + px)
        ry2 = min(h, y2 + py)

        roi = frame[ry1:ry2, rx1:rx2]
        if roi.size == 0:
            return []

        objects = self.identify(roi, confidence)

        # Adjust coordinates back to full frame
        for obj in objects:
            obj["bbox"] = [
                obj["bbox"][0] + rx1,
                obj["bbox"][1] + ry1,
                obj["bbox"][2] + rx1,
                obj["bbox"][3] + ry1,
            ]
            obj["center"] = [
                obj["center"][0] + rx1,
                obj["center"][1] + ry1,
            ]

        # Filter out "Person" — we already know there's a person
        objects = [o for o in objects if o["label"] != "Person"]
        return objects


# Singleton
object_identifier = ObjectIdentifier()
