"""Clip Recorder — maintains a rolling frame buffer per camera and saves short clips on demand.

Non-intrusive: reads frames via stream_manager.get_frame() (public API).
Low CPU: captures at ~2 FPS, resized to 320px wide.
Low memory: ring buffer of ~30 frames per camera (~15 seconds).
"""

import logging
import os
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

# Frame stored in buffer: (timestamp, frame_resized)
BufferFrame = tuple[float, np.ndarray]

_CAPTURE_FPS = 2         # Frames per second to buffer
_BUFFER_SECONDS = 15     # Seconds of history to keep
_POST_EVENT_SECONDS = 5  # Seconds to record after trigger
_RESIZE_WIDTH = 320      # Resize frames to save memory


class CameraBuffer:
    """Ring buffer for a single camera."""

    def __init__(self, max_frames: int):
        self._buffer: deque[BufferFrame] = deque(maxlen=max_frames)
        self._lock = threading.Lock()

    def add(self, ts: float, frame: np.ndarray):
        with self._lock:
            self._buffer.append((ts, frame))

    def snapshot(self) -> list[BufferFrame]:
        """Return a copy of current buffer contents."""
        with self._lock:
            return list(self._buffer)

    def clear(self):
        with self._lock:
            self._buffer.clear()


class ClipRecorder:
    """Manages ring buffers for all cameras and saves clips on event trigger."""

    def __init__(self):
        self._buffers: dict[int, CameraBuffer] = {}
        self._threads: dict[int, threading.Thread] = {}
        self._running: dict[int, bool] = {}
        self._saving: set[int] = set()  # event_ids currently being saved

    def start_camera(self, camera_id: int):
        """Start buffering frames for a camera."""
        if not settings.ENABLE_CLIP_RECORDING:
            return
        if camera_id in self._threads:
            return

        max_frames = _CAPTURE_FPS * _BUFFER_SECONDS
        self._buffers[camera_id] = CameraBuffer(max_frames)
        self._running[camera_id] = True

        t = threading.Thread(
            target=self._capture_loop,
            args=(camera_id,),
            daemon=True,
            name=f"clip-buf-{camera_id}",
        )
        self._threads[camera_id] = t
        t.start()
        logger.info(f"Clip buffer started for camera {camera_id}")

    def stop_camera(self, camera_id: int):
        self._running[camera_id] = False
        self._threads.pop(camera_id, None)
        self._buffers.pop(camera_id, None)

    def _capture_loop(self, camera_id: int):
        """Continuously capture frames at low FPS into ring buffer."""
        from app.services.stream_processor import stream_manager

        interval = 1.0 / _CAPTURE_FPS
        while self._running.get(camera_id, False):
            frame = stream_manager.get_frame(camera_id)
            if frame is not None:
                # Resize to save memory
                h, w = frame.shape[:2]
                if w > _RESIZE_WIDTH:
                    scale = _RESIZE_WIDTH / w
                    small = cv2.resize(frame, (_RESIZE_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)
                else:
                    small = frame.copy()
                buf = self._buffers.get(camera_id)
                if buf:
                    buf.add(time.time(), small)
            time.sleep(interval)

    def save_clip(self, camera_id: int, event_id: int) -> str | None:
        """Save the current buffer + post-event frames as a video clip.

        Returns the clip file path, or None if no frames available.
        Non-blocking: runs in a separate thread.
        """
        if not settings.ENABLE_CLIP_RECORDING:
            return None

        buf = self._buffers.get(camera_id)
        if not buf:
            return None

        # Snapshot the pre-event buffer
        pre_frames = buf.snapshot()
        if not pre_frames:
            return None

        # Avoid duplicate saves for the same event
        if event_id in self._saving:
            return None
        self._saving.add(event_id)

        # Save in background thread to not block the caller
        t = threading.Thread(
            target=self._save_clip_sync,
            args=(camera_id, event_id, pre_frames),
            daemon=True,
        )
        t.start()

        # Return the expected path (file will appear shortly)
        clips_dir = Path(settings.CLIPS_DIR)
        return str(clips_dir / f"evt_{event_id}.mp4")

    def _save_clip_sync(self, camera_id: int, event_id: int, pre_frames: list[BufferFrame]):
        """Synchronous clip saving: pre-event buffer + post-event capture."""
        from app.services.stream_processor import stream_manager

        try:
            # Capture post-event frames
            post_frames: list[BufferFrame] = []
            interval = 1.0 / _CAPTURE_FPS
            end_time = time.time() + _POST_EVENT_SECONDS
            while time.time() < end_time:
                frame = stream_manager.get_frame(camera_id)
                if frame is not None:
                    h, w = frame.shape[:2]
                    if w > _RESIZE_WIDTH:
                        scale = _RESIZE_WIDTH / w
                        small = cv2.resize(frame, (_RESIZE_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)
                    else:
                        small = frame.copy()
                    post_frames.append((time.time(), small))
                time.sleep(interval)

            all_frames = pre_frames + post_frames
            if len(all_frames) < 3:
                return

            # Write video file
            clips_dir = Path(settings.CLIPS_DIR)
            clips_dir.mkdir(parents=True, exist_ok=True)
            clip_path = clips_dir / f"evt_{event_id}.mp4"

            h, w = all_frames[0][1].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(clip_path), fourcc, _CAPTURE_FPS, (w, h))

            for _, frame in all_frames:
                if frame.shape[:2] == (h, w):
                    writer.write(frame)
            writer.release()

            size_kb = os.path.getsize(clip_path) / 1024
            duration = len(all_frames) / _CAPTURE_FPS
            logger.info(f"Clip saved: {clip_path} ({duration:.1f}s, {size_kb:.0f}KB, {len(all_frames)} frames)")

        except Exception as e:
            logger.error(f"Clip save failed for event {event_id}: {e}")
        finally:
            self._saving.discard(event_id)

    def get_clip_path(self, event_id: int) -> str | None:
        """Check if a clip exists for an event."""
        clip_path = Path(settings.CLIPS_DIR) / f"evt_{event_id}.mp4"
        if clip_path.exists():
            return str(clip_path)
        return None


# Singleton
clip_recorder = ClipRecorder()
