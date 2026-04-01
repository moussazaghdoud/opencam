"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { getCameras, getWsUrl } from "@/lib/api";
import type { Camera } from "@/lib/api";
import {
  MonitorPlay,
  Grid2x2,
  Grid3x3,
  LayoutGrid,
  Maximize2,
  Minimize2,
  WifiOff,
  ArrowLeft,
  Square,
  EyeOff,
  Eye,
  Flame,
} from "lucide-react";

type GridSize = "1x1" | "2x2" | "3x3" | "4x4";

const GRID_COLS: Record<GridSize, string> = {
  "1x1": "grid-cols-1",
  "2x2": "grid-cols-1 md:grid-cols-2",
  "3x3": "grid-cols-1 md:grid-cols-2 lg:grid-cols-3",
  "4x4": "grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
};

function LiveCameraCell({
  camera,
  onExpand,
}: {
  camera: Camera;
  onExpand: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [connected, setConnected] = useState(false);
  const [detectionCount, setDetectionCount] = useState(0);

  useEffect(() => {
    if (camera.status !== "online") return;

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      ws = new WebSocket(getWsUrl(camera.id));

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws?.close();

      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          setDetectionCount(data.detections?.length || 0);

          const canvas = canvasRef.current;
          if (!canvas || !data.frame) return;

          const img = new Image();
          img.onload = () => {
            canvas.width = img.width;
            canvas.height = img.height;
            const ctx = canvas.getContext("2d");
            if (ctx) ctx.drawImage(img, 0, 0);
          };
          img.src = `data:image/jpeg;base64,${data.frame}`;
        } catch {
          // ignore parse errors
        }
      };
    }

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [camera.id, camera.status]);

  const isOffline = camera.status !== "online";

  return (
    <div
      className="relative border border-[#27272a] rounded-xl overflow-hidden bg-black group cursor-pointer transition-all duration-200 hover:border-[#3f3f46]"
      onClick={onExpand}
    >
      <div className="aspect-video relative">
        {isOffline ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#111113]">
            <WifiOff className="w-8 h-8 text-zinc-700 mb-2" />
            <span className="text-xs text-zinc-600">Camera Offline</span>
          </div>
        ) : (
          <>
            <canvas
              ref={canvasRef}
              className="w-full h-full object-contain"
            />
            {!connected && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/80">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                  <span className="text-xs text-zinc-400">Connecting...</span>
                </div>
              </div>
            )}
          </>
        )}

        {/* Live indicator */}
        {connected && !isOffline && (
          <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2 py-1 bg-black/50 backdrop-blur-sm rounded-md">
            <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-[10px] text-emerald-400 font-medium uppercase tracking-wider">
              Live
            </span>
          </div>
        )}

        {/* Detection badge */}
        {detectionCount > 0 && (
          <div className="absolute top-3 right-3 px-2 py-1 bg-red-500/80 backdrop-blur-sm rounded-md">
            <span className="text-[10px] text-white font-bold">
              {detectionCount} detected
            </span>
          </div>
        )}

        {/* Expand icon on hover */}
        <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <div className="p-1.5 bg-black/50 backdrop-blur-sm rounded-md">
            <Maximize2 className="w-3.5 h-3.5 text-white" />
          </div>
        </div>

        {/* Camera name overlay at bottom */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 via-black/30 to-transparent px-3 py-2.5 backdrop-blur-[2px]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm text-white font-medium truncate">
                {camera.name}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <div
                className={`w-1.5 h-1.5 rounded-full ${
                  connected ? "bg-emerald-500" : "bg-zinc-600"
                }`}
              />
              <span className="text-[11px] text-zinc-400">
                {camera.location || `ID: ${camera.id}`}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ExpandedCameraView({
  camera,
  onBack,
}: {
  camera: Camera;
  onBack: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [connected, setConnected] = useState(false);
  const [detectionCount, setDetectionCount] = useState(0);

  useEffect(() => {
    if (camera.status !== "online") return;

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      ws = new WebSocket(getWsUrl(camera.id));

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws?.close();

      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          setDetectionCount(data.detections?.length || 0);

          const canvas = canvasRef.current;
          if (!canvas || !data.frame) return;

          const img = new Image();
          img.onload = () => {
            canvas.width = img.width;
            canvas.height = img.height;
            const ctx = canvas.getContext("2d");
            if (ctx) ctx.drawImage(img, 0, 0);
          };
          img.src = `data:image/jpeg;base64,${data.frame}`;
        } catch {
          // ignore parse errors
        }
      };
    }

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [camera.id, camera.status]);

  return (
    <div className="fixed inset-0 z-[100] bg-black flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/80 backdrop-blur-sm border-b border-[#27272a]">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-zinc-300 hover:text-white hover:bg-[#27272a] transition-all duration-200"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="text-sm">Back to grid</span>
        </button>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            {connected && (
              <div className="flex items-center gap-1.5 px-2 py-1 bg-emerald-500/15 rounded-md">
                <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                <span className="text-[10px] text-emerald-400 font-medium uppercase tracking-wider">
                  Live
                </span>
              </div>
            )}
            <span className="text-white font-medium">{camera.name}</span>
          </div>
          {detectionCount > 0 && (
            <span className="px-2 py-1 bg-red-500/20 text-red-400 text-xs rounded-md font-medium">
              {detectionCount} detected
            </span>
          )}
        </div>
        <button
          onClick={onBack}
          className="p-2 rounded-lg text-zinc-400 hover:text-white hover:bg-[#27272a] transition-all duration-200"
        >
          <Minimize2 className="w-4 h-4" />
        </button>
      </div>

      {/* Full-screen video */}
      <div className="flex-1 flex items-center justify-center bg-black">
        {camera.status !== "online" ? (
          <div className="flex flex-col items-center gap-3">
            <WifiOff className="w-16 h-16 text-zinc-700" />
            <span className="text-zinc-500">Camera Offline</span>
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            className="max-w-full max-h-full object-contain"
          />
        )}
        {camera.status === "online" && !connected && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse" />
              <span className="text-zinc-400">Connecting...</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function LiveViewPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [gridSize, setGridSize] = useState<GridSize>("2x2");
  const [expandedCamera, setExpandedCamera] = useState<Camera | null>(null);
  const [error, setError] = useState("");
  const [privacyMode, setPrivacyMode] = useState(false);
  const [heatmapMode, setHeatmapMode] = useState(false);
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const fetchCameras = useCallback(async () => {
    try {
      setCameras(await getCameras());
      setError("");
    } catch {
      setError("Cannot connect to backend");
    }
  }, []);

  useEffect(() => {
    fetchCameras();
    const interval = setInterval(fetchCameras, 10000);
    return () => clearInterval(interval);
  }, [fetchCameras]);

  const enabledCameras = cameras.filter((c) => c.enabled);
  const onlineCount = cameras.filter((c) => c.status === "online").length;

  if (expandedCamera) {
    return (
      <ExpandedCameraView
        camera={expandedCamera}
        onBack={() => setExpandedCamera(null)}
      />
    );
  }

  return (
    <div className="-m-6 flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#27272a] bg-[#111113] flex-shrink-0">
        <div className="flex items-center gap-3">
          <MonitorPlay className="w-5 h-5 text-blue-400" />
          <h1 className="text-lg font-semibold text-white">Live View</h1>
          <span className="text-xs text-zinc-500 bg-[#27272a] px-2 py-0.5 rounded">
            {onlineCount}/{cameras.length} cameras
          </span>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex bg-[#09090b] border border-[#27272a] rounded-lg overflow-hidden">
            <button
              onClick={() => setGridSize("1x1")}
              className={`p-2 transition-all duration-200 ${
                gridSize === "1x1"
                  ? "bg-blue-500/15 text-blue-400"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
              title="1x1"
            >
              <Square className="w-4 h-4" />
            </button>
            <button
              onClick={() => setGridSize("2x2")}
              className={`p-2 transition-all duration-200 ${
                gridSize === "2x2"
                  ? "bg-blue-500/15 text-blue-400"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
              title="2x2"
            >
              <Grid2x2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => setGridSize("3x3")}
              className={`p-2 transition-all duration-200 ${
                gridSize === "3x3"
                  ? "bg-blue-500/15 text-blue-400"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
              title="3x3"
            >
              <Grid3x3 className="w-4 h-4" />
            </button>
            <button
              onClick={() => setGridSize("4x4")}
              className={`p-2 transition-all duration-200 ${
                gridSize === "4x4"
                  ? "bg-blue-500/15 text-blue-400"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
              title="4x4"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
          </div>

          <button
            onClick={async () => {
              const newState = !privacyMode;
              setPrivacyMode(newState);
              // Toggle for all online cameras
              for (const cam of cameras.filter(c => c.status === "online")) {
                try {
                  await fetch(`${API_BASE}/api/privacy/${cam.id}?enabled=${newState}`, { method: "POST" });
                } catch {}
              }
            }}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
              privacyMode
                ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                : "bg-[#09090b] border border-[#27272a] text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {privacyMode ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            {privacyMode ? "Privacy ON" : "Privacy OFF"}
          </button>

          <button
            onClick={async () => {
              const newState = !heatmapMode;
              setHeatmapMode(newState);
              for (const cam of cameras.filter(c => c.status === "online")) {
                try {
                  await fetch(`${API_BASE}/api/heatmap-overlay/${cam.id}?enabled=${newState}`, { method: "POST" });
                } catch {}
              }
            }}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
              heatmapMode
                ? "bg-orange-500/15 text-orange-400 border border-orange-500/30"
                : "bg-[#09090b] border border-[#27272a] text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Flame className="w-4 h-4" />
            {heatmapMode ? "Heatmap ON" : "Heatmap OFF"}
          </button>
        </div>
      </div>

      {/* Camera Grid */}
      <div className="flex-1 overflow-auto p-3">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-3 rounded-xl text-sm mb-3">
            {error}
          </div>
        )}

        {enabledCameras.length > 0 ? (
          <div className={`grid ${GRID_COLS[gridSize]} gap-3 h-full`}>
            {enabledCameras.map((cam) => (
              <LiveCameraCell
                key={cam.id}
                camera={cam}
                onExpand={() => setExpandedCamera(cam)}
              />
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-20 h-20 bg-[#18181b] border border-[#27272a] rounded-2xl flex items-center justify-center mx-auto mb-4">
                <MonitorPlay className="w-10 h-10 text-zinc-700" />
              </div>
              <h3 className="text-zinc-400 font-medium mb-1">
                No cameras available
              </h3>
              <p className="text-zinc-600 text-sm">
                Add and enable cameras to see live feeds
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
