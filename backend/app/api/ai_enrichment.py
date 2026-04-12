"""AI Enrichment API — event narration + suspicion scoring.

All endpoints are gated behind ENABLE_AI_NARRATOR config flag.
These endpoints only READ from the events table and WRITE to ai_enrichments.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.ai_enrichment import AIEnrichment
from app.schemas.ai_enrichment import AIEnrichmentOut
from app.services.ai_narrator import narrate_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai-enrichment"])


def _check_enabled():
    if not settings.ENABLE_AI_NARRATOR:
        raise HTTPException(503, "AI narrator is disabled (set OPENCAM_ENABLE_AI_NARRATOR=true)")


@router.post("/enrich/{event_id}", response_model=AIEnrichmentOut)
async def enrich_event(event_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Enrich a single event with narration + suspicion score.

    If already enriched, returns cached result (unless force=true to re-analyze).
    If not, calls AI narrator (Claude or rule-based fallback).
    """
    _check_enabled()

    # Check cache first (skip if force re-analyze)
    existing = db.query(AIEnrichment).filter(AIEnrichment.event_id == event_id).first()
    if existing and not force:
        return existing
    if existing and force:
        db.delete(existing)
        db.commit()

    # Generate narration
    try:
        result = await narrate_event(event_id, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error(f"AI enrichment failed for event {event_id}: {e}")
        raise HTTPException(500, "AI enrichment failed")

    # Store in separate table
    enrichment = AIEnrichment(
        event_id=result["event_id"],
        narration=result["narration"],
        suspicion_score=result["suspicion_score"],
        suspicion_label=result["suspicion_label"],
        suspicion_reason=result.get("suspicion_reason"),
        powered_by=result["powered_by"],
    )
    db.add(enrichment)
    db.commit()
    db.refresh(enrichment)

    logger.info(
        f"Enriched event {event_id}: {result['suspicion_label']} "
        f"({result['suspicion_score']}) powered_by={result['powered_by']}"
    )
    return enrichment


@router.get("/enrichment/{event_id}", response_model=AIEnrichmentOut)
def get_enrichment(event_id: int, db: Session = Depends(get_db)):
    """Get cached enrichment for an event (no LLM call)."""
    _check_enabled()

    enrichment = db.query(AIEnrichment).filter(AIEnrichment.event_id == event_id).first()
    if not enrichment:
        raise HTTPException(404, "Event not yet enriched")
    return enrichment


@router.get("/status")
def ai_status():
    """Check if AI narrator is enabled and which mode is active."""
    import os
    from app.services.activity_baseline import activity_baseline
    has_key = bool(settings.ANTHROPIC_API_KEY or os.environ.get("OPENCAM_ANTHROPIC_API_KEY"))
    return {
        "enabled": settings.ENABLE_AI_NARRATOR,
        "mode": "claude" if has_key else "rules",
        "feature": "event_narration",
        "clip_recording": settings.ENABLE_CLIP_RECORDING,
        "object_identification": settings.ENABLE_OBJECT_IDENTIFICATION,
        "baseline_learned": activity_baseline._built,
        "baseline_last_rebuild": activity_baseline._last_rebuild.isoformat() if activity_baseline._last_rebuild else None,
    }


@router.post("/baseline/rebuild")
def rebuild_baseline(db: Session = Depends(get_db)):
    """Force rebuild the activity baseline from historical events."""
    _check_enabled()
    from app.services.activity_baseline import activity_baseline
    activity_baseline.rebuild(db)
    return {
        "ok": True,
        "last_rebuild": activity_baseline._last_rebuild.isoformat() if activity_baseline._last_rebuild else None,
    }


@router.get("/baseline/{camera_id}")
def get_baseline(camera_id: int):
    """Get the learned baseline for a camera at the current time."""
    _check_enabled()
    from app.services.activity_baseline import activity_baseline
    from datetime import datetime

    now = datetime.now()
    bl = activity_baseline.get_baseline(camera_id, now)
    dow_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][now.weekday()]

    if not bl:
        return {
            "camera_id": camera_id,
            "day": dow_name,
            "hour": now.hour,
            "has_data": False,
            "message": "No baseline data for this camera at this time.",
        }

    return {
        "camera_id": camera_id,
        "day": dow_name,
        "hour": now.hour,
        "has_data": True,
        "sample_days": bl.sample_days,
        "avg_events_per_hour": round(bl.event_count, 1),
        "avg_persons": round(bl.person_count, 1),
        "avg_known_faces": round(bl.face_known_count, 1),
        "avg_unknown_faces": round(bl.face_unknown_count, 1),
        "avg_zone_entries": round(bl.enter_count, 1),
        "avg_confidence": round(bl.avg_confidence, 3),
    }


# ---------------------------------------------------------------------------
# Detection Preferences — user-configurable object detection settings
# ---------------------------------------------------------------------------

@router.get("/detection-prefs")
def get_detection_prefs():
    """Get current detection preferences (which objects to detect/announce)."""
    from app.services.object_identifier import detection_prefs, object_identifier
    all_classes = object_identifier.get_all_class_names() if settings.ENABLE_OBJECT_IDENTIFICATION else []
    return {
        "prefs": detection_prefs.to_dict(),
        "available_classes": all_classes,
        "object_identification_enabled": settings.ENABLE_OBJECT_IDENTIFICATION,
    }


class DetectionPrefsUpdate(BaseModel):
    enabled: list[str] | None = None
    high_alert: list[str] | None = None
    announce: list[str] | None = None


@router.put("/detection-prefs")
def update_detection_prefs(data: DetectionPrefsUpdate):
    """Update detection preferences."""
    from app.services.object_identifier import detection_prefs
    detection_prefs.update(
        enabled=data.enabled,
        high_alert=data.high_alert,
        announce=data.announce,
    )
    logger.info(f"Detection prefs updated: {len(detection_prefs.enabled_labels)} enabled, "
                f"{len(detection_prefs.announce_labels)} announced, "
                f"{len(detection_prefs.high_alert_labels)} high-alert")
    return {"ok": True, "prefs": detection_prefs.to_dict()}
