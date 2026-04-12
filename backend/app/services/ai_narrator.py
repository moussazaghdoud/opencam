"""AI Narrator — generates human-readable event narrations + suspicion scores.

Two modes:
  1. Claude API (when ANTHROPIC_API_KEY is set)
  2. Rule-based fallback (always available, no external dependency)

This service READS events — it never modifies them.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.event import Event
from app.models.camera import Camera
from app.models.ai_enrichment import AIEnrichment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior security analyst narrating CCTV events for operators.
Your job: describe what happened, provide activity context, and assess suspicion level.

RULES:
- Only state facts present in the input data. Never invent details.
- Never guess identities, motives, or intent beyond what the data shows.
- Describe the full activity picture: who/what was detected, where, when, what happened before and after.
- If a person was detected but not recognized, say so and mention whether known faces were seen nearby in time.
- If multiple events form a sequence (enter → face detected → exit), describe the sequence as a narrative.
- Mention the duration of activity if inferable from the timeline.
- Keep narration to 3-5 sentences — concise but informative.
- Keep suspicion_reason to 1-2 sentences.
- Be conservative: default to "normal" unless clear indicators exist.
- Output valid JSON only, no markdown, no code fences.

SUSPICION SCORING:
- 0.0-0.29 = "normal" — routine activity
- 0.30-0.49 = "noteworthy" — minor anomaly worth logging
- 0.50-0.69 = "unusual" — warrants operator attention
- 0.70-1.0 = "suspicious" — operator should review immediately

FACTORS THAT INCREASE SUSPICION:
- Event outside business hours (before 07:00 or after 19:00)
- Unknown face detected (especially if known faces are registered)
- Low detection confidence (< 50%)
- Zone intrusion event
- Repeated unknown face detections in short period
- Activity pattern: person detected → no face match → extended presence
- Unusual activity volume compared to daily average

FACTORS THAT DECREASE SUSPICION:
- Known face recognized
- Event during business hours
- High confidence detection
- Normal activity volume for this time of day

OUTPUT FORMAT (JSON only):
{
  "narration": "Describe the full event and surrounding activity context in 3-5 sentences.",
  "suspicion_score": 0.0,
  "suspicion_label": "normal",
  "suspicion_reason": "Explain why this score was assigned based on the evidence."
}"""


def _build_activity_context(db: Session, event: Event, camera_id: int) -> dict:
    """Build rich activity context from existing events. Read-only."""
    now = event.created_at or datetime.now()

    # --- Timeline: events from same camera in a 30-minute window around this event ---
    window_start = now - timedelta(minutes=15)
    window_end = now + timedelta(minutes=15)
    timeline = (
        db.query(Event)
        .filter(
            Event.camera_id == camera_id,
            Event.created_at >= window_start,
            Event.created_at <= window_end,
        )
        .order_by(Event.created_at.asc())
        .limit(20)
        .all()
    )
    timeline_data = [
        {
            "id": e.id,
            "type": e.event_type,
            "object": e.object_type,
            "zone": e.zone_name,
            "confidence": round(e.confidence or 0, 2),
            "time": e.created_at.strftime("%H:%M:%S") if e.created_at else None,
            "is_current": e.id == event.id,
        }
        for e in timeline
    ]

    # --- Face activity: who was seen on this camera recently ---
    face_events = (
        db.query(Event)
        .filter(
            Event.camera_id == camera_id,
            Event.event_type.in_(["face_known", "face_unknown"]),
            Event.created_at >= now - timedelta(hours=1),
        )
        .order_by(Event.created_at.desc())
        .limit(10)
        .all()
    )
    known_faces = set()
    unknown_count = 0
    for fe in face_events:
        if fe.event_type == "face_known" and fe.zone_name:
            known_faces.add(fe.zone_name)  # zone_name stores the person's name for face events
        elif fe.event_type == "face_unknown":
            unknown_count += 1

    # --- Activity volume: compare to typical ---
    hour_count = (
        db.query(sqlfunc.count(Event.id))
        .filter(
            Event.camera_id == camera_id,
            Event.created_at >= now - timedelta(hours=1),
        )
        .scalar() or 0
    )

    # Daily average for this camera (last 7 days, same hour)
    seven_days_ago = now - timedelta(days=7)
    daily_avg = (
        db.query(sqlfunc.count(Event.id))
        .filter(
            Event.camera_id == camera_id,
            Event.created_at >= seven_days_ago,
        )
        .scalar() or 0
    ) / 7.0

    # --- Duration estimate: time span of consecutive events ---
    if len(timeline) >= 2:
        first_ts = timeline[0].created_at
        last_ts = timeline[-1].created_at
        if first_ts and last_ts:
            duration_minutes = round((last_ts - first_ts).total_seconds() / 60, 1)
        else:
            duration_minutes = None
    else:
        duration_minutes = None

    return {
        "timeline": timeline_data,
        "faces_seen": {
            "known": sorted(known_faces) if known_faces else [],
            "unknown_count": unknown_count,
        },
        "activity_volume": {
            "last_hour": hour_count,
            "daily_average": round(daily_avg, 1),
            "above_average": hour_count > (daily_avg * 1.5) if daily_avg > 0 else False,
        },
        "duration_minutes": duration_minutes,
        "total_events_in_window": len(timeline),
    }


