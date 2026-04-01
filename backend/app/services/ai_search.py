"""AI-powered event search using Claude API with keyword fallback."""

import os
import json
import re

import httpx
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.event import Event
from app.models.camera import Camera
from app.core.config import settings


async def ai_search(query: str, db: Session) -> dict:
    """Search events using natural language.

    1. Get recent events + cameras from DB
    2. Build a context prompt with the data
    3. Ask Claude to interpret the query and return relevant results
    4. Return structured response
    """

    # Get last 500 events
    events = db.query(Event).order_by(Event.created_at.desc()).limit(500).all()
    cameras = db.query(Camera).all()

    # Build context
    event_summary = []
    for e in events:
        cam_name = next(
            (c.name for c in cameras if c.id == e.camera_id),
            f"Camera {e.camera_id}",
        )
        event_summary.append(
            {
                "id": e.id,
                "type": e.event_type,
                "object": e.object_type,
                "camera": cam_name,
                "zone": e.zone_name,
                "confidence": e.confidence,
                "time": e.created_at.isoformat() if e.created_at else None,
                "acknowledged": e.acknowledged,
            }
        )

    camera_list = [
        {"id": c.id, "name": c.name, "location": c.location, "status": c.status}
        for c in cameras
    ]

    # If no API key, do a simple keyword search fallback
    api_key = settings.ANTHROPIC_API_KEY or os.environ.get(
        "OPENCAM_ANTHROPIC_API_KEY"
    )
    if not api_key:
        # Simple keyword fallback - filter events by matching query words
        return _keyword_search(query, event_summary)

    # Call Claude API
    system_prompt = (
        "You are an AI security assistant for OpenCam video surveillance system. "
        "You analyze security events and camera data to answer natural language queries.\n\n"
        "Given the user's query and the event data, return a JSON response with:\n"
        "{\n"
        '    "summary": "Brief natural language answer to the query",\n'
        '    "matching_event_ids": [list of event IDs that match],\n'
        '    "insights": "Any patterns or insights you notice",\n'
        '    "camera_focus": "Which camera(s) are most relevant"\n'
        "}\n\n"
        "Be concise and security-focused. Current time is " + datetime.now().isoformat()
    )

    user_message = (
        f"Query: {query}\n\n"
        f"Available cameras: {json.dumps(camera_list)}\n\n"
        f"Recent events (last 500): {json.dumps(event_summary[:100])}\n\n"
        f"Total events: {len(event_summary)}\n"
        f"Event type breakdown: {json.dumps(_count_by_type(event_summary))}"
    )

    try:
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_message}],
                },
            )
            result = resp.json()
            ai_text = result["content"][0]["text"]

            # Try to parse JSON from response
            json_match = re.search(r"\{[\s\S]*\}", ai_text)
            if json_match:
                ai_response = json.loads(json_match.group())
            else:
                ai_response = {
                    "summary": ai_text,
                    "matching_event_ids": [],
                    "insights": "",
                    "camera_focus": "",
                }

            return {
                "query": query,
                "response": ai_response,
                "total_events_searched": len(event_summary),
                "powered_by": "claude",
            }
    except Exception:
        return _keyword_search(query, event_summary)


def _keyword_search(query: str, events: list[dict]) -> dict:
    """Simple keyword fallback when Claude API is not available."""
    words = query.lower().split()
    matching = []
    for e in events:
        text = f"{e['type']} {e['object']} {e['camera']} {e['zone'] or ''}".lower()
        if any(w in text for w in words):
            matching.append(e["id"])

    return {
        "query": query,
        "response": {
            "summary": f"Found {len(matching)} events matching keywords: {', '.join(words)}",
            "matching_event_ids": matching[:50],
            "insights": "Keyword search (AI search available with OPENCAM_ANTHROPIC_API_KEY)",
            "camera_focus": "",
        },
        "total_events_searched": len(events),
        "powered_by": "keyword",
    }


def _count_by_type(events: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for e in events:
        t = e["type"]
        counts[t] = counts.get(t, 0) + 1
    return counts
