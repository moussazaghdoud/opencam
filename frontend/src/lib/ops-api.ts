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

// Types

export interface DockStatus {
  zone_id: number;
  name: string;
  status: "loading" | "idle" | "waiting";
  current_load_time_seconds: number;
  worker_count: number;
  truck_present: boolean;
  avg_load_time: number;
}

export interface CountingLine {
  id: number;
  camera_id: number;
  name: string;
  in_count: number;
  out_count: number;
  total: number;
}

export interface DockSession {
  id: number;
  zone_id: number;
  start_time: string;
  end_time: string | null;
  duration_seconds: number;
  truck_id: string | null;
}

export interface OpsData {
  throughput: {
    current_hour: number;
    today_total: number;
    target: number;
    pace_percent: number;
  };
  docks: DockStatus[];
  workers: {
    total_detected: number;
    per_zone: Record<string, number>;
  };
  safety: {
    score: number;
    ppe_compliance_percent: number;
    violations_today: number;
  };
  hourly_throughput: { hour: number; count: number }[];
  alerts: { id: number; event_type: string; object_type: string; zone_name: string; confidence: number; acknowledged: boolean; created_at: string }[];
  counting_lines?: CountingLine[];
}

// API calls

export const getOpsData = () => fetchAPI<OpsData>("/api/ops/dashboard");

export const getCountingLines = () =>
  fetchAPI<CountingLine[]>("/api/ops/counting-lines");

export const createCountingLine = (data: {
  camera_id: number;
  name: string;
}) => fetchAPI<CountingLine>("/api/ops/counting-lines", {
  method: "POST",
  body: JSON.stringify(data),
});

export const resetCountingLine = (id: number) =>
  fetchAPI<void>(`/api/ops/counting-lines/${id}/reset`, {
    method: "POST",
  });

export const getDockSessions = (zoneId: number) =>
  fetchAPI<DockSession[]>(`/api/ops/docks/${zoneId}/sessions`);