def _build_user_prompt(event: Event, camera_name: str, camera_location: str,
                       activity: dict, clip_analysis: dict | None = None) -> str:
    hour = event.created_at.hour if event.created_at else 0
    confidence_pct = round((event.confidence or 0) * 100, 1)
    time_str = event.created_at.isoformat() if event.created_at else "unknown"

    faces = activity["faces_seen"]
    volume = activity["activity_volume"]

    face_summary = ""
    if faces["known"]:
        face_summary += f"Known faces seen on this camera in the last hour: {', '.join(faces['known'])}. "
    if faces["unknown_count"] > 0:
        face_summary += f"Unknown faces detected: {faces['unknown_count']}. "
    if not faces["known"] and faces["unknown_count"] == 0:
        face_summary = "No face detections on this camera in the last hour. "

    duration_str = ""
    if activity["duration_minutes"] is not None:
        duration_str = f"Activity in the 30-minute window spans approximately {activity['duration_minutes']} minutes. "

    return (
        f"Analyze this security event and its surrounding activity:\n\n"
        f"--- CURRENT EVENT ---\n"
        f"Event ID: {event.id}\n"
        f"Type: {event.event_type}\n"
        f"Object: {event.object_type}\n"
        f"Camera: {camera_name}\n"
        f"Location: {camera_location or 'N/A'}\n"
        f"Zone: {event.zone_name or 'N/A'}\n"
        f"Confidence: {confidence_pct}%\n"
        f"Time: {time_str}\n"
        f"Hour of day: {hour}\n\n"
        f"--- ACTIVITY TIMELINE (30-min window, ★ = this event) ---\n"
        f"{json.dumps(activity['timeline'], default=str)}\n\n"
        f"--- FACE RECOGNITION CONTEXT ---\n"
        f"{face_summary}\n"
        f"--- ACTIVITY VOLUME ---\n"
        f"Events from this camera in the last hour: {volume['last_hour']}\n"
        f"Daily average: {volume['daily_average']} events/day\n"
        f"Above average: {'Yes' if volume['above_average'] else 'No'}\n\n"
        f"--- DURATION ---\n"
        f"{duration_str or 'Single isolated event.'}\n\n"
        f"Total events in 30-min window: {activity['total_events_in_window']}"
    )

    # Add clip analysis if available
    if clip_analysis:
        scene = clip_analysis.get("scene_change", {})
        scene_str = ""
        if scene.get("changed"):
            scene_str = (
                f"\n\n--- SCENE CHANGE ---\n"
                f"Type: {scene['change_type']}\n"
                f"Location: {scene['change_location']} area\n"
                f"Size: {scene['change_percent']}% of frame\n"
                f"Description: {scene['description']}"
            )

        carrying = clip_analysis.get("carrying_change", {})
        carrying_str = ""
        if carrying.get("detected"):
            carrying_str = (
                f"\n\n--- OBJECT CARRYING DETECTION ---\n"
                f"Type: {carrying['change_type']}\n"
                f"Bbox growth: {carrying['bbox_growth_percent']}%\n"
                f"Description: {carrying['description']}"
            )

        objects = clip_analysis.get("objects_detected", {})
        objects_str = ""
        if objects.get("summary"):
            objects_str = f"\n\n--- OBJECT IDENTIFICATION (YOLO Open Images, 601 classes) ---\n"
            if objects.get("on_person_entry"):
                labels = [o["label"] for o in objects["on_person_entry"]]
                objects_str += f"Objects on person at ENTRY: {', '.join(labels)}\n"
            if objects.get("on_person_exit"):
                labels = [o["label"] for o in objects["on_person_exit"]]
                objects_str += f"Objects on person at EXIT: {', '.join(labels)}\n"
            if objects.get("new_objects_on_person"):
                labels = [o["label"] for o in objects["new_objects_on_person"]]
                objects_str += f"NEW objects on person at exit (not at entry): {', '.join(labels)}\n"
            if objects.get("missing_objects_from_scene"):
                labels = [o["label"] for o in objects["missing_objects_from_scene"]]
                objects_str += f"Objects MISSING from scene: {', '.join(labels)}\n"
            if objects.get("high_alert"):
                labels = [o["label"] for o in objects["high_alert"]]
                objects_str += f"HIGH ALERT OBJECTS: {', '.join(labels)}\n"
            objects_str += f"Summary: {objects['summary']}"

        prompt += (
            f"\n\n--- VIDEO CLIP ANALYSIS (local CV, {clip_analysis['duration_seconds']}s clip) ---\n"
            f"Person visible for: {clip_analysis['person_present_seconds']}s out of {clip_analysis['duration_seconds']}s\n"
            f"Person count range: {clip_analysis['person_count_min']}-{clip_analysis['person_count_max']}\n"
            f"Entry direction: {clip_analysis['entry_direction']}\n"
            f"Exit direction: {clip_analysis['exit_direction']}\n"
            f"Movement trend: {clip_analysis['bbox_size_trend']}\n"
            f"Movement summary: {clip_analysis['movement_summary']}"
            f"{scene_str}"
            f"{carrying_str}"
            f"{objects_str}"
        )

    return prompt


