# OpenCam — AI Video Surveillance System

## What is OpenCam
Privacy-first AI-powered video surveillance system. Cameras stream locally, AI processes on-premise, only events/alerts go to cloud. Same hybrid architecture as SecureLLM (Moussa's other project).

## Architecture

```
[IP Cameras (RTSP)] -> [On-Prem Engine (Python/FastAPI)] -> [NATS tunnel] -> [Cloud Dashboard (Next.js)]
```

Video never leaves the building. Only metadata, events, and thumbnails go to cloud.

## Code Repository
- GitHub: https://github.com/moussazaghdoud/opencam
- Branch: master

## Backend — `backend/` (Python/FastAPI)

### Framework & Stack
- FastAPI + Uvicorn (port 8000, hot reload)
- SQLAlchemy + SQLite (dev), PostgreSQL (prod)
- Python 3.12 required (3.14 breaks PyTorch)
- Virtual env at `backend/venv`

### AI Models
- **YOLO v8n** (ultralytics) — person, vehicle, bicycle detection, ~40ms/frame on Ryzen 5
- **ArcFace** (w600k_r50.onnx) via ONNX Runtime — 512-dim face embeddings, 99.8% NIST accuracy
- **Face Detection:** Haar cascade (primary) + RetinaFace ONNX (fallback)
- **Face Enhancement:** Auto upscale + CLAHE + sharpen for faces < 100px (distant faces)
- Models stored at: `~/.insightface/models/buffalo_l/` (det_10g.onnx, w600k_r50.onnx, genderage.onnx)

### Key Backend Files
- `app/main.py` — FastAPI app, lifespan, all routes registered
- `app/core/config.py` — Settings via env vars (prefix: `OPENCAM_`), includes ANTHROPIC_API_KEY
- `app/core/database.py` — SQLAlchemy engine, session, Base
- `app/models/camera.py` — Camera model (name, rtsp_url, location, status, resolution)
- `app/models/zone.py` — Zone model (polygon points, type, color)
- `app/models/rule.py` — Rule model (trigger, schedule, alert_email, webhook, cooldown)
- `app/models/event.py` — Event model (type, confidence, snapshot, bbox, acknowledged)
- `app/models/face.py` — KnownFace model (name, role, photo_path)
- `app/models/ops.py` — CountingLineModel, CountingRecord, DockSession
- `app/api/cameras.py` — CRUD + start/stop/snapshot endpoints
- `app/api/zones.py` — Zone CRUD
- `app/api/rules.py` — Rule CRUD
- `app/api/events.py` — Event list/acknowledge/stats with filtering
- `app/api/faces.py` — Face register (upload or camera capture), recognize, delete
- `app/api/operations.py` — Operations dashboard, counting lines CRUD, dock status, PPE check, heatmap, AI search
- `app/api/ws.py` — WebSocket live feed with overlays (detections, faces, counting lines, PPE, heatmap, privacy blur). Also has privacy and heatmap toggle endpoints.
- `app/services/detector.py` — YOLO singleton, detect persons/vehicles
- `app/services/face_recognizer.py` — ArcFace ONNX recognizer with face enhancement for distance
- `app/services/stream_processor.py` — CameraStream + StreamManager, async processing loop per camera, integrates YOLO + face reco + counter + activity timer + heatmap
- `app/services/zone_checker.py` — Point-in-polygon (ray casting), schedule checking
- `app/services/alert_service.py` — Email (SMTP) + webhook alerts with cooldown
- `app/services/counter.py` — ObjectTracker (centroid tracking) + CountingLine (side-change detection for IN/OUT)
- `app/services/activity_timer.py` — ZoneActivityTimer (tracks active/idle per zone, sessions)
- `app/services/ops_stats.py` — OpsStats aggregator (throughput, docks, workers, safety)
- `app/services/ppe_detector.py` — White jacket detection via HSV + brightness analysis with hysteresis (5 frames to change state)
- `app/services/heatmap.py` — HeatmapAccumulator (64x48 grid, decay rate 0.95, COLORMAP_JET, absolute scale)
- `app/services/ai_search.py` — AI search via Claude API (keyword fallback without API key)

### Database Schema
- `cameras` — id, name, rtsp_url, location, enabled, width, height, fps, status
- `zones` — id, camera_id, name, zone_type, points (JSON polygon), color, enabled
- `rules` — id, zone_id, name, object_type, trigger, threshold, schedule_*, alert_email, alert_webhook, cooldown
- `events` — id, camera_id, rule_id, event_type, object_type, confidence, snapshot_path, bbox, zone_name, acknowledged, false_alarm
- `known_faces` — id, name, role, photo_path
- `counting_lines` — id, camera_id, name, point_a, point_b, direction, enabled
- `counting_records` — id, line_id, direction, object_type, timestamp
- `dock_sessions` — id, zone_id, zone_name, camera_id, started_at, ended_at, duration_seconds, peak_workers, status

### Event Types
- `enter` — object entered a zone
- `count_above` — object count exceeds threshold
- `face_known` — recognized face detected
- `face_unknown` — unrecognized face detected

## Frontend — `frontend/` (Next.js 16 + TypeScript + Tailwind)

### Enterprise UI (Verkada-inspired redesign)
Dark theme: bg-[#09090b] (main), bg-[#111113] (sidebar/topbar), bg-[#18181b] (cards), border-[#27272a]

### Layout — `src/components/AppShell.tsx`
- Fixed top nav bar: OpenCam logo + DEV badge, AI search bar (Claude-powered), notification bell, settings gear, MZ avatar
- Left sidebar (w-64, collapsible): 3 sections — MONITORING (Dashboard, Live View, Cameras), INTELLIGENCE (Face Recognition, Operations, Analytics), MANAGEMENT (Events, Alerts, Settings)
- System status bar at bottom ("cameras online", "System healthy")

### Pages
- `src/app/page.tsx` — **Dashboard** — 5 stat cards (cameras, alerts, people, face matches, system health), camera grid with 2x2/3x3/4x4 toggle, recent activity timeline
- `src/app/live/page.tsx` — **Live View** — full-screen camera grid, Privacy ON/OFF toggle (face blur), Heatmap ON/OFF toggle, expand single camera
- `src/app/cameras/page.tsx` — **Cameras** — camera cards with thumbnails, add camera slide-in form, start/stop/delete
- `src/app/faces/page.tsx` — **Face Recognition** — face grid with photos + role badges, register (camera capture or upload), live recognition scan
- `src/app/events/page.tsx` — **Events** — split view (list + detail panel), filters (type, camera, acknowledged), snapshot viewer, acknowledge/false alarm
- `src/app/operations/page.tsx` — **Operations** — live video feed with counting line + IN/OUT/NET counters + reset button, throughput chart, dock status, live alerts with sound (IN=double beep, OUT=low tone, PPE=triple alarm), PPE violation banner
- `src/app/analytics/page.tsx` — **Analytics** — heatmap overlay on camera snapshot, stats cards (detections, peak zone, coverage %), reset button
- `src/app/settings/page.tsx` — **Settings** — backend config reference, system info

### Key Frontend Files
- `src/components/AppShell.tsx` — Layout wrapper with top nav + sidebar + AI search results dropdown
- `src/components/CameraFeed.tsx` — WebSocket live video canvas
- `src/lib/api.ts` — API client (cameras, zones, rules, events, faces, dashboard, health)
- `src/lib/ops-api.ts` — Operations API client (ops data, counting lines, dock sessions)

## Features Built & Working

### Core Surveillance
- Real-time person/vehicle detection (YOLO v8)
- Multi-camera support (tested with webcam + Reolink TrackMix PoE)
- WebSocket live video feed with detection overlays
- Zone-based rules with schedule and alerts
- Event logging with snapshots

### Face Recognition
- ArcFace (512-dim embeddings) via ONNX Runtime
- Register faces via camera capture or photo upload
- Live recognition scan from any camera
- Auto face enhancement for distant/small faces
- Tested: 100% match at 50cm, 70% at 1m, detection at 4m

### PPE Detection
- White/bright jacket detection via HSV + brightness analysis
- Hysteresis (5 consecutive frames before state change)
- Red "NO JACKET!" overlay + PPE violation banner + triple alarm beep
- Green "JACKET OK" when wearing

### Privacy Mode (GDPR)
- Toggle in Live View toolbar
- Blurs upper 40% of person bounding boxes
- Shows "PRIVACY" label instead of face recognition data
- One-click toggle per camera

### Heatmap
- 64x48 grid accumulator with decay (0.95/frame)
- COLORMAP_JET visualization (blue=cold, red=hot)
- Toggle ON/OFF in Live View
- Analytics page with stats + overlay on snapshot
- Absolute scale (fades when nobody present)

### People Counting
- Directional counting lines (IN/OUT)
- Side-change detection algorithm
- Live IN/OUT/NET counters on video feed
- Sound alerts (different beeps for IN vs OUT)
- Reset button

### Operations Dashboard
- Live camera feed with counting line overlay
- Throughput chart (hourly)
- Dock status panel
- Worker count per zone
- Safety score
- Live alerts feed

### AI Search
- Search bar in top nav
- Claude API powered (with keyword fallback)
- Returns summary, matching events, insights
- Works without API key (keyword search)

## Camera Support

### Reolink TrackMix PoE (PRODUCTION CAMERA)
- Connected via PoE switch (TP-Link TL-SG108PE)
- IP: 192.168.0.3, password: OpenCam2026
- Main stream: `rtsp://admin:OpenCam2026@192.168.0.3:554/h264Preview_01_main` (3840x2160 4K — too heavy for real-time)
- **Sub stream: `rtsp://admin:OpenCam2026@192.168.0.3:554/h264Preview_01_sub` (896x512 — USE THIS for real-time)**
- Dual lens, 6X zoom, auto-tracking, color night vision, PoE powered

### Webcam
- Use `0` as RTSP URL (uses DirectShow on Windows via cv2.CAP_DSHOW)
- 640x480 resolution

### Video files
- Use local file path as RTSP URL, auto-loops

### EZVIZ H6c (NOT SUITED)
- Cloud-only camera, no RTSP, no local API
- Serial: BH3113456
- pyezvizapi can connect but no local streaming
- Conclusion: don't use for OpenCam — need RTSP cameras

## Hardware Setup

### Demo Kit (deployed)
- **Beelink SER5** Mini PC — AMD Ryzen 5 5500U (6C/12T, 4GHz), 16GB DDR4, 500GB NVMe
  - Windows 11, Python 3.12, Node.js 24.1
  - Username: moussa
  - Code at: C:\Users\moussa\opencam (cloned from GitHub)
  - WiFi IP: 192.168.1.159 (Freebox-MZ)
  - Ethernet IP: 192.168.0.100 (static, for camera network)
- **Reolink TrackMix PoE** camera — 4K, dual lens, auto-tracking
  - IP: 192.168.0.3
  - Connected via PoE switch port 1
- **TP-Link TL-SG108PE** — 8-port switch (4 PoE + 4 normal)
  - Camera on port 1 (PoE)
  - Beelink on port 5 (non-PoE)
  - NOT connected to router (isolated network for camera)

### Network topology
```
[Freebox Router 192.168.1.254]
        |
        | WiFi (192.168.1.x)
        |
[Beelink SER5 - WiFi: 192.168.1.159]
        |
        | Ethernet (192.168.0.x)
        |
[TP-Link PoE Switch]
        |
        | PoE (192.168.0.x)
        |
[Reolink TrackMix - 192.168.0.3]
```

## Running on Beelink

### Backend
```powershell
cd C:\Users\moussa\opencam\backend
.\venv\Scripts\Activate.ps1
python run.py
# -> http://localhost:8000
```

### Frontend
```powershell
cd C:\Users\moussa\opencam\frontend
npm run dev
# -> http://localhost:3000
```

## Running on Main PC (development)

### Backend
```bash
cd /c/Users/zaghdoud/opencam/backend
source venv/Scripts/activate
python run.py
# -> http://localhost:8000
```

### Frontend
```bash
cd /c/Users/zaghdoud/opencam/frontend
npm run dev
# -> http://localhost:3000
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
OPENCAM_SMTP_HOST=  (optional)
OPENCAM_SMTP_PORT=587
OPENCAM_SMTP_USER=
OPENCAM_SMTP_PASSWORD=
OPENCAM_ANTHROPIC_API_KEY=  (optional, for AI search)
```

## Windows Notes
- Python 3.12 required (3.14 breaks PyTorch/torch DLL loading)
- Need Microsoft Visual C++ Redistributable for PyTorch
- Webcam requires cv2.CAP_DSHOW (MSMF has issues)
- PowerShell: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` for venv activation
- Zscaler blocks SSL — use verify=False or Zscaler cert
- Use PYTHONUTF8=1 for Unicode console output
- requirements.txt uses unpinned versions for Python 3.12 compatibility

## Competitive Positioning
- vs Verkada: same protocols (RTSP/ONVIF/H.265), same AI accuracy (ArcFace 99.8%), 1/1000th the cost, privacy-first
- vs basic CCTV: AI-powered, real-time alerts, face recognition, analytics
- Unique advantages: on-premise AI (GDPR), works offline, open camera support, PPE detection

## Feature Gap vs Verkada (not built yet)
1. AI-powered natural language search on footage (partially built — keyword search works)
2. Visual heatmaps (built)
3. Auth + roles / SSO (not built)
4. Multi-site management (not built)
5. License plate recognition (not built)
6. Person re-identification across cameras (not built)
7. Unified timeline (not built)
8. Mobile app (not built)
9. Motion search (not built)

## Pricing Model (planned)
- Starter: 99 EUR/month (8 cameras, 1 site)
- Business: 299 EUR/month (32 cameras, 5 sites)
- Enterprise: 999+ EUR/month (unlimited)
- Hardware appliance: 500 EUR one-time per site

## Scaling Path
- 1-4 cameras: Beelink SER5 (CPU, ~250 EUR)
- 8-16 cameras: Jetson Orin NX (~500 EUR)
- 16-50 cameras: Mini-tower + RTX 4060 (~1,200 EUR)
- 50-100 cameras: RTX 4090 server (~5,000 EUR)
- Stadium (100-300): A100 cluster (~50,000 EUR)

## Registered Faces
- Moussa Zaghdoud (admin) — faces/moussa.jpg

## Claude Code Account
- Email: codeur.rainbow@proton.me
- Plan: Claude Max
- Model: Opus 4.6 (1M context)
