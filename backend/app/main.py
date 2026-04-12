import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings
from app.core.database import init_db
from app.api import cameras, zones, rules, events, ws, faces, operations, ai_enrichment
import app.models.ops  # noqa: F401 — register ORM models
import app.models.ai_enrichment  # noqa: F401 — register AI enrichment model
from app.services.stream_processor import stream_manager
from app.services.face_recognizer import face_recognizer

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "opencam.log", encoding="utf-8"),
    ],
)
# Keep noisy libs at WARNING
for noisy in ("uvicorn.access", "watchfiles", "httpcore", "httpx", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    init_db()

    # Create storage dirs
    Path(settings.CLIPS_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.SNAPSHOTS_DIR).mkdir(parents=True, exist_ok=True)

    # Load known faces
    face_recognizer.load_known_faces()

    # Build activity baseline from historical events
    if settings.ENABLE_AI_NARRATOR:
        from app.services.activity_baseline import activity_baseline
        activity_baseline.rebuild()
        logger.info("Activity baseline built from historical events")

    # Start processing all enabled cameras
    await stream_manager.start_all()
    logger.info("All camera streams started")

    yield

    # Shutdown
    await stream_manager.stop_all()
    logger.info("All camera streams stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS - allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(cameras.router)
app.include_router(zones.router)
app.include_router(rules.router)
app.include_router(events.router)
app.include_router(faces.router)
app.include_router(operations.router)
app.include_router(ws.router)
app.include_router(ai_enrichment.router)

# Serve snapshots
snapshots_path = Path(settings.SNAPSHOTS_DIR)
snapshots_path.mkdir(parents=True, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=str(snapshots_path)), name="snapshots")


@app.get("/api/health")
def health():
    active_streams = len(stream_manager.streams)
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "active_cameras": active_streams,
    }


@app.get("/api/dashboard")
def dashboard_data():
    """Aggregated dashboard data."""
    from app.core.database import SessionLocal
    from app.models.camera import Camera
    from app.models.event import Event
    from sqlalchemy import func

    db = SessionLocal()
    try:
        cameras_total = db.query(func.count(Camera.id)).scalar()
        cameras_online = db.query(func.count(Camera.id)).filter(Camera.status == "online").scalar()
        events_total = db.query(func.count(Event.id)).scalar()
        events_unack = db.query(func.count(Event.id)).filter(Event.acknowledged == False).scalar()

        recent_events = (
            db.query(Event)
            .order_by(Event.created_at.desc())
            .limit(10)
            .all()
        )

        return {
            "cameras": {"total": cameras_total, "online": cameras_online},
            "events": {"total": events_total, "unacknowledged": events_unack},
            "recent_events": [
                {
                    "id": e.id,
                    "camera_id": e.camera_id,
                    "event_type": e.event_type,
                    "object_type": e.object_type,
                    "confidence": e.confidence,
                    "zone_name": e.zone_name,
                    "acknowledged": e.acknowledged,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in recent_events
            ],
        }
    finally:
        db.close()
