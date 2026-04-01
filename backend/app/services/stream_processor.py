import asyncio
import logging
import platform
import time
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.detector import detector
from app.services.zone_checker import check_detection_in_zone, is_within_schedule
from app.services.alert_service import trigger_alert
from app.services.face_recognizer import face_recognizer
from app.services.counter import get_tracker, CountingLine
from app.services.activity_timer import activity_timer
from app.services.heatmap import heatmap_accumulator
from app.models.camera import Camera
from app.models.zone import Zone
from app.models.rule import Rule
from app.models.event import Event

logger = logging.getLogger(__name__)


class CameraStream:
    def __init__(self, camera_id: int, rtsp_url: str, name: str):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.name = name
        self.cap = None
        self.running = False
        self.last_frame = None
        self.last_detections = []
        self.last_faces = []
        self.frame_count = 0
        self._face_cooldown: dict[str, datetime] = {}  # name -> last seen time

    def open(self) -> bool:
        try:
            # Support webcam index (e.g. "0", "1") or RTSP URL
            source = int(self.rtsp_url) if self.rtsp_url.isdigit() else self.rtsp_url
            # Use DirectShow on Windows for webcams (MSMF has issues)
            if isinstance(source, int) and platform.system() == "Windows":
                self.cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            else:
                self.cap = cv2.VideoCapture(source)
            if not self.cap.isOpened():
                logger.error(f"Cannot open camera {self.name}: {self.rtsp_url}")
                return False

            # Read camera properties
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = self.cap.get(cv2.CAP_PROP_FPS)

            db = SessionLocal()
            try:
                cam = db.query(Camera).filter(Camera.id == self.camera_id).first()
                if cam:
                    cam.width = width
                    cam.height = height
                    cam.fps = fps
                    cam.status = "online"
                    db.commit()
            finally:
                db.close()

            self.running = True
            logger.info(f"Camera {self.name} opened: {width}x{height} @ {fps}fps")
            return True
        except Exception as e:
            logger.error(f"Error opening camera {self.name}: {e}")
            return False

    def close(self):
        self.running = False
        if self.cap:
            self.cap.release()

        db = SessionLocal()
        try:
            cam = db.query(Camera).filter(Camera.id == self.camera_id).first()
            if cam:
                cam.status = "offline"
                db.commit()
        finally:
            db.close()

    def read_frame(self) -> np.ndarray | None:
        if not self.cap or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        if not ret:
            # Loop video files back to start
            if not self.rtsp_url.isdigit() and not self.rtsp_url.startswith("rtsp"):
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
                if not ret:
                    return None
            else:
                return None
        self.last_frame = frame
        return frame

    async def process_frame(self, frame: np.ndarray):
        """Run detection and check rules."""
        self.frame_count += 1
        if self.frame_count % settings.FRAME_SKIP != 0:
            return

        detections = detector.detect(frame)
        self.last_detections = detections

        h, w = frame.shape[:2]

        # Accumulate heatmap data
        heatmap_accumulator.add_detections(self.camera_id, detections, w, h)

        # Update object tracker (counting lines) — normalize bboxes
        tracker = get_tracker(self.camera_id)
        if detections:
            normalized_dets = []
            for d in detections:
                nd = dict(d)
                x1, y1, x2, y2 = d["bbox"]
                nd["bbox"] = [x1 / w, y1 / h, x2 / w, y2 / h]
                normalized_dets.append(nd)
            tracker.update(normalized_dets)

        if not detections:
            # Update zone timers with no activity
            for zone_id in activity_timer._zones:
                activity_timer.update(zone_id, False, 0)
            return

        db = SessionLocal()
        try:
            zones = (
                db.query(Zone)
                .filter(Zone.camera_id == self.camera_id, Zone.enabled == True)
                .all()
            )

            for zone in zones:
                # Count objects in this zone for activity timer
                objects_in_zone = [
                    d for d in detections
                    if check_detection_in_zone(d, zone.points, w, h)
                ]
                activity_timer.update(zone.id, len(objects_in_zone) > 0, len(objects_in_zone))

                rules = (
                    db.query(Rule)
                    .filter(Rule.zone_id == zone.id, Rule.enabled == True)
                    .all()
                )

                for rule in rules:
                    if not is_within_schedule(
                        rule.schedule_start, rule.schedule_end, rule.schedule_days
                    ):
                        continue

                    matching = [
                        d for d in detections
                        if (rule.object_type == "any" or d["object_type"] == rule.object_type)
                        and check_detection_in_zone(d, zone.points, w, h)
                    ]

                    triggered = False
                    if rule.trigger == "enter" and len(matching) >= rule.threshold:
                        triggered = True
                    elif rule.trigger == "count_above" and len(matching) > rule.threshold:
                        triggered = True

                    if triggered:
                        best = max(matching, key=lambda d: d["confidence"])

                        # Save snapshot
                        snap_dir = Path(settings.SNAPSHOTS_DIR)
                        snap_dir.mkdir(parents=True, exist_ok=True)
                        snap_name = f"{self.camera_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        snap_path = str(snap_dir / snap_name)
                        cv2.imwrite(snap_path, frame)

                        event = Event(
                            camera_id=self.camera_id,
                            rule_id=rule.id,
                            event_type=rule.trigger,
                            object_type=best["object_type"],
                            confidence=best["confidence"],
                            snapshot_path=snap_path,
                            bbox=best["bbox"],
                            zone_name=zone.name,
                        )
                        db.add(event)
                        db.commit()

                        event_data = {
                            "event_type": rule.trigger,
                            "camera_name": self.name,
                            "zone_name": zone.name,
                            "object_type": best["object_type"],
                            "confidence": best["confidence"],
                            "event_id": event.id,
                        }
                        await trigger_alert(rule, event_data)

            # Face recognition (run every 10th eligible frame to save CPU)
            if self.frame_count % (settings.FRAME_SKIP * 10) == 0:
                try:
                    face_results = face_recognizer.recognize(frame)
                    self.last_faces = face_results

                    now = datetime.now()
                    for face in face_results:
                        face_name = face["name"]
                        # Cooldown: don't log same face within 30 seconds
                        last_seen = self._face_cooldown.get(face_name)
                        if last_seen and (now - last_seen).total_seconds() < 30:
                            continue
                        self._face_cooldown[face_name] = now

                        # Save snapshot
                        snap_dir = Path(settings.SNAPSHOTS_DIR)
                        snap_dir.mkdir(parents=True, exist_ok=True)
                        snap_name = f"face_{self.camera_id}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
                        snap_path = str(snap_dir / snap_name)
                        cv2.imwrite(snap_path, frame)

                        event_type = "face_known" if face["known"] else "face_unknown"
                        event = Event(
                            camera_id=self.camera_id,
                            event_type=event_type,
                            object_type="person",
                            confidence=face["confidence"],
                            snapshot_path=snap_path,
                            bbox=face["bbox"],
                            zone_name=face_name,
                        )
                        db.add(event)
                        db.commit()

                        logger.info(
                            f"Face {'recognized' if face['known'] else 'unknown'}: "
                            f"{face_name} on camera {self.name}"
                        )
                except Exception as e:
                    logger.debug(f"Face recognition error: {e}")
        finally:
            db.close()


