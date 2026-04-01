# OpenCam — AI Video Surveillance System

## What is OpenCam
Privacy-first AI-powered video surveillance system. Cameras stream locally, AI processes on-premise, only events/alerts go to cloud. Same hybrid architecture as SecureLLM.

## Architecture

```
[IP Cameras (RTSP)] → [On-Prem Engine (Python)] → [NATS tunnel] → [Cloud Dashboard (Next.js)]
```

### Backend — `backend/` (Python/FastAPI)
- **Framework:** FastAPI + Uvicorn (port 8000)
- **Database:** SQLite (dev), PostgreSQL (prod)
- **Detection:** YOLOv8n (ultralytics) — person, vehicle, bicycle detection
- **Face Recognition:** ArcFace (w600k_r50) via ONNX Runtime — 512-dim embeddings
- **Face Detection:** Haar cascade (primary) + RetinaFace ONNX (fallback)
- **Face Enhancement:** Auto upscale + CLAHE + sharpen for small/distant faces
- **Stream Processing:** OpenCV VideoCapture, async processing loop per camera
- **Alerts:** Email (SMTP) + Webhook

### Frontend — `frontend/` (Next.js + TypeScript + Tailwind)
- **Pages:** Dashboard `/`, Cameras `/cameras`, Faces `/faces`, Events `/events`, Settings `/settings`
- **Live Feed:** WebSocket connection for real-time video with detection overlays
- **Components:** Sidebar, StatCard, CameraFeed, EventRow

## Key Files

### Backend
- `app/main.py` — FastAPI app, lifespan, routes
- `app/core/config.py` — Settings via env vars (prefix: `OPENCAM_`)
- `app/core/database.py` — SQLAlchemy engine, session
- `app/models/` — Camera, Zone, Rule, Event, KnownFace
- `app/schemas/` — Pydantic request/response models
- `app/api/cameras.py` — CRUD + start/stop/snapshot endpoints
- `app/api/zones.py` — Zone CRUD
- `app/api/rules.py` — Rule CRUD
- `app/api/events.py` — Event list/acknowledge/stats
- `app/api/faces.py` — Face register/recognize/delete
- `app/api/ws.py` — WebSocket live feed with detection + face overlays
- `app/services/detector.py` — YOLO singleton, detect persons/vehicles
- `app/services/face_recognizer.py` — ArcFace ONNX + face enhancement
- `app/services/stream_processor.py` — Camera stream manager, processing loop
- `app/services/zone_checker.py` — Point-in-polygon, schedule checking
- `app/services/alert_service.py` — Email/webhook alerts with cooldown

### Frontend
- `src/app/page.tsx` — Dashboard with stats, live feeds, recent events
- `src/app/cameras/page.tsx` — Camera management (add/remove/start/stop)
- `src/app/faces/page.tsx` — Face registration + live recognition scan
- `src/app/events/page.tsx` — Event log with detail panel + snapshots
- `src/app/settings/page.tsx` — Config reference
- `src/components/Sidebar.tsx` — Navigation
- `src/components/CameraFeed.tsx` — WebSocket live video canvas
- `src/lib/api.ts` — API client functions

## Models & AI

### YOLO (Object Detection)
- Model: `yolov8n.pt` (nano, fast on CPU)
- Detects: person, car, truck, motorcycle, bicycle, bus
- Config: `OPENCAM_DETECTION_CONFIDENCE=0.5`, `OPENCAM_FRAME_SKIP=3`

### ArcFace (Face Recognition)
- Model: `w600k_r50.onnx` at `~/.insightface/models/buffalo_l/`
- Also available: `det_10g.onnx` (RetinaFace), `genderage.onnx`
- Embeddings: 512-dimensional, cosine similarity, threshold 0.4
- Face enhancement: auto-upscale faces < 100px with LANCZOS4 + CLAHE + sharpen

