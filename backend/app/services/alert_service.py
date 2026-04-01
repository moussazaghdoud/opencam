import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Track last alert time per rule to enforce cooldown
_last_alert: dict[int, datetime] = {}


def can_alert(rule_id: int, cooldown_seconds: int) -> bool:
    """Check if enough time has passed since last alert for this rule."""
    now = datetime.now()
    last = _last_alert.get(rule_id)
    if last is None:
        return True
    elapsed = (now - last).total_seconds()
    return elapsed >= cooldown_seconds


def record_alert(rule_id: int):
    _last_alert[rule_id] = datetime.now()


async def send_email_alert(to_email: str, event_data: dict):
    """Send alert email."""
    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured, skipping email alert")
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = settings.ALERT_EMAIL_FROM or settings.SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = f"[OpenCam Alert] {event_data['event_type']} - {event_data.get('zone_name', 'Unknown zone')}"

        body = f"""
OpenCam Security Alert
━━━━━━━━━━━━━━━━━━━━

Event: {event_data['event_type']}
Camera: {event_data.get('camera_name', 'Unknown')}
Zone: {event_data.get('zone_name', 'N/A')}
Object: {event_data.get('object_type', 'Unknown')}
Confidence: {event_data.get('confidence', 0):.1%}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Review this event in the OpenCam dashboard.
"""
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email alert sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")


async def send_webhook_alert(webhook_url: str, event_data: dict):
    """Send alert via webhook POST."""
    try:
        async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT) as client:
            resp = await client.post(webhook_url, json={
                "source": "opencam",
                "timestamp": datetime.now().isoformat(),
                **event_data,
            })
            logger.info(f"Webhook alert sent: {resp.status_code}")
    except Exception as e:
        logger.error(f"Failed to send webhook alert: {e}")


async def trigger_alert(rule, event_data: dict):
    """Send alerts for a triggered rule."""
    if not can_alert(rule.id, rule.cooldown_seconds):
        return

    record_alert(rule.id)
    logger.info(f"Alert triggered: rule={rule.name}, event={event_data['event_type']}")

    if rule.alert_email:
        await send_email_alert(rule.alert_email, event_data)

    if rule.alert_webhook:
        await send_webhook_alert(rule.alert_webhook, event_data)
