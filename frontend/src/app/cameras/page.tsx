"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getCameras,
  createCamera,
  deleteCamera,
  startCamera,
  stopCamera,
} from "@/lib/api";
import CameraFeed from "@/components/CameraFeed";
import type { Camera } from "@/lib/api";
import {
  Plus,
  Trash2,
  Play,
  Square,
  Camera as CameraIcon,
  Settings,
  MapPin,
  ChevronDown,
} from "lucide-react";

export default function CamerasPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", rtsp_url: "", location: "" });
  const [submitting, setSubmitting] = useState(false);
  const fetchCameras = useCallback(async () => {
    try {
      setCameras(await getCameras());
    } catch {
      // backend offline
    }
  }, []);

  useEffect(() => {
    fetchCameras();
    const interval = setInterval(fetchCameras, 5000);
    return () => clearInterval(interval);
  }, [fetchCameras]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.rtsp_url || submitting) return;
    setSubmitting(true);
    try {
      await createCamera(form);
      setForm({ name: "", rtsp_url: "", location: "" });
      setShowAdd(false);
      fetchCameras();
    } catch {
      // error
    }
    setSubmitting(false);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this camera?")) return;
    try {
      await deleteCamera(id);
      fetchCameras();
    } catch {
      // error
    }
  };

  const handleToggle = async (cam: Camera) => {
    try {
      if (cam.status === "online") {
        await stopCamera(cam.id);
      } else {
        await startCamera(cam.id);
      }
      fetchCameras();
    } catch {
      // error
    }
  };

  const statusColor = (status: string) => {
    switch (status) {
      case "online":
        return "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20";
      case "error":
        return "bg-red-500/15 text-red-400 border border-red-500/20";
      default:
        return "bg-zinc-500/15 text-zinc-400 border border-zinc-500/20";
    }
  };

  const onlineCount = cameras.filter((c) => c.status === "online").length;

  return (
    <div className="min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white">Cameras</h1>
          <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-500/15 text-zinc-400">
            {cameras.length} total
          </span>
          {onlineCount > 0 && (
            <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400">
              {onlineCount} online
            </span>
          )}
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-all duration-200"
        >
          <Plus className="w-4 h-4" />
          Add Camera
        </button>
      </div>

      {/* Add Camera Panel */}
      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          showAdd ? "max-h-[400px] opacity-100 mb-6" : "max-h-0 opacity-0 mb-0"
        }`}
      >
        <form
          onSubmit={handleAdd}
          className="bg-[#18181b] border border-[#27272a] rounded-xl p-6"
        >
          <h3 className="text-base font-semibold mb-5 text-white">
            New Camera
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-5">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Name
              </label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Front Door"
                className="w-full px-3 py-2.5 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white placeholder:text-zinc-600 focus:border-blue-500 focus:outline-none transition-all duration-200"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                RTSP URL
              </label>
              <input
                type="text"
                value={form.rtsp_url}
                onChange={(e) => setForm({ ...form, rtsp_url: e.target.value })}
                placeholder="rtsp://admin:pass@192.168.1.x:554/stream"
                className="w-full px-3 py-2.5 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white placeholder:text-zinc-600 focus:border-blue-500 focus:outline-none transition-all duration-200"
              />
              <p className="text-[11px] text-zinc-600 mt-1">
                e.g., rtsp://admin:pass@192.168.1.x:554/stream
              </p>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Location
              </label>
              <input
                type="text"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder="Building A, Floor 1"
                className="w-full px-3 py-2.5 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white placeholder:text-zinc-600 focus:border-blue-500 focus:outline-none transition-all duration-200"
              />
            </div>
          </div>
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-all duration-200"
            >
              {submitting ? "Adding..." : "Add Camera"}
            </button>
            <button
              type="button"
              onClick={() => setShowAdd(false)}
              className="px-5 py-2.5 bg-[#27272a] hover:bg-[#333] rounded-lg text-sm transition-all duration-200"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>

      {/* Camera Cards */}
      {cameras.length > 0 ? (
        <div className="grid gap-4">
          {cameras.map((cam) => (
            <div
              key={cam.id}
              className="group bg-[#18181b] border border-[#27272a] rounded-xl p-5 flex items-center gap-5 hover:border-[#333] transition-all duration-200"
            >
              {/* Thumbnail — live WebSocket feed */}
              <div className="w-[180px] flex-shrink-0 overflow-hidden rounded-lg">
                {cam.status === "online" ? (
                  <CameraFeed cameraId={cam.id} cameraName="" className="border-0 rounded-none" />
                ) : (
                  <div className="w-full h-[100px] bg-black flex items-center justify-center">
                    <CameraIcon className="w-8 h-8 text-zinc-700" />
                  </div>
                )}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="font-medium text-base text-white">
                  {cam.name}
                </div>
                <div className="text-xs text-zinc-500 font-mono truncate mt-0.5 max-w-md">
                  {cam.rtsp_url}
                </div>
                {cam.location && (
                  <div className="flex items-center gap-1 text-sm text-zinc-400 mt-1">
                    <MapPin className="w-3 h-3" />
                    {cam.location}
                  </div>
                )}
                {cam.width && cam.height && (
                  <span className="inline-block mt-1.5 px-2 py-0.5 rounded text-[11px] font-medium bg-zinc-700 text-zinc-300">
                    {cam.width}x{cam.height}
                  </span>
                )}
              </div>

              {/* Right Side */}
              <div className="flex flex-col items-end gap-3">
                <span
                  className={`px-2.5 py-1 rounded-full text-xs font-medium ${statusColor(
                    cam.status
                  )}`}
                >
                  {cam.status}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleToggle(cam)}
                    className="p-2 rounded-lg hover:bg-[#27272a] transition-all duration-200"
                    title={cam.status === "online" ? "Stop" : "Start"}
                  >
                    {cam.status === "online" ? (
                      <Square className="w-4 h-4 text-amber-400" />
                    ) : (
                      <Play className="w-4 h-4 text-emerald-400" />
                    )}
                  </button>
                  <button
                    className="p-2 rounded-lg hover:bg-[#27272a] transition-all duration-200 opacity-50 cursor-default"
                    title="Settings (coming soon)"
                  >
                    <Settings className="w-4 h-4 text-zinc-400" />
                  </button>
                  <button
                    onClick={() => handleDelete(cam.id)}
                    className="p-2 rounded-lg hover:bg-red-500/10 transition-all duration-200 text-zinc-500 hover:text-red-400"
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
                <span className="text-[11px] text-zinc-600">
                  {cam.created_at
                    ? new Date(cam.created_at).toLocaleDateString()
                    : ""}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Empty State */
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-16 text-center">
          <CameraIcon className="w-16 h-16 text-zinc-700 mx-auto mb-4" />
          <div className="text-lg text-zinc-400 font-medium">
            No cameras configured
          </div>
          <div className="text-sm text-zinc-600 mt-1">
            Connect your first IP camera to start monitoring
          </div>
          <button
            onClick={() => setShowAdd(true)}
            className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-all duration-200"
          >
            <Plus className="w-4 h-4" />
            Add Camera
          </button>
        </div>
      )}
    </div>
  );
}
