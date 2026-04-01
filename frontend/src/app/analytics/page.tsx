"use client";

import { useEffect, useState, useCallback } from "react";
import { getCameras } from "@/lib/api";
import type { Camera } from "@/lib/api";
import {
  BarChart3,
  Eye,
  EyeOff,
  RotateCcw,
  ChevronDown,
  Flame,
  MapPin,
  Percent,
  Loader2,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface HeatmapStats {
  total_detections: number;
  peak_cell_value: number;
  coverage_percent: number;
}

export default function AnalyticsPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCamera, setSelectedCamera] = useState<number | null>(null);
  const [stats, setStats] = useState<HeatmapStats | null>(null);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Load cameras
  useEffect(() => {
    getCameras()
      .then((cams) => {
        setCameras(cams);
        if (cams.length > 0 && selectedCamera === null) {
          setSelectedCamera(cams[0].id);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    if (selectedCamera === null) return;
    try {
      const res = await fetch(
        `${API_BASE}/api/ops/heatmap/${selectedCamera}/stats`
      );
      if (res.ok) {
        const data: HeatmapStats = await res.json();
        setStats(data);
      }
    } catch {
      // ignore
    }
  }, [selectedCamera]);

  // Auto-refresh stats and heatmap every 5 seconds
  useEffect(() => {
    if (selectedCamera === null) return;
    fetchStats();
    const interval = setInterval(() => {
      setRefreshKey((k) => k + 1);
      fetchStats();
    }, 5000);
    return () => clearInterval(interval);
  }, [selectedCamera, fetchStats]);

  const handleReset = async () => {
    if (selectedCamera === null) return;
    setResetting(true);
    try {
      await fetch(`${API_BASE}/api/ops/heatmap/${selectedCamera}/reset`, {
        method: "POST",
      });
      setRefreshKey((k) => k + 1);
      await fetchStats();
    } catch {
      // ignore
    }
    setResetting(false);
  };

  const selectedCameraObj = cameras.find((c) => c.id === selectedCamera);

  const heatmapUrl =
    selectedCamera !== null
      ? `${API_BASE}/api/ops/heatmap/${selectedCamera}?t=${refreshKey}`
      : null;

  const snapshotUrl =
    selectedCamera !== null
      ? `${API_BASE}/api/cameras/${selectedCamera}/snapshot?t=${refreshKey}`
      : null;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 text-zinc-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Analytics
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Heatmap visualization of movement patterns over time
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Camera selector */}
          <div className="relative">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2 px-4 py-2 bg-[#18181b] border border-[#27272a] rounded-lg text-sm text-zinc-300 hover:border-zinc-600 transition-colors"
            >
              <MapPin className="w-4 h-4 text-zinc-500" />
              <span>{selectedCameraObj?.name || "Select Camera"}</span>
              <ChevronDown className="w-4 h-4 text-zinc-500" />
            </button>
            {dropdownOpen && (
              <div className="absolute right-0 mt-1 w-56 bg-[#18181b] border border-[#27272a] rounded-lg shadow-xl z-50 py-1">
                {cameras.map((cam) => (
                  <button
                    key={cam.id}
                    onClick={() => {
                      setSelectedCamera(cam.id);
                      setDropdownOpen(false);
                    }}
                    className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                      cam.id === selectedCamera
                        ? "bg-blue-500/10 text-blue-400"
                        : "text-zinc-400 hover:bg-[#27272a] hover:text-zinc-200"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className={`w-2 h-2 rounded-full ${
                          cam.status === "online"
                            ? "bg-emerald-500"
                            : "bg-zinc-600"
                        }`}
                      />
                      {cam.name}
                    </div>
                    {cam.location && (
                      <div className="text-xs text-zinc-600 mt-0.5 ml-4">
                        {cam.location}
                      </div>
                    )}
                  </button>
                ))}
                {cameras.length === 0 && (
                  <div className="px-4 py-3 text-sm text-zinc-600">
                    No cameras configured
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Toggle heatmap */}
          <button
            onClick={() => setShowHeatmap(!showHeatmap)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm border transition-colors ${
              showHeatmap
                ? "bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/20"
                : "bg-[#18181b] border-[#27272a] text-zinc-400 hover:border-zinc-600"
            }`}
          >
            {showHeatmap ? (
              <Eye className="w-4 h-4" />
            ) : (
              <EyeOff className="w-4 h-4" />
            )}
            {showHeatmap ? "Heatmap On" : "Heatmap Off"}
          </button>

          {/* Reset */}
          <button
            onClick={handleReset}
            disabled={resetting || selectedCamera === null}
            className="flex items-center gap-2 px-4 py-2 bg-[#18181b] border border-[#27272a] rounded-lg text-sm text-zinc-400 hover:border-red-500/30 hover:text-red-400 transition-colors disabled:opacity-50"
          >
            {resetting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RotateCcw className="w-4 h-4" />
            )}
            Reset
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 bg-blue-500/10 rounded-lg flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-blue-400" />
            </div>
            <div className="text-xs text-zinc-500 uppercase tracking-wider font-medium">
              Total Detections
            </div>
          </div>
          <div className="text-3xl font-bold text-white">
            {stats ? stats.total_detections.toLocaleString() : "--"}
          </div>
          <div className="text-xs text-zinc-600 mt-1">
            Person detections accumulated
          </div>
        </div>

        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 bg-orange-500/10 rounded-lg flex items-center justify-center">
              <Flame className="w-5 h-5 text-orange-400" />
            </div>
            <div className="text-xs text-zinc-500 uppercase tracking-wider font-medium">
              Peak Zone
            </div>
          </div>
          <div className="text-3xl font-bold text-white">
            {stats ? stats.peak_cell_value.toLocaleString() : "--"}
          </div>
          <div className="text-xs text-zinc-600 mt-1">
            Hottest cell value
          </div>
        </div>

        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 bg-emerald-500/10 rounded-lg flex items-center justify-center">
              <Percent className="w-5 h-5 text-emerald-400" />
            </div>
            <div className="text-xs text-zinc-500 uppercase tracking-wider font-medium">
              Coverage
            </div>
          </div>
          <div className="text-3xl font-bold text-white">
            {stats ? `${stats.coverage_percent}%` : "--"}
          </div>
          <div className="text-xs text-zinc-600 mt-1">
            Area with activity
          </div>
        </div>
      </div>

      {/* Heatmap Viewer */}
      <div className="bg-[#18181b] border border-[#27272a] rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-[#27272a] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Flame className="w-4 h-4 text-orange-400" />
            <span className="text-sm font-medium text-zinc-200">
              Movement Heatmap
            </span>
          </div>
          <div className="flex items-center gap-4">
            {/* Legend */}
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span>Low</span>
              <div className="flex h-3 rounded overflow-hidden">
                <div className="w-6 bg-blue-600" />
                <div className="w-6 bg-cyan-500" />
                <div className="w-6 bg-green-500" />
                <div className="w-6 bg-yellow-400" />
                <div className="w-6 bg-orange-500" />
                <div className="w-6 bg-red-500" />
              </div>
              <span>High</span>
            </div>
            <div className="text-xs text-zinc-600">
              Auto-refreshes every 5s
            </div>
          </div>
        </div>

        <div className="relative bg-black aspect-video">
          {selectedCamera !== null ? (
            <>
              {/* Camera snapshot as background */}
              {snapshotUrl && (
                <img
                  key={`snap-${refreshKey}`}
                  src={snapshotUrl}
                  alt="Camera view"
                  className="absolute inset-0 w-full h-full object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              )}

              {/* Heatmap overlay */}
              {showHeatmap && heatmapUrl && (
                <img
                  key={`heat-${refreshKey}`}
                  src={heatmapUrl}
                  alt="Heatmap overlay"
                  className="absolute inset-0 w-full h-full object-contain opacity-60"
                  style={{ mixBlendMode: "screen" }}
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              )}

              {/* No data placeholder */}
              {stats && stats.total_detections === 0 && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <BarChart3 className="w-12 h-12 text-zinc-700 mx-auto mb-3" />
                    <p className="text-zinc-500 text-sm">
                      No detection data yet
                    </p>
                    <p className="text-zinc-600 text-xs mt-1">
                      Heatmap will build up as people are detected
                    </p>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <MapPin className="w-12 h-12 text-zinc-700 mx-auto mb-3" />
                <p className="text-zinc-500 text-sm">
                  Select a camera to view the heatmap
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
