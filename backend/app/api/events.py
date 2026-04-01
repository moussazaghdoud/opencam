from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path

from app.core.database import get_db
from app.models.event import Event
from app.schemas.event import EventOut, EventAcknowledge

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/", response_model=list[EventOut])
def list_events(
    camera_id: int | None = None,
    event_type: str | None = None,
    acknowledged: bool | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if camera_id is not None:
        q = q.filter(Event.camera_id == camera_id)
    if event_type is not None:
        q = q.filter(Event.event_type == event_type)
    if acknowledged is not None:
        q = q.filter(Event.acknowledged == acknowledged)

    return q.order_by(Event.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/stats")
def event_stats(db: Session = Depends(get_db)):
    """Get event counts by type."""
    from sqlalchemy import func

    total = db.query(func.count(Event.id)).scalar()
    unacknowledged = db.query(func.count(Event.id)).filter(Event.acknowledged == False).scalar()
    by_type = (
        db.query(Event.event_type, func.count(Event.id))
        .group_by(Event.event_type)
        .all()
    )
    return {
        "total": total,
        "unacknowledged": unacknowledged,
        "by_type": {t: c for t, c in by_type},
    }


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


@router.patch("/{event_id}", response_model=EventOut)
def acknowledge_event(event_id: int, data: EventAcknowledge, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    event.acknowledged = data.acknowledged
    event.false_alarm = data.false_alarm
    db.commit()
    db.refresh(event)
    return event


@router.get("/{event_id}/snapshot")
def get_event_snapshot(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event or not event.snapshot_path:
        raise HTTPException(404, "Snapshot not found")

    path = Path(event.snapshot_path)
    if not path.exists():
        raise HTTPException(404, "Snapshot file not found")

    return FileResponse(path, media_type="image/jpeg")


@router.delete("/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    db.delete(event)
    db.commit()
    return {"ok": True}
