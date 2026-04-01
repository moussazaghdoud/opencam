"""Zone activity timer service.

Tracks how long zones are active (have people/objects in them),
accumulates session history, and provides idle alerting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ActivitySession:
    """One continuous period of activity in a zone."""

    start: datetime
    end: datetime | None = None
    duration: float = 0.0
    peak_object_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "duration": self.duration,
            "peak_object_count": self.peak_object_count,
        }


@dataclass
class _ZoneState:
    """Internal mutable state for a single zone."""

    is_active: bool = False
    active_since: datetime | None = None
    idle_since: datetime | None = None
    total_active_seconds: float = 0.0
    current_object_count: int = 0
    sessions: list[ActivitySession] = field(default_factory=list)
    # Day boundary for resetting daily totals
    _day: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_str() -> str:
    return _now().strftime("%Y-%m-%d")


class ZoneActivityTimer:
    """Tracks activity duration in zones for dock timing and occupancy analytics."""

    def __init__(self) -> None:
        self._zones: dict[int, _ZoneState] = {}

    def _get_zone(self, zone_id: int) -> _ZoneState:
        if zone_id not in self._zones:
            self._zones[zone_id] = _ZoneState(idle_since=_now(), _day=_today_str())
        state = self._zones[zone_id]
        # Reset daily totals on day boundary
        today = _today_str()
        if state._day != today:
            state.total_active_seconds = 0.0
            state.sessions = []
            state._day = today
        return state

    # ------------------------------------------------------------------
    # Core update — call every processed frame
    # ------------------------------------------------------------------

    def update(self, zone_id: int, has_objects: bool, object_count: int = 0) -> None:
        """Update zone activity state. Call on every processed frame.

        Args:
            zone_id: ID of the zone being updated.
            has_objects: Whether any objects are currently in the zone.
            object_count: Number of objects currently in the zone.
        """
        now = _now()
        state = self._get_zone(zone_id)
        state.current_object_count = object_count

        if has_objects and not state.is_active:
            # Zone just became active
            state.is_active = True
            state.active_since = now
            state.idle_since = None
            state.sessions.append(ActivitySession(start=now, peak_object_count=object_count))

        elif has_objects and state.is_active:
            # Zone still active — update current session peak
            if state.sessions:
                session = state.sessions[-1]
                session.peak_object_count = max(session.peak_object_count, object_count)

        elif not has_objects and state.is_active:
            # Zone just became idle
            state.is_active = False
            state.idle_since = now
            if state.active_since is not None:
                elapsed = (now - state.active_since).total_seconds()
                state.total_active_seconds += elapsed
                # Close current session
                if state.sessions:
                    session = state.sessions[-1]
                    session.end = now
                    session.duration = elapsed
            state.active_since = None

        # else: still idle — no change

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_zone_stats(self, zone_id: int) -> dict[str, Any]:
        """Return current stats for a single zone."""
        state = self._get_zone(zone_id)
        now = _now()

        # If currently active, include live elapsed time
        current_session_seconds = 0.0
        if state.is_active and state.active_since is not None:
            current_session_seconds = (now - state.active_since).total_seconds()

        idle_seconds = 0.0
        if state.idle_since is not None:
            idle_seconds = (now - state.idle_since).total_seconds()

        return {
            "zone_id": zone_id,
            "is_active": state.is_active,
            "active_since": state.active_since.isoformat() if state.active_since else None,
            "idle_since": state.idle_since.isoformat() if state.idle_since else None,
            "idle_seconds": round(idle_seconds, 1),
            "current_session_seconds": round(current_session_seconds, 1),
            "total_active_seconds_today": round(
                state.total_active_seconds + current_session_seconds, 1
            ),
            "current_object_count": state.current_object_count,
            "sessions_today": len(state.sessions),
            "recent_sessions": [s.to_dict() for s in state.sessions[-10:]],
        }

    def get_all_stats(self) -> dict[str, Any]:
        """Return stats for all tracked zones."""
        return {
            zone_id: self.get_zone_stats(zone_id)
            for zone_id in sorted(self._zones.keys())
        }

    def check_idle_alert(self, zone_id: int, threshold_seconds: int = 300) -> bool:
        """Return True if the zone has been idle longer than threshold."""
        state = self._get_zone(zone_id)
        if state.is_active:
            return False
        if state.idle_since is None:
            return False
        idle_duration = (_now() - state.idle_since).total_seconds()
        return idle_duration >= threshold_seconds

    def get_current_session_duration(self, zone_id: int) -> float | None:
        """Return current active session duration in seconds, or None if idle."""
        state = self._get_zone(zone_id)
        if not state.is_active or state.active_since is None:
            return None
        return (_now() - state.active_since).total_seconds()

    def reset_zone(self, zone_id: int) -> None:
        """Reset all state for a zone."""
        self._zones.pop(zone_id, None)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

activity_timer = ZoneActivityTimer()
