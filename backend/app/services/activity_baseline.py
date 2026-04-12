"""Activity Baseline — learns what's "normal" for each camera from historical events.

Builds per-camera, per-hour-of-day, per-day-of-week baselines from the events table.
Used to detect anomalies: "this is unusual because it never happens at 3am on this camera."

Read-only: only reads from the events table, never modifies it.
No new DB table: baselines stored as an in-memory dict, rebuilt periodically.
No LLM: pure statistics.
"""

import logging
import json
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.event import Event

logger = logging.getLogger(__name__)

# How many days of history to use for baseline
_BASELINE_DAYS = 14

# Rebuild baseline every N minutes
_REBUILD_INTERVAL_MINUTES = 30


class CameraHourBaseline:
    """Baseline stats for one camera at one hour of one day-of-week."""

    def __init__(self):
        self.event_count: float = 0.0        # avg events per occurrence of this hour
        self.person_count: float = 0.0       # avg person detections
        self.face_known_count: float = 0.0   # avg known face events
        self.face_unknown_count: float = 0.0 # avg unknown face events
        self.enter_count: float = 0.0        # avg zone entry events
        self.avg_confidence: float = 0.0     # avg detection confidence
        self.sample_days: int = 0            # how many days contributed to this baseline


class ActivityBaseline:
    """Learns and stores activity baselines for all cameras."""

    def __init__(self):
        # baselines[camera_id][day_of_week][hour] = CameraHourBaseline
        # day_of_week: 0=Monday, 6=Sunday
        self._baselines: dict[int, dict[int, dict[int, CameraHourBaseline]]] = {}
        self._last_rebuild: datetime | None = None
        self._lock = threading.Lock()
        self._built = False

    def rebuild(self, db: Session | None = None):
        """Rebuild baselines from the last 14 days of events. Read-only."""
        own_db = db is None
        if own_db:
            db = SessionLocal()

        try:
            cutoff = datetime.now() - timedelta(days=_BASELINE_DAYS)

            # Query all events in the window
            events = (
                db.query(Event)
                .filter(Event.created_at >= cutoff)
                .all()
            )

            if not events:
                logger.info("Activity baseline: no events in the last 14 days")
                self._built = True
                return

            # Bucket events by camera_id × day_of_week × hour
            buckets: dict[int, dict[int, dict[int, list]]] = defaultdict(
                lambda: defaultdict(lambda: defaultdict(list))
            )

            for e in events:
                if not e.created_at:
                    continue
                cam_id = e.camera_id
                dow = e.created_at.weekday()  # 0=Mon, 6=Sun
                hour = e.created_at.hour
                buckets[cam_id][dow][hour].append(e)

            # Compute baselines
            new_baselines: dict[int, dict[int, dict[int, CameraHourBaseline]]] = {}

            for cam_id, dow_data in buckets.items():
                new_baselines[cam_id] = {}
                for dow, hour_data in dow_data.items():
                    new_baselines[cam_id][dow] = {}
                    for hour, events_list in hour_data.items():
                        bl = CameraHourBaseline()

                        # Count unique days that contributed
                        unique_days = len(set(e.created_at.date() for e in events_list))
                        bl.sample_days = unique_days
                        divisor = max(unique_days, 1)

                        bl.event_count = len(events_list) / divisor
                        bl.person_count = sum(
                            1 for e in events_list if e.object_type == "person"
                        ) / divisor
                        bl.face_known_count = sum(
                            1 for e in events_list if e.event_type == "face_known"
                        ) / divisor
                        bl.face_unknown_count = sum(
                            1 for e in events_list if e.event_type == "face_unknown"
                        ) / divisor
                        bl.enter_count = sum(
                            1 for e in events_list if e.event_type == "enter"
                        ) / divisor

                        confidences = [e.confidence for e in events_list if e.confidence]
                        bl.avg_confidence = (
                            sum(confidences) / len(confidences) if confidences else 0.0
                        )

                        new_baselines[cam_id][dow][hour] = bl

            with self._lock:
                self._baselines = new_baselines
                self._last_rebuild = datetime.now()
                self._built = True

            total_cameras = len(new_baselines)
            total_entries = sum(
                sum(len(hours) for hours in dows.values())
                for dows in new_baselines.values()
            )
            logger.info(
                f"Activity baseline rebuilt: {total_cameras} cameras, "
                f"{total_entries} hour-slots, from {len(events)} events "
                f"over last {_BASELINE_DAYS} days"
            )

        finally:
            if own_db:
                db.close()

    def _ensure_fresh(self):
        """Rebuild if stale or never built."""
        if not self._built:
            self.rebuild()
            return
        if self._last_rebuild:
            age = (datetime.now() - self._last_rebuild).total_seconds() / 60
            if age > _REBUILD_INTERVAL_MINUTES:
                self.rebuild()

    def get_baseline(self, camera_id: int, dt: datetime | None = None) -> CameraHourBaseline | None:
        """Get the baseline for a camera at a specific datetime."""
        self._ensure_fresh()
        if dt is None:
            dt = datetime.now()

        dow = dt.weekday()
        hour = dt.hour

        with self._lock:
            cam_data = self._baselines.get(camera_id)
            if not cam_data:
                return None
            dow_data = cam_data.get(dow)
            if not dow_data:
                return None
            return dow_data.get(hour)

    def score_anomaly(self, camera_id: int, event: Event) -> dict:
        """Score how anomalous an event is compared to baseline.

        Returns:
          - anomaly_score: float 0-1
          - is_anomalous: bool (score >= 0.5)
          - reasons: list of strings explaining why
          - baseline_summary: text description of what's normal
        """
        result = {
            "anomaly_score": 0.0,
            "is_anomalous": False,
            "reasons": [],
            "baseline_summary": "No baseline data available for this camera.",
        }

        dt = event.created_at or datetime.now()
        baseline = self.get_baseline(camera_id, dt)

        if not baseline or baseline.sample_days < 2:
            result["baseline_summary"] = "Insufficient historical data (need at least 2 days)."
            return result

        score = 0.0
        reasons = []
        dow_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][dt.weekday()]

        # --- Check if this event type is unusual for this hour ---
        if event.event_type == "face_unknown":
            if baseline.face_unknown_count < 0.5:
                score += 0.3
                reasons.append(
                    f"Unknown faces are rare on this camera at {dt.hour}:00 on {dow_name}s "
                    f"(avg {baseline.face_unknown_count:.1f}/hour)"
                )

        if event.event_type == "enter":
            if baseline.enter_count < 0.5:
                score += 0.25
                reasons.append(
                    f"Zone entries are rare at {dt.hour}:00 on {dow_name}s "
                    f"(avg {baseline.enter_count:.1f}/hour)"
                )

        # --- Check if current volume is unusual ---
        # Get current hour's actual event count
        db = SessionLocal()
        try:
            hour_start = dt.replace(minute=0, second=0, microsecond=0)
            current_count = (
                db.query(sqlfunc.count(Event.id))
                .filter(
                    Event.camera_id == camera_id,
                    Event.created_at >= hour_start,
                )
                .scalar() or 0
            )
        finally:
            db.close()

        if baseline.event_count > 0:
            volume_ratio = current_count / baseline.event_count
            if volume_ratio > 3.0:
                score += 0.2
                reasons.append(
                    f"Activity is {volume_ratio:.1f}x higher than normal "
                    f"({current_count} events this hour vs avg {baseline.event_count:.1f})"
                )
            elif volume_ratio < 0.2 and current_count > 0:
                score += 0.1
                reasons.append(
                    f"Activity is unusually low ({current_count} vs avg {baseline.event_count:.1f}/hour)"
                )
        elif current_count > 0:
            # No baseline events for this hour = any activity is unusual
            score += 0.35
            reasons.append(
                f"No activity has been recorded at {dt.hour}:00 on {dow_name}s before"
            )

        # --- Check if confidence is unusual ---
        if baseline.avg_confidence > 0 and event.confidence:
            if event.confidence < baseline.avg_confidence * 0.6:
                score += 0.1
                reasons.append(
                    f"Detection confidence ({event.confidence:.0%}) is below normal "
                    f"(avg {baseline.avg_confidence:.0%})"
                )

        # --- Check unknown/known face ratio ---
        if event.event_type == "face_unknown" and baseline.face_known_count > 2:
            if baseline.face_unknown_count < 1:
                score += 0.15
                reasons.append(
                    f"This camera usually sees known faces at this hour "
                    f"({baseline.face_known_count:.1f} known vs {baseline.face_unknown_count:.1f} unknown avg)"
                )

        score = min(score, 1.0)

        # Build baseline summary
        summary_parts = [
            f"Normal for this camera on {dow_name}s at {dt.hour}:00:",
            f"{baseline.event_count:.1f} events/hour,",
            f"{baseline.person_count:.1f} persons,",
            f"{baseline.face_known_count:.1f} known faces,",
            f"{baseline.face_unknown_count:.1f} unknown faces.",
            f"Based on {baseline.sample_days} days of data.",
        ]

        result["anomaly_score"] = round(score, 2)
        result["is_anomalous"] = score >= 0.5
        result["reasons"] = reasons
        result["baseline_summary"] = " ".join(summary_parts)

        return result


# Singleton
activity_baseline = ActivityBaseline()
