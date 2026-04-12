import asyncio
import logging
import os
import platform
import queue
import threading
import time
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Any

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
from app.services.clip_recorder import clip_recorder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Work item passed from Tier 1 (real-time) → Tier 2 (background worker)
# ---------------------------------------------------------------------------

@dataclass
class WorkItem:
    camera_id: int
    camera_name: str
    frame: np.ndarray
    detections: list[dict]
    frame_count: int
    timestamp: datetime


# ---------------------------------------------------------------------------
# Zone/Rule cache — avoids DB queries on every frame
# ---------------------------------------------------------------------------

class ZoneRuleCache:
    """Caches zone and rule data per camera, refreshed periodically."""

    def __init__(self, ttl_seconds: float = 10.0):
        self._cache: dict[int, dict] = {}  # camera_id -> {zones, rules, ts}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, camera_id: int) -> list[Any] | None:
        with self._lock:
            entry = self._cache.get(camera_id)
            if entry and (time.time() - entry["ts"]) < self._ttl:
                return entry["zones"]
        return None

    def refresh(self, camera_id: int) -> list[Any]:
        db = SessionLocal()
        try:
            zones = (
                db.query(Zone)
                .filter(Zone.camera_id == camera_id, Zone.enabled == True)
                .all()
            )
            # Eagerly load rules for each zone
            zone_data = []
            for zone in zones:
                rules = (
                    db.query(Rule)
                    .filter(Rule.zone_id == zone.id, Rule.enabled == True)
                    .all()
                )
                zone_data.append({
                    "zone": zone,
                    "rules": rules,
                    "zone_id": zone.id,
                    "zone_name": zone.name,
                    "zone_points": zone.points,
                })
        finally:
            db.close()

        with self._lock:
            self._cache[camera_id] = {"zones": zone_data, "ts": time.time()}
        return zone_data

    def get_or_refresh(self, camera_id: int) -> list[Any]:
        cached = self.get(camera_id)
        if cached is not None:
            return cached
        return self.refresh(camera_id)

    def invalidate(self, camera_id: int):
        with self._lock:
            self._cache.pop(camera_id, None)


_zone_cache = ZoneRuleCache()


# ---------------------------------------------------------------------------
# Background Worker — processes Tier 2 tasks (face reco, PPE, rules, events)
# ---------------------------------------------------------------------------