# ---------------------------------------------------------------------------
# Rule-based fallback (no LLM needed)
# ---------------------------------------------------------------------------

_EVENT_TYPE_LABELS = {
    "enter": "entered",
    "count_above": "triggered a count alert in",
    "face_known": "was recognized in",
    "face_unknown": "was detected (unknown face) in",
}


def _rule_based_narration(event: Event, camera_name: str,
                          activity: dict, clip_analysis: dict | None = None) -> dict:
    """Generate narration using deterministic rules. Always works."""

    # --- Build narration text ---
    time_str = event.created_at.strftime("%H:%M") if event.created_at else "unknown time"
    action = _EVENT_TYPE_LABELS.get(event.event_type, "was detected in")
    zone = event.zone_name or "the monitored area"
    confidence_pct = round((event.confidence or 0) * 100)
    obj = (event.object_type or "object").capitalize()

    parts = [f"{obj} {action} {zone} via {camera_name} at {time_str} with {confidence_pct}% confidence."]

    # Face context
    faces = activity["faces_seen"]
    if faces["known"]:
        parts.append(f"Known faces seen recently on this camera: {', '.join(faces['known'])}.")
    if faces["unknown_count"] > 0:
        parts.append(f"{faces['unknown_count']} unknown face(s) detected in the last hour.")

    # Duration/activity context
    if activity["duration_minutes"] is not None and activity["duration_minutes"] > 1:
        parts.append(f"Activity in the area spans approximately {activity['duration_minutes']} minutes.")

    volume = activity["activity_volume"]
    if volume["last_hour"] > 1:
        parts.append(f"{volume['last_hour']} events from this camera in the last hour (daily avg: {volume['daily_average']}).")

    # Clip analysis facts
    if clip_analysis:
        parts.append(clip_analysis["movement_summary"])

    narration = " ".join(parts)

    # --- Compute suspicion score ---
    score = 0.0
    reasons = []

    # Time-based
    hour = event.created_at.hour if event.created_at else 12
    if hour < 7 or hour >= 19:
        score += 0.3
        reasons.append("outside business hours")

    # Unknown face
    if event.event_type == "face_unknown":
        score += 0.3
        reasons.append("unknown face detected")

    # Multiple unknown faces
    if faces["unknown_count"] >= 3:
        score += 0.15
        reasons.append(f"{faces['unknown_count']} unknown faces in the last hour")

    # Low confidence
    if (event.confidence or 0) < 0.5:
        score += 0.1
        reasons.append("low detection confidence")

    # Zone intrusion
    if event.event_type == "enter" and event.zone_name:
        score += 0.2
        reasons.append("zone intrusion")

    # High activity volume
    if volume["above_average"]:
        score += 0.1
        reasons.append("activity above daily average")

    # Person detected but not recognized (no known face nearby in time)
    if event.event_type in ("enter", "count_above") and not faces["known"] and faces["unknown_count"] > 0:
        score += 0.15
        reasons.append("unrecognized person with no known faces nearby")

    # Known face lowers suspicion
    if event.event_type == "face_known":
        score = max(0.0, score - 0.2)
        reasons.append("known face recognized (lower risk)")

    # Scene change — object removed or added
    if clip_analysis:
        scene = clip_analysis.get("scene_change", {})
        if scene.get("changed"):
            if scene["change_type"] == "object_removed":
                score += 0.3
                reasons.append(f"object appears removed from {scene['change_location']} area")
            elif scene["change_type"] == "object_added":
                score += 0.15
                reasons.append(f"object appears placed in {scene['change_location']} area")
            elif scene["change_type"] == "scene_altered":
                score += 0.1
                reasons.append(f"scene altered in {scene['change_location']} area")

        # Carrying detection — person picked up or put down object
        carrying = clip_analysis.get("carrying_change", {})
        if carrying.get("detected"):
            if carrying["change_type"] == "picked_up_object":
                score += 0.3
                reasons.append(f"person appears to have picked up an object (bbox grew {carrying['bbox_growth_percent']}%)")
            elif carrying["change_type"] == "put_down_object":
                score += 0.1
                reasons.append("person appears to have put down an object")

        # Object identification — what the person is carrying / what's in scene
        objects = clip_analysis.get("objects_detected", {})
        if objects.get("high_alert"):
            labels = [o["label"] for o in objects["high_alert"]]
            score += 0.5
            reasons.append(f"DANGEROUS OBJECT DETECTED: {', '.join(labels)}")
        if objects.get("new_objects_on_person"):
            labels = [o["label"] for o in objects["new_objects_on_person"]]
            score += 0.25
            reasons.append(f"person acquired object(s): {', '.join(labels)}")
        if objects.get("missing_objects_from_scene"):
            labels = [o["label"] for o in objects["missing_objects_from_scene"]]
            score += 0.2
            reasons.append(f"object(s) missing from scene: {', '.join(labels)}")

    score = min(score, 1.0)

    if score >= 0.7:
        label = "suspicious"
    elif score >= 0.5:
        label = "unusual"
    elif score >= 0.3:
        label = "noteworthy"
    else:
        label = "normal"

    reason = ". ".join(r.capitalize() for r in reasons) + "." if reasons else None

    return {
        "narration": narration,
        "suspicion_score": round(score, 2),
        "suspicion_label": label,
        "suspicion_reason": reason,
        "powered_by": "rules",
    }


