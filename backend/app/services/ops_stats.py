"""Operations statistics aggregator.

Pulls data from the counting service, activity timer, and database
to produce a unified operations dashboard payload.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.ops import CountingLineModel, CountingRecord, DockSession
from app.models.zone import Zone
from app.models.event import Event
from app.services.counter import get_tracker, _trackers
from app.services.activity_timer import activity_timer


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OpsStats:
    """Aggregates counting, timing, and detection stats for the operations dashboard."""

    # ------------------------------------------------------------------
    # Main dashboard payload
    # ------------------------------------------------------------------

    def get_dashboard_data(self, db: Session) -> dict[str, Any]:
        """Return full operations dashboard data."""
        return {
            "throughput": self._get_throughput(db),
            "docks": self._get_docks(db),
            "workers": self._get_workers(db),
            "safety": self._get_safety(db),
            "hourly_throughput": self._get_hourly_throughput(db),
            "alerts": self._get_recent_alerts(db),
        }

    # ------------------------------------------------------------------
    # Throughput
    # ------------------------------------------------------------------

    def _get_throughput(self, db: Session) -> dict[str, Any]:
        now = _now()
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        current_hour = (
            db.query(func.count(CountingRecord.id))
            .filter(CountingRecord.timestamp >= hour_start)
            .scalar()
            or 0
        )
        today_total = (
            db.query(func.count(CountingRecord.id))
            .filter(CountingRecord.timestamp >= day_start)
            .scalar()
            or 0
        )

        # Estimated daily target (simple heuristic: 8 working hours)
        hours_elapsed = max((now - day_start).total_seconds() / 3600, 0.1)
        pace_per_hour = today_total / hours_elapsed
        projected = int(pace_per_hour * 8)
        target = 500  # configurable default target

        return {
            "current_hour": current_hour,
            "today_total": today_total,
            "target": target,
            "projected": projected,
            "pace_percent": round((today_total / max(target, 1)) * 100, 1),
        }

    def get_throughput(self, db: Session) -> dict[str, Any]:
        """Public accessor for throughput data."""
        return self._get_throughput(db)

    # ------------------------------------------------------------------
    # Dock status
    # ------------------------------------------------------------------

    def _get_docks(self, db: Session) -> list[dict[str, Any]]:
        zones = db.query(Zone).filter(Zone.zone_type == "counting").all()
        docks: list[dict[str, Any]] = []

        for zone in zones:
            stats = activity_timer.get_zone_stats(zone.id)
            current_load_time = stats["current_session_seconds"]

            # Latest session from DB
            last_session = (
                db.query(DockSession)
                .filter(DockSession.zone_id == zone.id)
                .order_by(DockSession.started_at.desc())
                .first()
            )

            docks.append({
                "id": zone.id,
                "name": zone.name,
                "camera_id": zone.camera_id,
                "status": "active" if stats["is_active"] else "idle",
                "current_load_time": round(current_load_time, 1),
                "truck_present": stats["is_active"],
                "worker_count": stats["current_object_count"],
                "total_active_today": stats["total_active_seconds_today"],
                "sessions_today": stats["sessions_today"],
                "idle_seconds": stats["idle_seconds"],
            })

        return docks

    def get_docks(self, db: Session) -> list[dict[str, Any]]:
        """Public accessor for dock status."""
        return self._get_docks(db)

    # ------------------------------------------------------------------
    # Worker counts
    # ------------------------------------------------------------------

    def _get_workers(self, db: Session) -> dict[str, Any]:
        all_stats = activity_timer.get_all_stats()
        per_zone: dict[str, int] = {}
        total = 0

        zones = {z.id: z.name for z in db.query(Zone).all()}

        for zone_id, stats in all_stats.items():
            zone_name = zones.get(zone_id, f"Zone {zone_id}")
            count = stats["current_object_count"]
            per_zone[zone_name] = count
            total += count

        return {
            "total_detected": total,
            "per_zone": per_zone,
        }

    def get_workers(self, db: Session) -> dict[str, Any]:
        """Public accessor for worker counts."""
        return self._get_workers(db)

    # ------------------------------------------------------------------
    # Safety metrics
    # ------------------------------------------------------------------

    def _get_safety(self, db: Session) -> dict[str, Any]:
        now = _now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        violations_today = (
            db.query(func.count(Event.id))
            .filter(
                Event.created_at >= day_start,
                Event.event_type.in_(["enter", "count_above"]),
            )
            .scalar()
            or 0
        )

        # Safety score: starts at 100, loses points per violation (capped at 0)
        score = max(100 - violations_today * 2, 0)

        return {
            "score": score,
            "ppe_compliance_percent": 100.0,  # placeholder until PPE detection is added
            "violations_today": violations_today,
        }

    # ------------------------------------------------------------------
    # Hourly throughput chart data
    # ------------------------------------------------------------------

    def _get_hourly_throughput(self, db: Session) -> list[dict[str, Any]]:
        now = _now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        records = (
            db.query(CountingRecord)
            .filter(CountingRecord.timestamp >= day_start)
            .all()
        )

        # Bucket by hour
        buckets: dict[int, int] = {h: 0 for h in range(24)}
        for rec in records:
            if rec.timestamp:
                buckets[rec.timestamp.hour] += 1

        return [{"hour": h, "count": c} for h, c in sorted(buckets.items())]

    def get_hourly_throughput(self, db: Session) -> list[dict[str, Any]]:
        """Public accessor for hourly throughput."""
        return self._get_hourly_throughput(db)

    # ------------------------------------------------------------------
    # Recent ops alerts
    # ------------------------------------------------------------------

    def _get_recent_alerts(self, db: Session) -> list[dict[str, Any]]:
        now = _now()
        since = now - timedelta(hours=24)

        events = (
            db.query(Event)
            .filter(Event.created_at >= since)
            .order_by(Event.created_at.desc())
            .limit(20)
            .all()
        )

        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "object_type": e.object_type,
                "zone_name": e.zone_name,
                "confidence": e.confidence,
                "acknowledged": e.acknowledged,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]

    # ------------------------------------------------------------------
    # Shift comparison
    # ------------------------------------------------------------------

    def get_shift_comparison(self, db: Session) -> dict[str, Any]:
        """Compare current shift to previous shift throughput.

        Assumes two 12-hour shifts: day (06:00-18:00) and night (18:00-06:00).
        """
        now = _now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if now.hour >= 6 and now.hour < 18:
            current_start = today.replace(hour=6)
            previous_start = today.replace(hour=6) - timedelta(hours=12)
            previous_end = today.replace(hour=6)
            shift_name = "day"
        else:
            if now.hour >= 18:
                current_start = today.replace(hour=18)
                previous_start = today.replace(hour=6)
                previous_end = today.replace(hour=18)
            else:
                current_start = (today - timedelta(days=1)).replace(hour=18)
                previous_start = (today - timedelta(days=1)).replace(hour=6)
                previous_end = (today - timedelta(days=1)).replace(hour=18)
            shift_name = "night"

        current_count = (
            db.query(func.count(CountingRecord.id))
            .filter(CountingRecord.timestamp >= current_start)
            .scalar()
            or 0
        )

        previous_count = (
            db.query(func.count(CountingRecord.id))
            .filter(
                CountingRecord.timestamp >= previous_start,
                CountingRecord.timestamp < previous_end,
            )
            .scalar()
            or 0
        )

        change_percent = 0.0
        if previous_count > 0:
            change_percent = round(
                ((current_count - previous_count) / previous_count) * 100, 1
            )

        return {
            "current_shift": shift_name,
            "current_count": current_count,
            "previous_count": previous_count,
            "change_percent": change_percent,
        }

    # ------------------------------------------------------------------
    # Multi-day trend
    # ------------------------------------------------------------------

    def get_trend(self, db: Session, days: int = 7) -> dict[str, Any]:
        """Return daily throughput totals for the last N days."""
        now = _now()
        start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

        records = (
            db.query(CountingRecord)
            .filter(CountingRecord.timestamp >= start)
            .all()
        )

        daily: dict[str, int] = {}
        for i in range(days):
            day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            daily[day] = 0

        for rec in records:
            if rec.timestamp:
                day_key = rec.timestamp.strftime("%Y-%m-%d")
                if day_key in daily:
                    daily[day_key] += 1

        return {
            "days": days,
            "daily": [{"date": d, "count": c} for d, c in sorted(daily.items())],
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

ops_stats = OpsStats()
