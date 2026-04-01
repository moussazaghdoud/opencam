"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  getOpsData,
  createCountingLine,
  resetCountingLine,
} from "@/lib/ops-api";
import type { OpsData, DockStatus, CountingLine } from "@/lib/ops-api";
import {
  Activity,
  Truck,
  Users,
  ShieldCheck,
  Gauge,
  AlertTriangle,
  CheckCircle2,
  Info,
  Clock,
  Plus,
  RotateCcw,
  ArrowDownToLine,
  ArrowUpFromLine,
  Loader2,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return s > 0 ? `${m} min ${s}s` : `${m} min`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm > 0 ? `${h}h ${rm}min` : `${h}h`;
}

function severityColor(sev: string): string {
  switch (sev) {
    case "critical":
    case "red":
      return "text-red-400 bg-red-500/10 border-red-500/20";
    case "warning":
    case "orange":
      return "text-orange-400 bg-orange-500/10 border-orange-500/20";
    case "info":
    case "blue":
      return "text-blue-400 bg-blue-500/10 border-blue-500/20";
    case "success":
    case "green":
      return "text-green-400 bg-green-500/10 border-green-500/20";
    default:
      return "text-zinc-400 bg-zinc-500/10 border-zinc-500/20";
  }
}

function severityIcon(sev: string) {
  switch (sev) {
    case "critical":
    case "red":
      return <AlertTriangle className="w-4 h-4 shrink-0" />;
    case "warning":
    case "orange":
      return <AlertTriangle className="w-4 h-4 shrink-0" />;
    case "info":
    case "blue":
      return <Info className="w-4 h-4 shrink-0" />;
    case "success":
    case "green":
      return <CheckCircle2 className="w-4 h-4 shrink-0" />;
    default:
      return <Info className="w-4 h-4 shrink-0" />;
  }
}

function dockStatusBadge(status: DockStatus["status"]) {
  const map = {
    loading: "bg-green-500/15 text-green-400 border-green-500/30",
    idle: "bg-red-500/15 text-red-400 border-red-500/30",
    waiting: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full border font-medium capitalize ${map[status]}`}
    >
      {status}
    </span>
  );
}

function dockStatusDot(status: DockStatus["status"]) {
  const map = {
    loading: "bg-green-500",
    idle: "bg-red-500",
    waiting: "bg-yellow-500",
  };
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${map[status]} ${status === "loading" ? "animate-pulse" : ""}`}
    />
  );
}

// ---------------------------------------------------------------------------
// Placeholder / empty data
// ---------------------------------------------------------------------------

const EMPTY_OPS: OpsData = {
  throughput: { current_hour: 0, today_total: 0, target: 100, pace_percent: 0 },
  docks: [],
  workers: { total_detected: 0, per_zone: {} },
  safety: { score: 100, ppe_compliance_percent: 100, violations_today: 0 },
  hourly_throughput: [],
  alerts: [],
  counting_lines: [],
};

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = API_BASE.replace("http", "ws");

interface CameraItem { id: number; name: string; status: string; }

// Shared audio context (initialized on user click)
let _audioCtx: AudioContext | null = null;

function getAudioCtx(): AudioContext | null {
  if (!_audioCtx) {
    try {
      _audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    } catch { return null; }
  }
  if (_audioCtx.state === "suspended") _audioCtx.resume();
  return _audioCtx;
}

function playBeep(frequency: number, duration: number, type: OscillatorType = "sine") {
  const ctx = getAudioCtx();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.frequency.value = frequency;
  osc.type = type;
  gain.gain.value = 0.4;
  gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration);
  osc.start();
  osc.stop(ctx.currentTime + duration);
}

function playInSound() {
  playBeep(880, 0.12, "sine");
  setTimeout(() => playBeep(1100, 0.15, "sine"), 130);
}

function playOutSound() {
  playBeep(330, 0.25, "triangle");
}