class BackgroundWorker:
    """Single worker thread that processes heavy tasks for all cameras.

    Uses per-camera queues with max size 1 (backpressure: newest frame wins).
    """

    def __init__(self):
        self._queues: dict[int, queue.Queue] = {}  # camera_id -> Queue
        self._thread: threading.Thread | None = None
        self._running = False
        self._face_cooldowns: dict[int, dict[str, datetime]] = {}  # cam_id -> {name: ts}
        self._lock = threading.Lock()
        # Event loop reference for async alert calls
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="bg-worker")
        self._thread.start()
        logger.info("Background worker started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("Background worker stopped")

    def register_camera(self, camera_id: int):
        with self._lock:
            self._queues[camera_id] = queue.Queue(maxsize=settings.WORKER_QUEUE_SIZE)
            self._face_cooldowns[camera_id] = {}

    def unregister_camera(self, camera_id: int):
        with self._lock:
            self._queues.pop(camera_id, None)
            self._face_cooldowns.pop(camera_id, None)

    def submit(self, item: WorkItem):
        """Submit work. Drops old item if queue is full (backpressure)."""
        with self._lock:
            q = self._queues.get(item.camera_id)
        if q is None:
            return
        # Drop old frame if queue full — keep newest
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            pass  # should not happen after drain above

    def _run(self):
        """Main worker loop — round-robin across cameras."""
        while self._running:
            processed = False
            with self._lock:
                camera_ids = list(self._queues.keys())

            for cam_id in camera_ids:
                with self._lock:
                    q = self._queues.get(cam_id)
                if q is None:
                    continue
                try:
                    item = q.get_nowait()
                except queue.Empty:
                    continue

                processed = True
                try:
                    self._process_item(item)
                except Exception as e:
                    logger.error(f"Background worker error (cam {cam_id}): {e}", exc_info=True)

            if not processed:
                time.sleep(0.05)  # Nothing to do, avoid busy-wait

    def _process_item(self, item: WorkItem):
        """Tier 2 processing: face reco, PPE, rules, events."""
        h, w = item.frame.shape[:2]
        zones = _zone_cache.get_or_refresh(item.camera_id)

        db = SessionLocal()
        try:
            # --- Zone rules + events ---
            for zd in zones:
                objects_in_zone = [
                    d for d in item.detections
                    if check_detection_in_zone(d, zd["zone_points"], w, h)
                ]
                activity_timer.update(zd["zone_id"], len(objects_in_zone) > 0, len(objects_in_zone))

                for rule in zd["rules"]:
                    if not is_within_schedule(
                        rule.schedule_start, rule.schedule_end, rule.schedule_days
                    ):
                        continue

                    matching = [
                        d for d in item.detections
                        if (rule.object_type == "any" or d["object_type"] == rule.object_type)
                        and check_detection_in_zone(d, zd["zone_points"], w, h)
                    ]

                    triggered = False
                    if rule.trigger == "enter" and len(matching) >= rule.threshold:
                        triggered = True
                    elif rule.trigger == "count_above" and len(matching) > rule.threshold:
                        triggered = True

                    if triggered:
                        best = max(matching, key=lambda d: d["confidence"])
                        snap_dir = Path(settings.SNAPSHOTS_DIR)
                        snap_dir.mkdir(parents=True, exist_ok=True)
                        snap_name = f"{item.camera_id}_{item.timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
                        snap_path = str(snap_dir / snap_name)
                        cv2.imwrite(snap_path, item.frame)

                        event = Event(
                            camera_id=item.camera_id,
                            rule_id=rule.id,
                            event_type=rule.trigger,
                            object_type=best["object_type"],
                            confidence=best["confidence"],
                            snapshot_path=snap_path,
                            bbox=best["bbox"],
                            zone_name=zd["zone_name"],
                        )
                        db.add(event)
                        db.commit()

                        # Save clip around this event (non-blocking)
                        clip_recorder.save_clip(item.camera_id, event.id)

                        event_data = {
                            "event_type": rule.trigger,
                            "camera_name": item.camera_name,
                            "zone_name": zd["zone_name"],
                            "object_type": best["object_type"],
                            "confidence": best["confidence"],
                            "event_id": event.id,
                        }
                        if self._loop:
                            asyncio.run_coroutine_threadsafe(
                                trigger_alert(rule, event_data), self._loop
                            )

            # --- Face recognition (if enabled) ---
            if settings.ENABLE_FACE_RECOGNITION:
                if item.frame_count % (settings.FRAME_SKIP * settings.FACE_RECOGNITION_INTERVAL) == 0:
                    try:
                        face_results = face_recognizer.recognize(item.frame)
                        person_count = sum(1 for d in item.detections if d.get("object_type") == "person")
                        if person_count > 0:
                            face_results = face_results[:person_count]

                        # Update stream's face results
                        stream = stream_manager.streams.get(item.camera_id)
                        if stream:
                            stream.last_faces = face_results
                            stream._faces_ts = time.time()

                        # Log face events with cooldown
                        cooldowns = self._face_cooldowns.get(item.camera_id, {})
                        now = item.timestamp
                        for face in face_results:
                            face_name = face["name"]
                            last_seen = cooldowns.get(face_name)
                            if last_seen and (now - last_seen).total_seconds() < 30:
                                continue
                            cooldowns[face_name] = now

                            snap_dir = Path(settings.SNAPSHOTS_DIR)
                            snap_dir.mkdir(parents=True, exist_ok=True)
                            snap_name = f"face_{item.camera_id}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
                            snap_path = str(snap_dir / snap_name)
                            cv2.imwrite(snap_path, item.frame)

                            event_type = "face_known" if face["known"] else "face_unknown"
                            event = Event(
                                camera_id=item.camera_id,
                                event_type=event_type,
                                object_type="person",
                                confidence=face["confidence"],
                                snapshot_path=snap_path,
                                bbox=face["bbox"],
                                zone_name=face_name,
                            )
                            db.add(event)
                            db.commit()

                            clip_recorder.save_clip(item.camera_id, event.id)

                            logger.info(
                                f"Face {'recognized' if face['known'] else 'unknown'}: "
                                f"{face_name} on camera {item.camera_name}"
                            )
                    except Exception as e:
                        logger.warning(f"Face recognition error: {e}", exc_info=True)
        finally:
            db.close()


_bg_worker = BackgroundWorker()


# ---------------------------------------------------------------------------
# CameraStream — frame reader + Tier 1 real-time processing
# ---------------------------------------------------------------------------

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
        self._faces_ts: float = 0.0
        self.frame_count = 0
        self._frame_lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None

    def open(self) -> bool:
        try:
            source = int(self.rtsp_url) if self.rtsp_url.isdigit() else self.rtsp_url
            if isinstance(source, int) and platform.system() == "Windows":
                self.cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            else:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay"
                self.cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not self.cap.isOpened():
                logger.error(f"Cannot open camera {self.name}: {self.rtsp_url}")
                return False

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
            self._reader_thread = threading.Thread(target=self._frame_reader, daemon=True)
            self._reader_thread.start()
            logger.info(f"Camera {self.name} opened: {width}x{height} @ {fps}fps")
            return True
        except Exception as e:
            logger.error(f"Error opening camera {self.name}: {e}")
            return False

    def _frame_reader(self):
        """Background thread: drains buffer, keeps only latest frame."""
        is_video_file = not self.rtsp_url.isdigit() and not self.rtsp_url.startswith("rtsp")
        while self.running:
            if not self.cap or not self.cap.isOpened():
                time.sleep(2)
                self._reopen()
                continue
            ret, frame = self.cap.read()
            if ret:
                with self._frame_lock:
                    self.last_frame = frame
            else:
                if is_video_file:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                else:
                    logger.warning(f"Lost frame from {self.name}, reconnecting...")
                    time.sleep(2)
                    self._reopen()

    def _reopen(self):
        if self.cap:
            self.cap.release()
        source = int(self.rtsp_url) if self.rtsp_url.isdigit() else self.rtsp_url
        if isinstance(source, int) and platform.system() == "Windows":
            self.cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
        else:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay"
            self.cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if self.cap.isOpened():
            logger.info(f"Camera {self.name} reconnected")

    def close(self):
        self.running = False
        if self._reader_thread:
            self._reader_thread.join(timeout=2)
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
        with self._frame_lock:
            return self.last_frame

    async def process_frame(self, frame: np.ndarray):
        """TIER 1: Real-time processing — YOLO + tracker + heatmap only."""
        self.frame_count += 1
        if self.frame_count % settings.FRAME_SKIP != 0:
            return

        # --- YOLO detection (the critical path, ~40ms) ---
        detections = detector.detect(frame)
        self.last_detections = detections

        h, w = frame.shape[:2]

        # --- Heatmap accumulation (cheap, ~1ms) ---
        if settings.ENABLE_HEATMAP:
            heatmap_accumulator.add_detections(self.camera_id, detections, w, h)

        # --- Object tracker for counting lines (~1ms) ---
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
            for zone_id in activity_timer._zones:
                activity_timer.update(zone_id, False, 0)
            return

        # --- Submit to background worker for heavy processing ---
        _bg_worker.submit(WorkItem(
            camera_id=self.camera_id,
            camera_name=self.name,
            frame=frame.copy(),  # copy because reader thread will overwrite
            detections=detections,
            frame_count=self.frame_count,
            timestamp=datetime.now(),
        ))


# ---------------------------------------------------------------------------
# StreamManager
# ---------------------------------------------------------------------------

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
        _bg_worker.register_camera(camera_id)
        clip_recorder.start_camera(camera_id)
        self._load_counting_lines(camera_id)
        self._tasks[camera_id] = asyncio.create_task(self._run_loop(stream))
        return True

    def _load_counting_lines(self, camera_id: int):
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
        _bg_worker.unregister_camera(camera_id)
        clip_recorder.stop_camera(camera_id)
        _zone_cache.invalidate(camera_id)

    async def _run_loop(self, stream: CameraStream):
        logger.info(f"Starting processing loop for camera {stream.name}")
        try:
            while stream.running:
                frame = stream.read_frame()
                if frame is None:
                    await asyncio.sleep(0.1)
                    continue
                await stream.process_frame(frame)
                await asyncio.sleep(0.01)
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

    def get_fresh_frame(self, camera_id: int) -> np.ndarray | None:
        return self.get_frame(camera_id)

    def get_detections(self, camera_id: int) -> list[dict]:
        stream = self.streams.get(camera_id)
        if stream:
            return stream.last_detections
        return []

    def get_faces(self, camera_id: int) -> list[dict]:
        stream = self.streams.get(camera_id)
        if stream:
            if time.time() - stream._faces_ts > 5.0:
                return []
            return stream.last_faces
        return []

    async def start_all(self):
        detector.load()

        # Start background worker with the current event loop
        _bg_worker.start(asyncio.get_running_loop())

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
        _bg_worker.stop()


# Singleton
stream_manager = StreamManager()
