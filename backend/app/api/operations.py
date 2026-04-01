"""Operations API routes for logistics dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.ops import CountingLineModel, CountingRecord, DockSession
from app.services.counter import CountingLine, get_tracker
from app.services.activity_timer import activity_timer
from app.services.ops_stats import ops_stats
from app.services.ppe_detector import check_persons_ppe
from app.services.stream_processor import stream_manager

router = APIRouter(prefix="/api/ops", tags=["operations"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class CountingLineCreate(BaseModel):
    camera_id: int
    name: str
    point_a: list[float]  # [x, y] normalized 0-1
    point_b: list[float]  # [x, y] normalized 0-1
    direction: str = "down_is_in"
    enabled: bool = True


class CountingLineOut(BaseModel):
    id: int
    camera_id: int
    name: str
    point_a: list[float]
    point_b: list[float]
    direction: str
    enabled: bool

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    """Full operations dashboard data."""
    return ops_stats.get_dashboard_data(db)


# ---------------------------------------------------------------------------
# Counting lines CRUD
# ---------------------------------------------------------------------------


@router.get("/counting-lines")
def list_counting_lines(
    camera_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(CountingLineModel)
    if camera_id is not None:
        q = q.filter(CountingLineModel.camera_id == camera_id)
    lines = q.order_by(CountingLineModel.id).all()
    result = []
    for line in lines:
        tracker = get_tracker(line.camera_id)
        counts = tracker.get_counts()
        result.append({
            "id": line.id,
            "camera_id": line.camera_id,
            "name": line.name,
            "point_a": line.point_a,
            "point_b": line.point_b,
            "direction": line.direction,
            "enabled": line.enabled,
            "live": counts,
            "active_tracks": tracker.get_active_tracks(),
        })
    return result


@router.post("/counting-lines", response_model=CountingLineOut)
def create_counting_line(data: CountingLineCreate, db: Session = Depends(get_db)):
    # Validate normalized coordinates
    for coord in [data.point_a, data.point_b]:
        if len(coord) != 2:
            raise HTTPException(400, "Points must be [x, y] with exactly 2 values")
        if not all(0.0 <= v <= 1.0 for v in coord):
            raise HTTPException(400, "Coordinates must be normalized between 0 and 1")

    row = CountingLineModel(
        camera_id=data.camera_id,
        name=data.name,
        point_a=data.point_a,
        point_b=data.point_b,
        direction=data.direction,
        enabled=data.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Register in the tracker for this camera
    tracker = get_tracker(data.camera_id)
    tracker.add_counting_line(CountingLine.from_db(row))

    return row


@router.delete("/counting-lines/{line_id}")
def delete_counting_line(line_id: int, db: Session = Depends(get_db)):
    row = db.query(CountingLineModel).filter(CountingLineModel.id == line_id).first()
    if not row:
        raise HTTPException(404, "Counting line not found")

    # Remove from tracker
    tracker = get_tracker(row.camera_id)
    tracker.remove_counting_line(line_id)

    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/counting-lines/{line_id}/counts")
def get_line_counts(line_id: int, db: Session = Depends(get_db)):
    row = db.query(CountingLineModel).filter(CountingLineModel.id == line_id).first()
    if not row:
        raise HTTPException(404, "Counting line not found")

    tracker = get_tracker(row.camera_id)
    counts = tracker.get_counts()

    # Also pull persisted records for today
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    in_count = (
        db.query(CountingRecord)
        .filter(
            CountingRecord.line_id == line_id,
            CountingRecord.direction == "in",
            CountingRecord.timestamp >= day_start,
        )
        .count()
    )
    out_count = (
        db.query(CountingRecord)
        .filter(
            CountingRecord.line_id == line_id,
            CountingRecord.direction == "out",
            CountingRecord.timestamp >= day_start,
        )
        .count()
    )

    return {
        "line_id": line_id,
        "line_name": row.name,
        "live": counts,
        "today_persisted": {
            "in": in_count,
            "out": out_count,
            "total": in_count + out_count,
        },
        "active_tracks": tracker.get_active_tracks(),
    }


@router.post("/counting-lines/{line_id}/reset")
def reset_line_counts(line_id: int, db: Session = Depends(get_db)):
    row = db.query(CountingLineModel).filter(CountingLineModel.id == line_id).first()
    if not row:
        raise HTTPException(404, "Counting line not found")

    tracker = get_tracker(row.camera_id)
    tracker.reset_counts()
    return {"ok": True, "line_id": line_id}


# ---------------------------------------------------------------------------
# Dock status and sessions
# ---------------------------------------------------------------------------


@router.get("/docks")
def get_docks(db: Session = Depends(get_db)):
    """Dock status and timing for all counting zones."""
    return ops_stats.get_docks(db)


@router.get("/docks/{zone_id}/sessions")
def get_dock_sessions(
    zone_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Session history for a specific dock/zone."""
    sessions = (
        db.query(DockSession)
        .filter(DockSession.zone_id == zone_id)
        .order_by(DockSession.started_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": s.id,
            "zone_id": s.zone_id,
            "zone_name": s.zone_name,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "duration_seconds": s.duration_seconds,
            "peak_workers": s.peak_workers,
            "status": s.status,
        }
        for s in sessions
    ]


