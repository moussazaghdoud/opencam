import logging
from pathlib import Path
from ultralytics import YOLO
import numpy as np
from app.core.config import settings

logger = logging.getLogger(__name__)

# COCO classes we care about
TARGET_CLASSES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "bicycle"}


class Detector:
    def __init__(self):
        self.model = None
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        logger.info(f"Loading YOLO model: {settings.YOLO_MODEL}")
        self.model = YOLO(settings.YOLO_MODEL)
        self._loaded = True
        logger.info("YOLO model loaded successfully")

    def detect(self, frame: np.ndarray) -> list[dict]:
        if not self._loaded:
            self.load()

        results = self.model(frame, conf=settings.DETECTION_CONFIDENCE, verbose=False)
        detections = []

        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                if cls_id not in TARGET_CLASSES:
                    continue

                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                label = TARGET_CLASSES[cls_id]
                obj_type = "vehicle" if label in VEHICLE_CLASSES else "person"

                detections.append({
                    "label": label,
                    "object_type": obj_type,
                    "confidence": round(conf, 3),
                    "bbox": [round(x1), round(y1), round(x2), round(y2)],
                    "center": [round((x1 + x2) / 2), round((y1 + y2) / 2)],
                })

        return detections


# Singleton
detector = Detector()
