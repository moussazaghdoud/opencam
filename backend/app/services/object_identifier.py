"""Object Identifier — second YOLO pass using Open Images V7 (601 classes).

Runs SEPARATELY from the main detection pipeline (which uses COCO for person/vehicle).
This service identifies WHAT objects are in the scene — not WHO is there.

Used by the clip analyzer to detect what a person is carrying or what changed in the scene.
Never modifies the core detection pipeline.
"""

import logging
import numpy as np
from ultralytics import YOLO

from app.core.config import settings

logger = logging.getLogger(__name__)

# Classes relevant to surveillance — subset of 601 for focused detection
SURVEILLANCE_CLASSES = {
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
HIGH_ALERT_OBJECTS = {"Handgun", "Knife", "Shotgun", "Weapon"}


class ObjectIdentifier:
    """Identifies objects in a frame using YOLOv8 Open Images V7."""

    def __init__(self):
        self.model: YOLO | None = None
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        if not settings.ENABLE_OBJECT_IDENTIFICATION:
            return
        logger.info("Loading YOLOv8 Open Images V7 model (601 classes)...")
        self.model = YOLO("yolov8n-oiv7.pt")
        self._loaded = True
        logger.info(f"Object identification model loaded ({len(self.model.names)} classes)")

    def identify(self, frame: np.ndarray, confidence: float = 0.3) -> list[dict]:
        """Identify objects in a frame. Returns list of detected objects.

        Only returns surveillance-relevant objects (not all 601 classes).
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
                # Only report surveillance-relevant classes
                if cls_id not in SURVEILLANCE_CLASSES:
                    continue

                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                label = SURVEILLANCE_CLASSES[cls_id]

                objects.append({
                    "label": label,
                    "confidence": round(conf, 3),
                    "bbox": [round(x1), round(y1), round(x2), round(y2)],
                    "center": [round((x1 + x2) / 2), round((y1 + y2) / 2)],
                    "high_alert": label in HIGH_ALERT_OBJECTS,
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