# ---------------------------------------------------------------------------
# Throughput and workers
# ---------------------------------------------------------------------------


@router.get("/throughput")
def get_throughput(db: Session = Depends(get_db)):
    """Hourly throughput data for charts."""
    return {
        "summary": ops_stats.get_throughput(db),
        "hourly": ops_stats.get_hourly_throughput(db),
    }


@router.get("/workers")
def get_workers(db: Session = Depends(get_db)):
    """Worker count per zone."""
    return ops_stats.get_workers(db)


# ---------------------------------------------------------------------------
# Shift and trend
# ---------------------------------------------------------------------------


@router.get("/shift-comparison")
def get_shift_comparison(db: Session = Depends(get_db)):
    """Compare current shift to previous shift."""
    return ops_stats.get_shift_comparison(db)


@router.get("/trend")
def get_trend(days: int = 7, db: Session = Depends(get_db)):
    """Daily throughput trend for the last N days."""
    if days < 1 or days > 90:
        raise HTTPException(400, "Days must be between 1 and 90")
    return ops_stats.get_trend(db, days=days)


# ---------------------------------------------------------------------------
# PPE Detection
# ---------------------------------------------------------------------------


@router.get("/ppe/check")
def check_ppe(camera_id: int):
    """Check PPE compliance for all detected persons on a camera."""
    frame = stream_manager.get_frame(camera_id)
    if frame is None:
        raise HTTPException(400, "No frame available")

    detections = stream_manager.get_detections(camera_id)
    if not detections:
        return {"persons": [], "compliant": True, "message": "No persons detected"}

    results = check_persons_ppe(frame, detections)

    all_compliant = all(r["wearing_jacket"] for r in results) if results else True

    return {
        "persons": results,
        "total_persons": len(results),
        "compliant": all_compliant,
        "violations": sum(1 for r in results if not r["wearing_jacket"]),
    }


# ---------------------------------------------------------------------------
# AI Search
# ---------------------------------------------------------------------------


@router.get("/search")
async def search_events(q: str, db: Session = Depends(get_db)):
    """AI-powered event search."""
    from app.services.ai_search import ai_search

    if not q.strip():
        raise HTTPException(400, "Query cannot be empty")
    return await ai_search(q.strip(), db)


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------


@router.get("/heatmap/{camera_id}")
def get_heatmap_image(camera_id: int):
    """Return heatmap as PNG overlay image with alpha channel."""
    from app.services.heatmap import heatmap_accumulator
    import cv2
    import io
    from fastapi.responses import StreamingResponse

    img = heatmap_accumulator.get_heatmap_image(camera_id)
    _, buffer = cv2.imencode(".png", img)
    return StreamingResponse(io.BytesIO(buffer.tobytes()), media_type="image/png")


@router.get("/heatmap/{camera_id}/stats")
def get_heatmap_stats(camera_id: int):
    """Return heatmap statistics for a camera."""
    from app.services.heatmap import heatmap_accumulator

    return heatmap_accumulator.get_stats(camera_id)


@router.post("/heatmap/{camera_id}/reset")
def reset_heatmap(camera_id: int):
    """Reset heatmap accumulator for a camera."""
    from app.services.heatmap import heatmap_accumulator

    heatmap_accumulator.reset(camera_id)
    return {"ok": True}