# ---------------------------------------------------------------------------
# Claude API narration
# ---------------------------------------------------------------------------

async def _claude_narration(event: Event, camera_name: str, camera_location: str,
                            activity: dict, clip_analysis: dict | None = None) -> dict | None:
    """Call Claude API. Returns None on any failure (caller falls back to rules)."""
    api_key = settings.ANTHROPIC_API_KEY or os.environ.get("OPENCAM_ANTHROPIC_API_KEY")
    if not api_key:
        return None

    user_prompt = _build_user_prompt(event, camera_name, camera_location, activity, clip_analysis)

    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 512,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
            result = resp.json()
            ai_text = result["content"][0]["text"]

            # Parse JSON from response
            json_match = re.search(r"\{[\s\S]*\}", ai_text)
            if not json_match:
                logger.warning("AI narrator: no JSON in LLM response")
                return None

            data = json.loads(json_match.group())

            # Validate required fields
            if "narration" not in data or "suspicion_score" not in data:
                logger.warning("AI narrator: missing required fields in LLM response")
                return None

            # Clamp and normalize
            score = max(0.0, min(1.0, float(data["suspicion_score"])))
            label = data.get("suspicion_label", "normal")
            if label not in ("normal", "noteworthy", "unusual", "suspicious"):
                label = "normal"

            return {
                "narration": str(data["narration"])[:500],
                "suspicion_score": round(score, 2),
                "suspicion_label": label,
                "suspicion_reason": str(data.get("suspicion_reason") or "")[:200] or None,
                "powered_by": "claude",
            }

    except Exception as e:
        logger.warning(f"AI narrator Claude call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def narrate_event(event_id: int, db: Session) -> dict:
    """Narrate a single event. Uses Claude if available, falls back to rules.

    Returns a dict ready to be stored as AIEnrichment.
    Does NOT modify the events table.
    """
    from app.services.clip_recorder import clip_recorder
    from app.services.clip_analyzer import analyze_clip

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise ValueError(f"Event {event_id} not found")

    # Get camera info (read-only)
    camera = db.query(Camera).filter(Camera.id == event.camera_id).first()
    camera_name = camera.name if camera else f"Camera {event.camera_id}"
    camera_location = camera.location if camera else ""

    # Build rich activity context (read-only queries)
    activity = _build_activity_context(db, event, event.camera_id)

    # Analyze clip if available (local CV, no LLM)
    clip_analysis = None
    clip_path = clip_recorder.get_clip_path(event_id)
    if clip_path:
        try:
            clip_analysis = analyze_clip(clip_path)
            if clip_analysis:
                logger.info(f"Clip analysis for event {event_id}: {clip_analysis['movement_summary']}")
        except Exception as e:
            logger.warning(f"Clip analysis failed for event {event_id}: {e}")

    # Try Claude first, fall back to rules
    result = await _claude_narration(event, camera_name, camera_location, activity, clip_analysis)
    if result is None:
        result = _rule_based_narration(event, camera_name, activity, clip_analysis)

    result["event_id"] = event_id
    return result
