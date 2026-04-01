"""Directional object counting service.

Counts objects crossing a defined line by tracking centroids across frames
and detecting line-crossing events using cross-product direction tests.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CountingLine:
    """A line defined by two points. Objects crossing it are counted IN or OUT."""

    id: int
    camera_id: int
    name: str
    point_a: list[float]  # [x, y] normalized 0-1
    point_b: list[float]  # [x, y] normalized 0-1
    direction: str = "down_is_in"  # down_is_in, up_is_in, left_is_in, right_is_in

    @classmethod
    def from_db(cls, row: Any) -> CountingLine:
        return cls(
            id=row.id,
            camera_id=row.camera_id,
            name=row.name,
            point_a=row.point_a,
            point_b=row.point_b,
            direction=row.direction,
        )


def _cross_product_sign(
    ax: float, ay: float, bx: float, by: float, px: float, py: float
) -> float:
    """Return sign of cross product (B-A) x (P-A). Positive = left side, negative = right side."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def _segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    """Check if segment p1-p2 intersects segment p3-p4 using cross products."""
    d1 = _cross_product_sign(p3[0], p3[1], p4[0], p4[1], p1[0], p1[1])
    d2 = _cross_product_sign(p3[0], p3[1], p4[0], p4[1], p2[0], p2[1])
    d3 = _cross_product_sign(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])
    d4 = _cross_product_sign(p1[0], p1[1], p2[0], p2[1], p4[0], p4[1])

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True

    # Collinear cases (treated as no crossing for counting purposes)
    return False


def _euclidean_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


class ObjectTracker:
    """Simple centroid tracker that assigns IDs and tracks positions across frames.

    Uses centroid distance matching — no deep SORT dependency needed.
    Detects when tracked objects cross a counting line and increments
    IN or OUT counters based on movement direction.
    """

    def __init__(
        self,
        max_disappeared: int = 50,
        max_distance: float = 0.5,
    ) -> None:
        self._next_id: int = 0
        # track_id -> (cx, cy) normalized
        self._objects: dict[int, tuple[float, float]] = {}
        # track_id -> previous (cx, cy)
        self._previous: dict[int, tuple[float, float]] = {}
        # track_id -> frames since last seen
        self._disappeared: dict[int, int] = {}
        self._max_disappeared = max_disappeared
        self._max_distance = max_distance

        # Counting state
        self._counting_lines: list[CountingLine] = []
        self._in_count: int = 0
        self._out_count: int = 0
        self._crossed: dict[int, set[int]] = {}

        # Simple side-based counting (line_id -> last known side with people)
        # None = no detection, "left" or "right" of line
        self._last_side: dict[int, str | None] = {}
        # Cooldown: don't count again for N frames after a crossing
        self._cooldown: dict[int, int] = {}
        self._cooldown_frames: int = 15

    # ------------------------------------------------------------------
    # Counting line management
    # ------------------------------------------------------------------

    def set_counting_lines(self, lines: list[CountingLine]) -> None:
        self._counting_lines = lines
        for line in lines:
            if line.id not in self._crossed:
                self._crossed[line.id] = set()

    def add_counting_line(self, line: CountingLine) -> None:
        self._counting_lines.append(line)
        self._crossed[line.id] = set()

    def remove_counting_line(self, line_id: int) -> None:
        self._counting_lines = [ln for ln in self._counting_lines if ln.id != line_id]
        self._crossed.pop(line_id, None)

    # ------------------------------------------------------------------
    # Core tracking
    # ------------------------------------------------------------------

    def _register(self, centroid: tuple[float, float]) -> int:
        track_id = self._next_id
        self._next_id += 1
        self._objects[track_id] = centroid
        self._previous[track_id] = centroid
        self._disappeared[track_id] = 0
        return track_id

    def _deregister(self, track_id: int) -> None:
        del self._objects[track_id]
        self._previous.pop(track_id, None)
        del self._disappeared[track_id]
        for line_id in self._crossed:
            self._crossed[line_id].discard(track_id)

    def update(self, detections: list[dict]) -> list[dict]:
        """Update tracker with new detections and return detections with track_ids.

        Each detection dict must have a ``bbox`` key with ``[x1, y1, x2, y2]``
        in normalized 0-1 coordinates. Returns the same dicts with an added
        ``track_id`` field.
        """
        # Compute centroids from bboxes
        input_centroids: list[tuple[float, float]] = []
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            input_centroids.append((cx, cy))

        # If no existing objects, register all
        if len(self._objects) == 0:
            for i, centroid in enumerate(input_centroids):
                tid = self._register(centroid)
                detections[i]["track_id"] = tid
            return detections

        # If no new detections, mark all as disappeared
        if len(input_centroids) == 0:
            for track_id in list(self._disappeared.keys()):
                self._disappeared[track_id] += 1
                if self._disappeared[track_id] > self._max_disappeared:
                    self._deregister(track_id)
            return detections

        # Match existing objects to new centroids using distance
        object_ids = list(self._objects.keys())
        object_centroids = list(self._objects.values())

        # Build distance matrix
        distances: list[list[float]] = []
        for oc in object_centroids:
            row = [_euclidean_distance(oc, ic) for ic in input_centroids]
            distances.append(row)

        # Greedy matching (good enough for moderate object counts)
        used_rows: set[int] = set()
        used_cols: set[int] = set()
        matches: list[tuple[int, int]] = []  # (row_idx, col_idx)

        # Flatten and sort by distance
        flat: list[tuple[float, int, int]] = []
        for r in range(len(distances)):
            for c in range(len(distances[r])):
                flat.append((distances[r][c], r, c))
        flat.sort(key=lambda x: x[0])

        for dist, r, c in flat:
            if r in used_rows or c in used_cols:
                continue
            if dist > self._max_distance:
                break
            matches.append((r, c))
            used_rows.add(r)
            used_cols.add(c)

        # Update matched objects
        for r, c in matches:
            track_id = object_ids[r]
            self._previous[track_id] = self._objects[track_id]
            self._objects[track_id] = input_centroids[c]
            self._disappeared[track_id] = 0
            detections[c]["track_id"] = track_id

        # After all matching, check crossings using ALL current detections
        self._check_crossings_simple(detections)

        # Handle unmatched existing objects
        for r in range(len(object_ids)):
            if r not in used_rows:
                track_id = object_ids[r]
                self._disappeared[track_id] += 1
                if self._disappeared[track_id] > self._max_disappeared:
                    self._deregister(track_id)

        # Register new detections
        for c in range(len(input_centroids)):
            if c not in used_cols:
                tid = self._register(input_centroids[c])
                detections[c]["track_id"] = tid

        return detections

    # ------------------------------------------------------------------
    # Line crossing detection
    # ------------------------------------------------------------------

    def _check_crossings_simple(self, detections: list[dict]) -> None:
        """Simple and reliable crossing detection.

        For each counting line, determine which side ALL detections are on.
        When all detections move from one side to the other, count a crossing.
        This works regardless of tracking accuracy.
        """
        for line in self._counting_lines:
            # Decrement cooldown
            cd = self._cooldown.get(line.id, 0)
            if cd > 0:
                self._cooldown[line.id] = cd - 1
                continue

            if not detections:
                continue

            # Find which side the majority of detections are on
            left_count = 0
            right_count = 0
            for det in detections:
                x1, y1, x2, y2 = det["bbox"]
                # Use bottom-center as the person's position (feet)
                px = (x1 + x2) / 2.0
                py = y2  # bottom of bbox

                side = _cross_product_sign(
                    line.point_a[0], line.point_a[1],
                    line.point_b[0], line.point_b[1],
                    px, py,
                )
                if side > 0:
                    left_count += 1
                elif side < 0:
                    right_count += 1

            # Determine current dominant side
            if left_count > right_count:
                current_side = "left"
            elif right_count > left_count:
                current_side = "right"
            else:
                continue  # balanced or no detections — skip

            # Check if side changed
            last_side = self._last_side.get(line.id)
            if last_side is None:
                self._last_side[line.id] = current_side
                continue

            if current_side != last_side:
                # Side changed — count crossing
                direction = self._get_direction(last_side, current_side, line)
                if direction == "in":
                    self._in_count += 1
                else:
                    self._out_count += 1
                self._last_side[line.id] = current_side
                self._cooldown[line.id] = self._cooldown_frames

    def _get_direction(self, from_side: str, to_side: str, line: CountingLine) -> str:
        """Determine IN or OUT based on movement direction and line config."""
        # For a vertical line (point_a at top, point_b at bottom):
        #   "left" side = cross product > 0 = left of line
        #   "right" side = cross product < 0 = right of line
        if line.direction == "right_is_in":
            return "in" if to_side == "right" else "out"
        elif line.direction == "left_is_in":
            return "in" if to_side == "left" else "out"
        elif line.direction == "down_is_in":
            # For horizontal line: "left" of downward vector = right side of screen
            return "in" if to_side == "left" else "out"
        elif line.direction == "up_is_in":
            return "in" if to_side == "right" else "out"
        else:
            return "in" if to_side == "right" else "out"

    # ------------------------------------------------------------------
    # Public counting API
    # ------------------------------------------------------------------

    def get_counts(self) -> dict[str, int]:
        return {
            "in": self._in_count,
            "out": self._out_count,
            "total": self._in_count + self._out_count,
            "net": self._in_count - self._out_count,
        }

    def reset_counts(self) -> None:
        self._in_count = 0
        self._out_count = 0
        for line_id in self._crossed:
            self._crossed[line_id].clear()

    def get_active_tracks(self) -> int:
        return len(self._objects)


# ---------------------------------------------------------------------------
# Module-level registry: one tracker per camera
# ---------------------------------------------------------------------------

_trackers: dict[int, ObjectTracker] = {}


def get_tracker(camera_id: int) -> ObjectTracker:
    """Get or create a tracker for a given camera."""
    if camera_id not in _trackers:
        _trackers[camera_id] = ObjectTracker()
    return _trackers[camera_id]


def remove_tracker(camera_id: int) -> None:
    _trackers.pop(camera_id, None)
