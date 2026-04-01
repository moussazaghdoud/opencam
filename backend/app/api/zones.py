from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.zone import Zone
from app.schemas.zone import ZoneCreate, ZoneUpdate, ZoneOut

router = APIRouter(prefix="/api/zones", tags=["zones"])


@router.get("/", response_model=list[ZoneOut])
def list_zones(camera_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Zone)
    if camera_id is not None:
        q = q.filter(Zone.camera_id == camera_id)
    return q.order_by(Zone.id).all()


@router.post("/", response_model=ZoneOut)
def create_zone(data: ZoneCreate, db: Session = Depends(get_db)):
    zone = Zone(**data.model_dump())
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.get("/{zone_id}", response_model=ZoneOut)
def get_zone(zone_id: int, db: Session = Depends(get_db)):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(404, "Zone not found")
    return zone


@router.patch("/{zone_id}", response_model=ZoneOut)
def update_zone(zone_id: int, data: ZoneUpdate, db: Session = Depends(get_db)):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(404, "Zone not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(zone, key, value)
    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db)):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(404, "Zone not found")
    db.delete(zone)
    db.commit()
    return {"ok": True}