function initSound() {
  const ctx = getAudioCtx();
  if (ctx) {
    // Play a silent sound to unlock audio
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    gain.gain.value = 0;
    osc.start();
    osc.stop(ctx.currentTime + 0.01);
  }
}

export default function OperationsPage() {
  const [data, setData] = useState<OpsData>(EMPTY_OPS);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [newLineName, setNewLineName] = useState("");
  const [newLineCameraId, setNewLineCameraId] = useState("");
  const [addingLine, setAddingLine] = useState(false);
  const prevAlertsLen = useRef(0);
  const [animateAlerts, setAnimateAlerts] = useState(false);
  const prevCounts = useRef({ in: 0, out: 0 });
  const [soundEnabled, setSoundEnabled] = useState(true);
  const soundEnabledRef = useRef(true);
  const [ppeViolation, setPpeViolation] = useState(false);
  const audioCtxRef = useRef<AudioContext | null>(null);

  // Video feed state
  const [cameras, setCameras] = useState<CameraItem[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<number>(0);
  const [wsConnected, setWsConnected] = useState(false);
  const [liveCounts, setLiveCounts] = useState({ in: 0, out: 0, net: 0, tracks: 0 });
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Fetch cameras
  useEffect(() => {
    fetch(`${API_BASE}/api/cameras/`)
      .then(r => r.json())
      .then((cams: CameraItem[]) => {
        setCameras(cams.filter(c => c.status === "online"));
        const online = cams.find(c => c.status === "online");
        if (online && selectedCameraId === 0) setSelectedCameraId(online.id);
      })
      .catch(() => {});
  }, []);

  // WebSocket for live video
  useEffect(() => {
    if (!selectedCameraId) return;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      ws = new WebSocket(`${WS_BASE}/ws/camera/${selectedCameraId}`);
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => { setWsConnected(false); reconnectTimer = setTimeout(connect, 3000); };
      ws.onerror = () => ws?.close();
      let lastPpeViolation = false;
      ws.onmessage = (msg) => {
        try {
          const d = JSON.parse(msg.data);
          const canvas = canvasRef.current;
          if (canvas && d.frame) {
            const img = new Image();
            img.onload = () => {
              canvas.width = img.width;
              canvas.height = img.height;
              const ctx = canvas.getContext("2d");
              if (ctx) ctx.drawImage(img, 0, 0);
            };
            img.src = `data:image/jpeg;base64,${d.frame}`;
          }
          // PPE violation alert beep
          if (d.ppe_violation && !lastPpeViolation && soundEnabledRef.current) {
            // Alarm sound — urgent triple beep
            playBeep(1000, 0.15, "square");
            setTimeout(() => playBeep(1000, 0.15, "square"), 200);
            setTimeout(() => playBeep(1000, 0.15, "square"), 400);
          }
          lastPpeViolation = d.ppe_violation || false;
          setPpeViolation(d.ppe_violation || false);
        } catch {}
      };
    }

    connect();

    // Poll counting line counts
    const countInterval = setInterval(() => {
      fetch(`${API_BASE}/api/ops/counting-lines`)
        .then(r => r.json())
        .then((lines: any[]) => {
          const totals = lines.reduce((acc, l) => {
            const live = l.live || {};
            return { in: acc.in + (live.in || 0), out: acc.out + (live.out || 0), net: acc.net + (live.net || 0), tracks: l.active_tracks || acc.tracks };
          }, { in: 0, out: 0, net: 0, tracks: 0 });
          // Play sounds on count changes (only if enabled)
          if (soundEnabledRef.current) {
            if (totals.in > prevCounts.current.in) playInSound();
            if (totals.out > prevCounts.current.out) playOutSound();
          }
          prevCounts.current = { in: totals.in, out: totals.out };
          setLiveCounts(totals);
        })
        .catch(() => {});
    }, 1000);

    return () => { clearTimeout(reconnectTimer); ws?.close(); clearInterval(countInterval); };
  }, [selectedCameraId]);

  const fetchData = useCallback(async () => {
    try {
      const ops = await getOpsData();
      setData((prev) => {
        if (ops.alerts.length > prev.alerts.length) {
          setAnimateAlerts(true);
          setTimeout(() => setAnimateAlerts(false), 600);
        }
        return ops;
      });
      setError("");
    } catch {
      setError("Cannot connect to operations API. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    // Auto-init sound on first user interaction
    const unlockAudio = () => { initSound(); document.removeEventListener("click", unlockAudio); };
    document.addEventListener("click", unlockAudio);
    return () => { clearInterval(interval); document.removeEventListener("click", unlockAudio); };
  }, [fetchData]);

  const handleCreateLine = async () => {
    if (!newLineName.trim() || !newLineCameraId.trim()) return;
    setAddingLine(true);
    try {
      await createCountingLine({
        camera_id: Number(newLineCameraId),
        name: newLineName.trim(),
      });
      setNewLineName("");
      setNewLineCameraId("");
      fetchData();
    } catch {
      // silently ignore
    } finally {
      setAddingLine(false);
    }
  };

  const handleResetLine = async (id: number) => {
    try {
      await resetCountingLine(id);
      fetchData();
    } catch {
      // silently ignore
    }
  };

  // Derived values
  const {
    throughput,
    docks,
    workers,
    safety,
    hourly_throughput,
    alerts,
    counting_lines = [],
  } = data;

  const activeDocks = docks.filter((d) => d.status === "loading").length;
  const totalDocks = docks.length;

  const safetyColor =
    safety.score >= 90
      ? "text-green-400"
      : safety.score >= 70
        ? "text-yellow-400"
        : "text-red-400";
  const safetyBarColor =
    safety.score >= 90
      ? "bg-green-500"
      : safety.score >= 70
        ? "bg-yellow-500"
        : "bg-red-500";

  const maxThroughput = Math.max(
    ...hourly_throughput.map((h) => h.count),
    1
  );
  const targetPacePerHour =
    throughput.target > 0 && hourly_throughput.length > 0
      ? throughput.target / 24
      : 0;

  return (
    <div className="min-h-full">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Activity className="w-6 h-6 text-blue-400" />
            <h1 className="text-2xl font-bold">Operations Dashboard</h1>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                if (!soundEnabled) initSound();
                setSoundEnabled(!soundEnabled);
                soundEnabledRef.current = !soundEnabled;
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                soundEnabled
                  ? "bg-green-600/20 text-green-400 border border-green-500/30"
                  : "bg-zinc-800 text-zinc-400 border border-zinc-700"
              }`}
            >
              {soundEnabled ? "Sound ON" : "Sound OFF"}
            </button>
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span
                className={`inline-block w-2 h-2 rounded-full ${error ? "bg-red-500" : "bg-green-500 animate-pulse"}`}
              />
              {error ? "Disconnected" : "Live"}
            </div>
          </div>
        </div>

        {/* PPE Violation Banner */}
        {ppeViolation && (
          <div className="bg-red-600/20 border-2 border-red-500 text-red-300 px-5 py-4 rounded-xl mb-6 flex items-center gap-4 animate-pulse">
            <div className="w-12 h-12 bg-red-600 rounded-full flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-7 h-7 text-white" />
            </div>
            <div>
              <div className="text-lg font-bold text-red-400">PPE VIOLATION DETECTED</div>
              <div className="text-sm text-red-300/80">Person detected without safety jacket — immediate action required</div>
            </div>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg mb-6 text-sm">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
          </div>
        )}

        {!loading && (
          <>
            {/* ============================================================ */}
            {/* TOP STATS ROW                                                */}
            {/* ============================================================ */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              {/* Throughput Today */}
              <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-zinc-500 uppercase tracking-wider font-medium">
                    Throughput Today
                  </span>
                  <Gauge className="w-4 h-4 text-blue-400" />
                </div>
                <div className="text-3xl font-bold mb-1">
                  {throughput.today_total}
                  <span className="text-sm font-normal text-zinc-500 ml-1">
                    / {throughput.target}
                  </span>
                </div>
                <div className="w-full bg-[#262626] rounded-full h-2 mt-3">
                  <div
                    className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(throughput.pace_percent, 100)}%`,
                    }}
                  />
                </div>
                <div className="text-xs text-zinc-500 mt-1">
                  {throughput.pace_percent}% of target pace
                </div>
              </div>

              {/* Active Docks */}
              <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-zinc-500 uppercase tracking-wider font-medium">
                    Active Docks
                  </span>
                  <Truck className="w-4 h-4 text-green-400" />
                </div>
                <div className="text-3xl font-bold mb-2">
                  {activeDocks}
                  <span className="text-sm font-normal text-zinc-500 ml-1">
                    / {totalDocks}
                  </span>
                </div>
                {totalDocks > 0 ? (
                  <div className="flex gap-1.5 flex-wrap">
                    {docks.map((d) => (
                      <div
                        key={d.zone_id}
                        className="flex items-center gap-1"
                        title={`${d.name}: ${d.status}`}
                      >
                        {dockStatusDot(d.status)}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-zinc-600">No docks configured</div>
                )}
              </div>

              {/* Workers Detected */}
              <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-zinc-500 uppercase tracking-wider font-medium">
                    Workers Detected
                  </span>
                  <Users className="w-4 h-4 text-purple-400" />
                </div>
                <div className="text-3xl font-bold mb-2">{workers.total_detected}</div>
                {Object.keys(workers.per_zone).length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(workers.per_zone).map(([zone, count]) => (
                      <span
                        key={zone}
                        className="text-xs bg-[#1e1e1e] border border-[#333] px-2 py-0.5 rounded"
                      >
                        {zone}: {count}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-zinc-600">Across all zones</div>
                )}
              </div>

              {/* Safety Score */}
              <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-zinc-500 uppercase tracking-wider font-medium">
                    Safety Score
                  </span>
                  <ShieldCheck className={`w-4 h-4 ${safetyColor}`} />
                </div>
                <div className={`text-3xl font-bold mb-1 ${safetyColor}`}>
                  {safety.score}%
                </div>
                <div className="w-full bg-[#262626] rounded-full h-2 mt-3">
                  <div
                    className={`${safetyBarColor} h-2 rounded-full transition-all duration-500`}
                    style={{ width: `${safety.score}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-zinc-500 mt-1">
                  <span>PPE: {safety.ppe_compliance_percent}%</span>
                  <span>{safety.violations_today} violations</span>
                </div>
              </div>
            </div>

            {/* ============================================================ */}
            {/* MIDDLE SECTION — Live Feed + Dock Status + Throughput       */}
            {/* ============================================================ */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
              {/* Live Camera Feed */}
              <div className="bg-[#141414] border border-[#262626] rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 border-b border-[#262626]">
                  <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
                    Live Feed
                  </h2>
                  <div className="flex items-center gap-2">
                    <select
                      value={selectedCameraId}
                      onChange={(e) => setSelectedCameraId(Number(e.target.value))}
                      className="px-2 py-1 bg-[#0a0a0a] border border-[#333] rounded text-xs focus:outline-none focus:border-blue-500"
                    >
                      {cameras.map((cam) => (
                        <option key={cam.id} value={cam.id}>{cam.name}</option>
                      ))}
                    </select>
                    <button
                      onClick={async () => {
                        try {
                          await fetch(`${API_BASE}/api/ops/counting-lines/1/reset`, { method: "POST" });
                          setLiveCounts({ in: 0, out: 0, net: 0, tracks: 0 });
                          prevCounts.current = { in: 0, out: 0 };
                        } catch {}
                      }}
                      className="px-2 py-1 bg-yellow-600 hover:bg-yellow-500 rounded text-xs font-bold transition-colors"
                    >
                      RESET
                    </button>
                  </div>
                </div>
                <div className="relative aspect-video bg-black">
                  <canvas ref={canvasRef} className="w-full h-full object-contain" />
                  {!wsConnected && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/80">
                      <span className="text-sm text-zinc-500">Connecting...</span>
                    </div>
                  )}
                  <div className="absolute top-2 right-2 flex gap-1">
                    <div className="bg-green-600/80 backdrop-blur px-2 py-1 rounded text-xs font-bold">
                      IN: {liveCounts.in}
                    </div>
                    <div className="bg-red-600/80 backdrop-blur px-2 py-1 rounded text-xs font-bold">
                      OUT: {liveCounts.out}
                    </div>
                    <div className="bg-blue-600/80 backdrop-blur px-2 py-1 rounded text-xs font-bold">
                      NET: {liveCounts.net}
                    </div>
                  </div>
                  <div className="absolute bottom-2 left-2 bg-black/60 backdrop-blur px-2 py-1 rounded text-[10px] text-zinc-300">
                    {liveCounts.tracks} tracks
                  </div>
                </div>
              </div>

              {/* Dock Status Panel */}
              <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">
                  Dock Status
                </h2>
                {docks.length === 0 ? (
                  <div className="text-sm text-zinc-600 py-8 text-center">
                    No docks configured yet. Add dock zones to your cameras.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {docks.map((dock) => {
                      const loadPct =
                        dock.avg_load_time > 0
                          ? Math.min(
                              (dock.current_load_time_seconds /
                                dock.avg_load_time) *
                                100,
                              100
                            )
                          : 0;
                      return (
                        <div
                          key={dock.zone_id}
                          className={`bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg p-3 transition-all ${
                            dock.status === "loading"
                              ? "ring-1 ring-green-500/20"
                              : ""
                          }`}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-sm">
                                {dock.name}
                              </span>
                              {dockStatusBadge(dock.status)}
                            </div>
                            <div className="flex items-center gap-3 text-xs text-zinc-500">
                              {dock.truck_present && (
                                <span className="flex items-center gap-1 text-blue-400">
                                  <Truck className="w-3 h-3" /> Truck
                                </span>
                              )}
                              <span className="flex items-center gap-1">
                                <Users className="w-3 h-3" />{" "}
                                {dock.worker_count}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            <div className="flex items-center gap-1 text-xs text-zinc-400 min-w-[80px]">
                              <Clock className="w-3 h-3" />
                              {formatDuration(
                                Math.floor(dock.current_load_time_seconds)
                              )}
                            </div>
                            <div className="flex-1 bg-[#262626] rounded-full h-1.5">
                              <div
                                className={`h-1.5 rounded-full transition-all duration-500 ${
                                  loadPct > 90
                                    ? "bg-red-500"
                                    : loadPct > 70
                                      ? "bg-yellow-500"
                                      : "bg-green-500"
                                }`}
                                style={{ width: `${loadPct}%` }}
                              />
                            </div>
                            <span className="text-xs text-zinc-600 min-w-[60px] text-right">
                              avg {formatDuration(Math.floor(dock.avg_load_time))}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Throughput Chart */}
              <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">
                  Hourly Throughput
                </h2>
                {hourly_throughput.length === 0 ? (
                  <div className="text-sm text-zinc-600 py-8 text-center">
                    No throughput data available yet.
                  </div>
                ) : (
                  <div className="flex items-end gap-1.5 h-48">
                    {hourly_throughput.map((h, i) => {
                      const pct = (h.count / maxThroughput) * 100;
                      const aboveTarget = h.count >= targetPacePerHour;
                      return (
                        <div
                          key={i}
                          className="flex-1 flex flex-col items-center justify-end h-full"
                        >
                          <span className="text-[10px] text-zinc-400 mb-1">
                            {h.count}
                          </span>
                          <div
                            className={`w-full rounded-t transition-all duration-500 ${
                              aboveTarget ? "bg-green-500/80" : "bg-orange-500/80"
                            }`}
                            style={{
                              height: `${Math.max(pct, 2)}%`,
                              minHeight: "4px",
                            }}
                          />
                          <span className="text-[9px] text-zinc-600 mt-1 truncate w-full text-center">
                            {h.hour}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {targetPacePerHour > 0 && hourly_throughput.length > 0 && (
                  <div className="flex items-center gap-4 mt-3 text-xs text-zinc-500">
                    <span className="flex items-center gap-1">
                      <span className="w-2.5 h-2.5 rounded-sm bg-green-500/80 inline-block" />
                      Above pace
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-2.5 h-2.5 rounded-sm bg-orange-500/80 inline-block" />
                      Below pace
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* ============================================================ */}
            {/* BOTTOM SECTION — Alerts + Counting Lines                     */}
            {/* ============================================================ */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Live Alerts Feed */}
              <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">
                  Live Alerts
                </h2>
                {alerts.length === 0 ? (
                  <div className="text-sm text-zinc-600 py-8 text-center">
                    No active alerts. All systems nominal.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                    {alerts.slice(0, 10).map((alert, i) => {
                      const severity = alert.event_type === "face_unknown" ? "critical" : alert.confidence > 0.9 ? "warning" : "info";
                      const message = `${alert.event_type} — ${alert.object_type} in ${alert.zone_name || "unknown zone"} (${(alert.confidence * 100).toFixed(0)}%)`;
                      const time = alert.created_at ? new Date(alert.created_at).toLocaleTimeString() : "";
                      return (
                        <div
                          key={`${alert.id}-${i}`}
                          className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border transition-all duration-300 ${severityColor(severity)} ${
                            i === 0 && animateAlerts ? "animate-pulse" : ""
                          }`}
                        >
                          {severityIcon(severity)}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm leading-snug">{message}</p>
                            <p className="text-[10px] opacity-60 mt-0.5">{time}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Counting Lines */}
              <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">
                  Counting Lines
                </h2>

                {counting_lines.length === 0 ? (
                  <div className="text-sm text-zinc-600 py-4 text-center">
                    No counting lines configured.
                  </div>
                ) : (
                  <div className="space-y-2 mb-4">
                    {counting_lines.map((line) => (
                      <div
                        key={line.id}
                        className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg p-3 flex items-center justify-between"
                      >
                        <div>
                          <div className="text-sm font-medium">{line.name}</div>
                          <div className="flex items-center gap-4 mt-1 text-xs">
                            <span className="flex items-center gap-1 text-green-400">
                              <ArrowDownToLine className="w-3 h-3" /> IN:{" "}
                              {line.in_count}
                            </span>
                            <span className="flex items-center gap-1 text-red-400">
                              <ArrowUpFromLine className="w-3 h-3" /> OUT:{" "}
                              {line.out_count}
                            </span>
                            <span className="text-zinc-400 font-medium">
                              TOTAL: {line.total}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={() => handleResetLine(line.id)}
                          className="p-1.5 rounded-lg hover:bg-[#262626] text-zinc-500 hover:text-zinc-300 transition-colors"
                          title="Reset counts"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Add counting line form */}
                <div className="border-t border-[#262626] pt-4 mt-4">
                  <div className="text-xs text-zinc-500 mb-2 font-medium">
                    Add Counting Line
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newLineName}
                      onChange={(e) => setNewLineName(e.target.value)}
                      placeholder="Line name"
                      className="flex-1 bg-[#1a1a1a] border border-[#333] rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-blue-500/50"
                    />
                    <input
                      type="number"
                      value={newLineCameraId}
                      onChange={(e) => setNewLineCameraId(e.target.value)}
                      placeholder="Cam ID"
                      className="w-20 bg-[#1a1a1a] border border-[#333] rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-blue-500/50"
                    />
                    <button
                      onClick={handleCreateLine}
                      disabled={
                        addingLine ||
                        !newLineName.trim() ||
                        !newLineCameraId.trim()
                      }
                      className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1"
                    >
                      {addingLine ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Plus className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
    </div>
  );
}
