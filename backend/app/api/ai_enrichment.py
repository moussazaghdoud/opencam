"""AI Enrichment API — event narration + suspicion scoring.

All endpoints are gated behind ENABLE_AI_NARRATOR config flag.
These endpoints only READ from the events table and WRITE to ai_enrichments.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
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
    has_key = bool(settings.ANTHROPIC_API_KEY or os.environ.get("OPENCAM_ANTHROPIC_API_KEY"))
    return {
        "enabled": settings.ENABLE_AI_NARRATOR,
        "mode": "claude" if has_key else "rules",
        "feature": "event_narration",
    }