### Face Detection
- Primary: Haar cascade (`haarcascade_frontalface_default.xml`) — reliable, fast
- Fallback: RetinaFace ONNX (`det_10g.onnx`) — better at angles but needs tuning
- Params: scaleFactor=1.05, minNeighbors=3, minSize=(30,30)

## Camera Support

### Working
- **Webcam:** Use `0` as RTSP URL (uses DirectShow on Windows via `cv2.CAP_DSHOW`)
- **RTSP cameras:** Direct URL e.g. `rtsp://admin:pass@192.168.1.x:554/stream`
- **Video files:** Local path, auto-loops

### EZVIZ H6c (cloud-only, NO RTSP)
- Serial: BH3113456, local IP: 192.168.1.7
- No RTSP port, no local API — cloud-only via P2P
- pyezvizapi can connect (needs SSL verify=False for Zscaler)
- Not suited for local AI processing — recommend RTSP cameras instead
- Recommended alternatives: Reolink RLC-510A, Tapo C210, Hikvision DS-2CD series

## Database Schema
- `cameras` — id, name, rtsp_url, location, enabled, width, height, fps, status
- `zones` — id, camera_id, name, zone_type, points (JSON polygon), color, enabled
- `rules` — id, zone_id, name, object_type, trigger, threshold, schedule_*, alert_email, alert_webhook, cooldown
- `events` — id, camera_id, rule_id, event_type, object_type, confidence, snapshot_path, bbox, zone_name, acknowledged, false_alarm
- `known_faces` — id, name, role, photo_path

## Event Types
- `enter` — object entered a zone
- `count_above` — object count exceeds threshold
- `face_known` — recognized face detected
- `face_unknown` — unrecognized face detected

## Running

### Backend
```bash
cd opencam/backend
source venv/Scripts/activate
python run.py
# → http://localhost:8000 (API + Swagger at /docs)
```

### Frontend
```bash
cd opencam/frontend
npm run dev
# → http://localhost:3000
```

## Environment Variables
```
OPENCAM_DATABASE_URL=sqlite:///./opencam.db
OPENCAM_YOLO_MODEL=yolov8n.pt
OPENCAM_DETECTION_CONFIDENCE=0.5
OPENCAM_FRAME_SKIP=3
OPENCAM_MAX_CAMERAS=16
OPENCAM_CLIPS_DIR=./clips
OPENCAM_SNAPSHOTS_DIR=./snapshots
OPENCAM_SMTP_HOST=  (optional, for email alerts)
OPENCAM_SMTP_PORT=587
OPENCAM_SMTP_USER=
OPENCAM_SMTP_PASSWORD=
```

## Windows/Zscaler Notes
- Webcam requires `cv2.CAP_DSHOW` backend on Windows (MSMF has issues)
- Zscaler blocks SSL to external APIs — use `verify=False` or Zscaler root cert
- EZVIZ Studio login fails due to Zscaler cert interception
- Model downloads may fail — download manually if needed
- Use `PYTHONUTF8=1` for Unicode in console output

## Tested Recognition Performance (laptop webcam 640x480)
- ~50cm: 100% confidence match
- ~1m: 70% confidence match (side angle)
- ~4m: face detected but too small for reliable match (enhancement helps ~15%)
- With proper 2K IP camera: expect 5-10m recognition range

## Future / Enterprise Roadmap
- Multi-tenant cloud (Railway SaaS)
- NATS tunnel for on-prem ↔ cloud (same as SecureLLM)
- On-prem engine as Docker image / appliance
- PostgreSQL + TimescaleDB for events
- SSO/SAML auth, role-based access
- Zone drawing UI on camera feed
- Daily LLM summary reports
- Slack/Teams/PagerDuty integration
- GPU acceleration (onnxruntime-gpu)
- License plate recognition (LPR)
- Heatmaps and analytics dashboard

## Registered Faces
- Moussa Zaghdoud (admin) — `faces/moussa.jpg`
