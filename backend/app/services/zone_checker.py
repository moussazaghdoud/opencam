import numpy as np
from datetime import datetime


def point_in_polygon(point: list[float], polygon: list[list[float]]) -> bool:
    """Ray casting algorithm to check if point is inside polygon.
    All coordinates should be normalized (0-1)."""
    x, y = point
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside


def check_detection_in_zone(
    detection: dict,
    zone_points: list[list[float]],
    frame_width: int,
    frame_height: int,
) -> bool:
    """Check if a detection's center point falls within a zone."""
    cx, cy = detection["center"]
    # Normalize to 0-1
    norm_x = cx / frame_width
    norm_y = cy / frame_height
    return point_in_polygon([norm_x, norm_y], zone_points)


def is_within_schedule(
    schedule_start: str | None,
    schedule_end: str | None,
    schedule_days: list[int],
) -> bool:
    """Check if current time falls within the rule's schedule."""
    now = datetime.now()
    current_day = now.weekday()  # 0=Monday

    if current_day not in schedule_days:
        return False

    if schedule_start is None or schedule_end is None:
        return True  # No time restriction = always active

    current_time = now.strftime("%H:%M")

    if schedule_start <= schedule_end:
        return schedule_start <= current_time <= schedule_end
    else:
        # Overnight schedule (e.g., 22:00 - 06:00)
        return current_time >= schedule_start or current_time <= schedule_end
