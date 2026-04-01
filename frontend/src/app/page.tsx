"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import CameraFeed from "@/components/CameraFeed";
import { getDashboard, getCameras, getEvents, acknowledgeEvent } from "@/lib/api";
import type { DashboardData, Camera, Event } from "@/lib/api";
import {
  Camera as CameraIcon,
  AlertTriangle,
  Users,
  ScanFace,
  HeartPulse,
  Grid2x2,
  Grid3x3,
  LayoutGrid,
  Plus,
  ArrowUpRight,
  ArrowDownRight,
  ChevronRight,
} from "lucide-react";

type GridSize = "2x2" | "3x3" | "4x4";

const GRID_COLS: Record<GridSize, string> = {
  "2x2": "grid-cols-1 md:grid-cols-2",
  "3x3": "grid-cols-1 md:grid-cols-2 lg:grid-cols-3",
  "4x4": "grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
};

const EVENT_DOT_COLORS: Record<string, string> = {
  enter: "bg-red-500",
  exit: "bg-amber-500",
  count_above: "bg-blue-500",
  face_known: "bg-emerald-500",
  face_unknown: "bg-amber-500",
  loiter: "bg-orange-500",
};

const EVENT_DESCRIPTIONS: Record<string, string> = {
  enter: "Intrusion detected",
  exit: "Object exited zone",
  count_above: "Count threshold exceeded",
  face_known: "Known face recognized",
  face_unknown: "Unknown face detected",
  loiter: "Loitering detected",
};

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState("");
  const [gridSize, setGridSize] = useState<GridSize>("3x3");

  const fetchData = async () => {
    try {
      const [dash, cams, evts] = await Promise.all([
        getDashboard(),
        getCameras(),
        getEvents({ limit: 20 }),
      ]);
      setData(dash);
      setCameras(cams);
      setEvents(evts);
      setError("");
    } catch {
      setError("Cannot connect to backend. Is the server running?");
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleAck = async (eventId: number, falseAlarm: boolean) => {
    await acknowledgeEvent(eventId, falseAlarm);
    fetchData();
  };

  const onlineCameras = cameras.filter((c) => c.status === "online");
  const offlineCameras = cameras.filter((c) => c.status !== "online");
  const unacknowledgedEvents = events.filter((e) => !e.acknowledged);
  const systemHealthPct = cameras.length > 0
    ? Math.round((onlineCameras.length / cameras.length) * 100)
    : 100;

  return (
    <div className="space-y-6">
      {/* Error Banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-3 rounded-xl text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Total Cameras */}
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-5 transition-all duration-200 hover:border-[#3f3f46]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-zinc-500 font-medium uppercase tracking-wide">
              Total Cameras
            </span>
            <div className="w-8 h-8 bg-blue-500/10 rounded-lg flex items-center justify-center">
              <CameraIcon className="w-4 h-4 text-blue-400" />
            </div>
          </div>
          <div className="text-3xl font-bold text-white">{cameras.length}</div>
          <div className="text-xs text-zinc-500 mt-1.5 flex items-center gap-2">
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
              {onlineCameras.length} online
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-zinc-600 rounded-full" />
              {offlineCameras.length} offline
            </span>
          </div>
        </div>

        {/* Active Alerts */}
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-5 transition-all duration-200 hover:border-[#3f3f46]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-zinc-500 font-medium uppercase tracking-wide">
              Active Alerts
            </span>
            <div className="w-8 h-8 bg-red-500/10 rounded-lg flex items-center justify-center">
              <AlertTriangle className="w-4 h-4 text-red-400" />
            </div>
          </div>
          <div className="text-3xl font-bold text-white">
            {data?.events.unacknowledged ?? 0}
          </div>
          <div className="text-xs text-zinc-500 mt-1.5 flex items-center gap-1">
            {(data?.events.unacknowledged ?? 0) > 0 ? (
              <>
                <ArrowUpRight className="w-3 h-3 text-red-400" />
                <span className="text-red-400">
                  {unacknowledgedEvents.length} pending review
                </span>
              </>
            ) : (
              <>
                <ArrowDownRight className="w-3 h-3 text-emerald-400" />
                <span className="text-emerald-400">All clear</span>
              </>
            )}
          </div>
        </div>

        {/* People Detected */}
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-5 transition-all duration-200 hover:border-[#3f3f46]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-zinc-500 font-medium uppercase tracking-wide">
              People Detected
            </span>
            <div className="w-8 h-8 bg-purple-500/10 rounded-lg flex items-center justify-center">
              <Users className="w-4 h-4 text-purple-400" />
            </div>
          </div>
          <div className="text-3xl font-bold text-white">
            {events.filter((e) => e.object_type === "person").length}
          </div>
          <div className="text-xs text-zinc-500 mt-1.5">Last hour</div>
        </div>

        {/* Face Matches */}
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-5 transition-all duration-200 hover:border-[#3f3f46]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-zinc-500 font-medium uppercase tracking-wide">
              Face Matches
            </span>
            <div className="w-8 h-8 bg-emerald-500/10 rounded-lg flex items-center justify-center">
              <ScanFace className="w-4 h-4 text-emerald-400" />
            </div>
          </div>
          <div className="text-3xl font-bold text-white">
            {events.filter((e) => e.event_type === "face_known").length}
          </div>
          <div className="text-xs text-zinc-500 mt-1.5 flex items-center gap-2">
            <span className="text-emerald-400">
              {events.filter((e) => e.event_type === "face_known").length} known
            </span>
            <span className="text-amber-400">
              {events.filter((e) => e.event_type === "face_unknown").length} unknown
            </span>
          </div>
        </div>

        {/* System Health */}
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-5 transition-all duration-200 hover:border-[#3f3f46]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-zinc-500 font-medium uppercase tracking-wide">
              System Health
            </span>
            <div
              className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                systemHealthPct >= 80
                  ? "bg-emerald-500/10"
                  : systemHealthPct >= 50
                  ? "bg-amber-500/10"
                  : "bg-red-500/10"
              }`}
            >
              <HeartPulse
                className={`w-4 h-4 ${
                  systemHealthPct >= 80
                    ? "text-emerald-400"
                    : systemHealthPct >= 50
                    ? "text-amber-400"
                    : "text-red-400"
                }`}
              />
            </div>
          </div>
          <div
            className={`text-3xl font-bold ${
              systemHealthPct >= 80
                ? "text-emerald-400"
                : systemHealthPct >= 50
                ? "text-amber-400"
                : "text-red-400"
            }`}
          >
            {systemHealthPct}%
          </div>
          <div className="text-xs text-zinc-500 mt-1.5">
            {cameras.length === 0
              ? "No cameras configured"
              : systemHealthPct === 100
              ? "All systems operational"
              : `${offlineCameras.length} camera${offlineCameras.length > 1 ? "s" : ""} offline`}
          </div>
        </div>
      </div>

      {/* Camera Grid Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Live Feeds</h2>
          <div className="flex items-center gap-2">
            <div className="flex bg-[#18181b] border border-[#27272a] rounded-lg overflow-hidden">
              <button
                onClick={() => setGridSize("2x2")}
                className={`p-2 transition-all duration-200 ${
                  gridSize === "2x2"
                    ? "bg-blue-500/15 text-blue-400"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
                title="2x2 Grid"
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
                title="3x3 Grid"
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
                title="4x4 Grid"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {cameras.filter((c) => c.enabled).length > 0 ? (
          <div className={`grid ${GRID_COLS[gridSize]} gap-4`}>
            {cameras
              .filter((c) => c.enabled)
              .map((cam) => (
                <div
                  key={cam.id}
                  className="bg-[#18181b] border border-[#27272a] rounded-xl overflow-hidden transition-all duration-200 hover:border-[#3f3f46] group"
                >
                  <CameraFeed
                    cameraId={cam.id}
                    cameraName={cam.name}
                    className="border-0 rounded-none bg-transparent"
                  />
                </div>
              ))}
          </div>
        ) : (
          <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-16 text-center">
            <div className="w-16 h-16 bg-[#27272a] rounded-2xl flex items-center justify-center mx-auto mb-4">
              <CameraIcon className="w-8 h-8 text-zinc-600" />
            </div>
            <h3 className="text-zinc-400 font-medium mb-1">
              No cameras configured
            </h3>
            <p className="text-zinc-600 text-sm mb-5">
              Add your first IP camera to start monitoring
            </p>
            <Link
              href="/cameras"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-all duration-200"
            >
              <Plus className="w-4 h-4" />
              Add Camera
            </Link>
          </div>
        )}
      </div>

      {/* Recent Activity Timeline */}
      <div className="bg-[#18181b] border border-[#27272a] rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#27272a]">
          <h2 className="text-lg font-semibold text-white">Recent Activity</h2>
          <Link
            href="/events"
            className="flex items-center gap-1 text-sm text-blue-400 hover:text-blue-300 transition-colors duration-200"
          >
            View All
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>

        {data?.recent_events && data.recent_events.length > 0 ? (
          <div className="divide-y divide-[#27272a]">
            {data.recent_events.slice(0, 10).map((event) => {
              const dotColor =
                EVENT_DOT_COLORS[event.event_type] || "bg-zinc-500";
              const description =
                EVENT_DESCRIPTIONS[event.event_type] || event.event_type;
              const timeAgo = event.created_at
                ? formatDistanceToNow(new Date(event.created_at), {
                    addSuffix: true,
                  })
                : "";

              return (
                <div
                  key={event.id}
                  className="flex items-center gap-4 px-5 py-3.5 hover:bg-[#1e1e22] transition-all duration-200 cursor-pointer group"
                >
                  {/* Left: colored dot */}
                  <div
                    className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${dotColor}`}
                  />

                  {/* Middle: description */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-zinc-200">
                      <span className="font-medium">{description}</span>
                      <span className="text-zinc-500">
                        {" "}
                        &middot; {event.object_type}
                      </span>
                      {event.zone_name && (
                        <span className="text-zinc-600">
                          {" "}
                          in {event.zone_name}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-zinc-600 mt-0.5">
                      Camera #{event.camera_id} &middot;{" "}
                      {(event.confidence * 100).toFixed(0)}% confidence
                    </div>
                  </div>

                  {/* Right: timestamp */}
                  <div className="text-xs text-zinc-500 whitespace-nowrap flex-shrink-0">
                    {timeAgo}
                  </div>

                  {/* Acknowledge button */}
                  {!event.acknowledged && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleAck(event.id, false);
                      }}
                      className="opacity-0 group-hover:opacity-100 px-2.5 py-1 text-xs bg-blue-500/15 text-blue-400 rounded-md hover:bg-blue-500/25 transition-all duration-200"
                    >
                      ACK
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-12 text-center">
            <div className="text-zinc-600 text-sm">
              No events yet. Add a camera and configure zones to start
              detecting.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