class StreamManager:
    def __init__(self):
        self.streams: dict[int, CameraStream] = {}
        self._tasks: dict[int, asyncio.Task] = {}

    async def start_camera(self, camera_id: int, rtsp_url: str, name: str):
        if camera_id in self.streams:
            await self.stop_camera(camera_id)

        stream = CameraStream(camera_id, rtsp_url, name)
        if not stream.open():
            return False

        self.streams[camera_id] = stream

        # Load counting lines for this camera
        self._load_counting_lines(camera_id)

        self._tasks[camera_id] = asyncio.create_task(self._run_loop(stream))
        return True

    def _load_counting_lines(self, camera_id: int):
        """Load counting lines from DB into the tracker."""
        from app.models.ops import CountingLineModel
        db = SessionLocal()
        try:
            lines = db.query(CountingLineModel).filter(
                CountingLineModel.camera_id == camera_id,
                CountingLineModel.enabled == True,
            ).all()
            tracker = get_tracker(camera_id)
            cl_list = [
                CountingLine(
                    id=l.id, camera_id=l.camera_id, name=l.name,
                    point_a=l.point_a, point_b=l.point_b, direction=l.direction,
                )
                for l in lines
            ]
            tracker.set_counting_lines(cl_list)
            if cl_list:
                logger.info(f"Loaded {len(cl_list)} counting lines for camera {camera_id}")
        finally:
            db.close()

    async def stop_camera(self, camera_id: int):
        if camera_id in self._tasks:
            self._tasks[camera_id].cancel()
            del self._tasks[camera_id]
        if camera_id in self.streams:
            self.streams[camera_id].close()
            del self.streams[camera_id]

    async def _run_loop(self, stream: CameraStream):
        """Main processing loop for a camera stream."""
        logger.info(f"Starting processing loop for camera {stream.name}")
        try:
            while stream.running:
                frame = stream.read_frame()
                if frame is None:
                    logger.warning(f"Lost frame from {stream.name}, reconnecting...")
                    await asyncio.sleep(2)
                    stream.open()
                    continue

                await stream.process_frame(frame)
                await asyncio.sleep(0.01)  # Yield to event loop
        except asyncio.CancelledError:
            logger.info(f"Processing loop cancelled for {stream.name}")
        except Exception as e:
            logger.error(f"Error in processing loop for {stream.name}: {e}")
        finally:
            stream.close()

    def get_frame(self, camera_id: int) -> np.ndarray | None:
        stream = self.streams.get(camera_id)
        if stream:
            return stream.last_frame
        return None

    def get_detections(self, camera_id: int) -> list[dict]:
        stream = self.streams.get(camera_id)
        if stream:
            return stream.last_detections
        return []

    def get_faces(self, camera_id: int) -> list[dict]:
        stream = self.streams.get(camera_id)
        if stream:
            return stream.last_faces
        return []

    async def start_all(self):
        """Start all enabled cameras from DB."""
        detector.load()
        db = SessionLocal()
        try:
            cameras = db.query(Camera).filter(Camera.enabled == True).all()
            for cam in cameras:
                await self.start_camera(cam.id, cam.rtsp_url, cam.name)
        finally:
            db.close()

    async def stop_all(self):
        for camera_id in list(self.streams.keys()):
            await self.stop_camera(camera_id)


# Singleton
stream_manager = StreamManager()
