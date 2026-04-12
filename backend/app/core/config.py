from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "OpenCam"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite:///./opencam.db"

    # Auth
    SECRET_KEY: str = "change-me-in-production-opencam-secret-2024"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # YOLO
    YOLO_MODEL: str = "yolov8n.pt"
    DETECTION_CONFIDENCE: float = 0.5

    # Storage
    CLIPS_DIR: str = "./clips"
    SNAPSHOTS_DIR: str = "./snapshots"

    # Alerts
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    ALERT_EMAIL_FROM: Optional[str] = None
    WEBHOOK_TIMEOUT: int = 10

    # AI Search
    ANTHROPIC_API_KEY: Optional[str] = None

    # Processing
    FRAME_SKIP: int = 3  # Process every Nth frame
    MAX_CAMERAS: int = 16

    # Module toggles — disable heavy modules to save CPU
    ENABLE_FACE_RECOGNITION: bool = True
    ENABLE_PPE_DETECTION: bool = True
    ENABLE_HEATMAP: bool = True

    # Face recognition runs every N × FRAME_SKIP frames (higher = less CPU)
    FACE_RECOGNITION_INTERVAL: int = 10

    # Background worker queue size per camera (1 = drop old frames, keep newest)
    WORKER_QUEUE_SIZE: int = 1

    # AI Narrator — event narration + suspicion scoring (default OFF)
    ENABLE_AI_NARRATOR: bool = False

    # Clip recording — save short video clips around events for activity analysis
    ENABLE_CLIP_RECORDING: bool = False

    class Config:
        env_file = ".env"
        env_prefix = "OPENCAM_"


settings = Settings()
