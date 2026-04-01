const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

// Camera
export interface Camera {
  id: number;
  name: string;
  rtsp_url: string;
  location: string;
  enabled: boolean;
  width: number | null;
  height: number | null;
  fps: number | null;
  status: string;
  created_at: string;
}

export const getCameras = () => fetchAPI<Camera[]>("/api/cameras/");
export const createCamera = (data: { name: string; rtsp_url: string; location?: string }) =>
  fetchAPI<Camera>("/api/cameras/", { method: "POST", body: JSON.stringify(data) });
export const deleteCamera = (id: number) =>
  fetchAPI("/api/cameras/" + id, { method: "DELETE" });
export const startCamera = (id: number) =>
  fetchAPI("/api/cameras/" + id + "/start", { method: "POST" });
export const stopCamera = (id: number) =>
  fetchAPI("/api/cameras/" + id + "/stop", { method: "POST" });

// Zone
export interface Zone {
  id: number;
  camera_id: number;
  name: string;
  zone_type: string;
  points: number[][];
  color: string;
  enabled: boolean;
  created_at: string;
}

export const getZones = (cameraId?: number) =>
  fetchAPI<Zone[]>(`/api/zones/${cameraId ? `?camera_id=${cameraId}` : ""}`);
export const createZone = (data: { camera_id: number; name: string; zone_type: string; points: number[][] }) =>
  fetchAPI<Zone>("/api/zones/", { method: "POST", body: JSON.stringify(data) });
export const deleteZone = (id: number) =>
  fetchAPI("/api/zones/" + id, { method: "DELETE" });

// Rule
export interface Rule {
  id: number;
  zone_id: number;
  name: string;
  object_type: string;
  trigger: string;
  threshold: number;
  schedule_start: string | null;
  schedule_end: string | null;
  schedule_days: number[];
  alert_email: string | null;
  alert_webhook: string | null;
  enabled: boolean;
  cooldown_seconds: number;
  created_at: string;
}

export const getRules = (zoneId?: number) =>
  fetchAPI<Rule[]>(`/api/rules/${zoneId ? `?zone_id=${zoneId}` : ""}`);
export const createRule = (data: Partial<Rule> & { zone_id: number; name: string }) =>
  fetchAPI<Rule>("/api/rules/", { method: "POST", body: JSON.stringify(data) });
export const deleteRule = (id: number) =>
  fetchAPI("/api/rules/" + id, { method: "DELETE" });

// Event
export interface Event {
  id: number;
  camera_id: number;
  rule_id: number | null;
  event_type: string;
  object_type: string;
  confidence: number;
  snapshot_path: string | null;
  clip_path: string | null;
  bbox: number[] | null;
  zone_name: string | null;
  acknowledged: boolean;
  false_alarm: boolean;
  created_at: string;
}

export const getEvents = (params?: { camera_id?: number; limit?: number }) => {
  const qs = new URLSearchParams();
  if (params?.camera_id) qs.set("camera_id", String(params.camera_id));
  if (params?.limit) qs.set("limit", String(params.limit));
  return fetchAPI<Event[]>(`/api/events/?${qs}`);
};
export const acknowledgeEvent = (id: number, falseAlarm = false) =>
  fetchAPI<Event>(`/api/events/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ acknowledged: true, false_alarm: falseAlarm }),
  });

// Dashboard
export interface DashboardData {
  cameras: { total: number; online: number };
  events: { total: number; unacknowledged: number };
  recent_events: Event[];
}

export const getDashboard = () => fetchAPI<DashboardData>("/api/dashboard");
export const getHealth = () => fetchAPI<{ status: string; active_cameras: number }>("/api/health");

// WebSocket URL
export const getWsUrl = (cameraId: number) => {
  const wsBase = API_BASE.replace("http", "ws");
  return `${wsBase}/ws/camera/${cameraId}`;
};

// Snapshot URL
export const getSnapshotUrl = (cameraId: number) =>
  `${API_BASE}/api/cameras/${cameraId}/snapshot`;
export const getEventSnapshotUrl = (eventId: number) =>
  `${API_BASE}/api/events/${eventId}/snapshot`;
