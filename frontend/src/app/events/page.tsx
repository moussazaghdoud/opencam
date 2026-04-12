"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getEvents,
  getCameras,
  acknowledgeEvent,
  getEventSnapshotUrl,
} from "@/lib/api";
import type { Event, Camera } from "@/lib/api";
import AINarration from "@/components/AINarration";
import {
  Bell,
  X,
  Filter,
  CheckCircle,
  AlertTriangle,
  Eye,
  ChevronDown,
} from "lucide-react";
import { formatDistanceToNow, format } from "date-fns";

const EVENT_TYPES = [
  { value: "", label: "All Types" },
  { value: "enter", label: "Intrusion" },
  { value: "face_known", label: "Known Face" },
  { value: "face_unknown", label: "Unknown Face" },
  { value: "count_above", label: "Counting" },
];

const eventTypeColor = (type: string) => {
  switch (type) {
    case "enter":
    case "face_unknown":
      return {
        bar: "bg-red-500",
        badge: "bg-red-500/15 text-red-400 border border-red-500/20",
      };
    case "face_known":
      return {
        bar: "bg-emerald-500",
        badge:
          "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20",
      };
    case "count_above":
      return {
        bar: "bg-blue-500",
        badge: "bg-blue-500/15 text-blue-400 border border-blue-500/20",
      };
    default:
      return {
        bar: "bg-amber-500",
        badge: "bg-amber-500/15 text-amber-400 border border-amber-500/20",
      };
  }
};

const eventTypeLabel = (type: string) => {
  switch (type) {
    case "enter":
      return "Intrusion";
    case "face_known":
      return "Known Face";
    case "face_unknown":
      return "Unknown Face";
    case "count_above":
      return "Count Alert";
    default:
      return type;
  }
};

export default function EventsPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);
  const [filterType, setFilterType] = useState("");
  const [filterCamera, setFilterCamera] = useState<number | 0>(0);
  const [filterAcknowledged, setFilterAcknowledged] = useState<
    "" | "true" | "false"
  >("");

  const fetchEvents = useCallback(async () => {
    try {
      const params: { camera_id?: number; limit?: number } = { limit: 200 };
      if (filterCamera) params.camera_id = filterCamera;
      setEvents(await getEvents(params));
    } catch {
      // backend offline
    }
  }, [filterCamera]);

  const fetchCameras = useCallback(async () => {
    try {
      setCameras(await getCameras());
    } catch {
      // backend offline
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    fetchCameras();
    const interval = setInterval(fetchEvents, 5000);
    return () => clearInterval(interval);
  }, [fetchEvents, fetchCameras]);

  const handleAck = async (eventId: number, falseAlarm: boolean) => {
    try {
      await acknowledgeEvent(eventId, falseAlarm);
      fetchEvents();
      if (selectedEvent?.id === eventId) {
        setSelectedEvent((prev) =>
          prev
            ? {
                ...prev,
                acknowledged: true,
                false_alarm: falseAlarm,
              }
            : null
        );
      }
    } catch {
      // error
    }
  };

  const getCameraName = (id: number) => {
    const cam = cameras.find((c) => c.id === id);
    return cam ? cam.name : `Camera #${id}`;
  };

  // Client-side filtering
  const filteredEvents = events.filter((e) => {
    if (filterType && e.event_type !== filterType) return false;
    if (
      filterAcknowledged === "true" &&
      !e.acknowledged
    )
      return false;
    if (
      filterAcknowledged === "false" &&
      e.acknowledged
    )
      return false;
    return true;
  });

  const unacknowledgedCount = events.filter((e) => !e.acknowledged).length;

  return (
    <div className="min-h-full flex flex-col">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white">Events</h1>
            <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-500/15 text-zinc-400">
              {events.length} total
            </span>
            {unacknowledgedCount > 0 && (
              <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/15 text-red-400 border border-red-500/20">
                {unacknowledgedCount} unacknowledged
              </span>
            )}
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative">
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="appearance-none pl-3 pr-8 py-2 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white focus:border-blue-500 focus:outline-none transition-all duration-200 cursor-pointer"
            >
              {EVENT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-zinc-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          <div className="relative">
            <select
              value={filterCamera}
              onChange={(e) => setFilterCamera(Number(e.target.value))}
              className="appearance-none pl-3 pr-8 py-2 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white focus:border-blue-500 focus:outline-none transition-all duration-200 cursor-pointer"
            >
              <option value={0}>All Cameras</option>
              {cameras.map((cam) => (
                <option key={cam.id} value={cam.id}>
                  {cam.name}
                </option>
              ))}
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-zinc-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          <div className="relative">
            <select
              value={filterAcknowledged}
              onChange={(e) =>
                setFilterAcknowledged(e.target.value as "" | "true" | "false")
              }
              className="appearance-none pl-3 pr-8 py-2 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white focus:border-blue-500 focus:outline-none transition-all duration-200 cursor-pointer"
            >
              <option value="">All Status</option>
              <option value="false">Pending</option>
              <option value="true">Acknowledged</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-zinc-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* Split View */}
      <div className="flex gap-6 flex-1 min-h-0">
        {/* Event List */}
        <div className="flex-1 overflow-y-auto max-h-[calc(100vh-220px)]">
          {filteredEvents.length > 0 ? (
            <div className="space-y-1">
              {filteredEvents.map((event) => {
                const colors = eventTypeColor(event.event_type);
                const isSelected = selectedEvent?.id === event.id;
                return (
                  <div
                    key={event.id}
                    onClick={() => setSelectedEvent(event)}
                    className={`group relative flex items-center gap-4 px-4 py-3.5 rounded-xl cursor-pointer transition-all duration-200 ${
                      isSelected
                        ? "bg-blue-500/5 border border-blue-500/20"
                        : "bg-[#18181b] border border-[#27272a] hover:bg-[#1e1e22] hover:border-[#333]"
                    }`}
                  >
                    {/* Left color bar */}
                    <div
                      className={`absolute left-0 top-3 bottom-3 w-1 rounded-r ${colors.bar} ${
                        !event.acknowledged ? "shadow-[0_0_8px_rgba(0,0,0,0.3)]" : "opacity-50"
                      }`}
                    />

                    {/* Content */}
                    <div className="flex-1 min-w-0 pl-2">
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[11px] font-medium ${colors.badge}`}
                        >
                          {eventTypeLabel(event.event_type)}
                        </span>
                        {!event.acknowledged && (
                          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                        )}
                      </div>
                      <div className="text-sm text-zinc-200">
                        {event.object_type
                          ? `${event.object_type.charAt(0).toUpperCase() + event.object_type.slice(1)} detected`
                          : "Activity detected"}
                        {event.zone_name && (
                          <span className="text-zinc-500">
                            {" "}
                            in {event.zone_name}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-zinc-500 mt-0.5">
                        {getCameraName(event.camera_id)}
                      </div>
                    </div>

                    {/* Right info */}
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <span className="text-xs text-zinc-500">
                        {(event.confidence * 100).toFixed(0)}%
                      </span>
                      <span className="text-[11px] text-zinc-600">
                        {event.created_at
                          ? formatDistanceToNow(new Date(event.created_at), {
                              addSuffix: true,
                            })
                          : ""}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-16 text-center">
              <Bell className="w-16 h-16 text-zinc-700 mx-auto mb-4" />
              <div className="text-lg text-zinc-400 font-medium">
                No events recorded
              </div>
              <div className="text-sm text-zinc-600 mt-1">
                Events will appear here when cameras detect activity
              </div>
            </div>
          )}
        </div>

        {/* Detail Panel */}
        {selectedEvent && (
          <div className="w-[420px] flex-shrink-0 bg-[#18181b] border border-[#27272a] rounded-xl overflow-hidden h-fit sticky top-0 max-h-[calc(100vh-220px)] overflow-y-auto">
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b border-[#27272a]">
              <h3 className="font-semibold text-white">
                Event #{selectedEvent.id}
              </h3>
              <button
                onClick={() => setSelectedEvent(null)}
                className="p-1.5 rounded-lg hover:bg-[#27272a] transition-all duration-200"
              >
                <X className="w-4 h-4 text-zinc-400" />
              </button>
            </div>

            {/* Snapshot */}
            {selectedEvent.snapshot_path && (
              <div className="mx-5 mt-5 rounded-lg overflow-hidden bg-black aspect-video flex items-center justify-center">
                <img
                  src={getEventSnapshotUrl(selectedEvent.id)}
                  alt="Event snapshot"
                  className="w-full h-full object-contain"
                />
              </div>
            )}

            {/* Details */}
            <div className="p-5 space-y-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-500">Type</span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      eventTypeColor(selectedEvent.event_type).badge
                    }`}
                  >
                    {eventTypeLabel(selectedEvent.event_type)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-500">Object</span>
                  <span className="text-white">
                    {selectedEvent.object_type || "N/A"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-500">Confidence</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 bg-[#27272a] rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          selectedEvent.confidence >= 0.8
                            ? "bg-emerald-500"
                            : selectedEvent.confidence >= 0.5
                            ? "bg-amber-500"
                            : "bg-red-500"
                        }`}
                        style={{
                          width: `${selectedEvent.confidence * 100}%`,
                        }}
                      />
                    </div>
                    <span className="text-white text-xs font-medium">
                      {(selectedEvent.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-500">Zone</span>
                  <span className="text-white">
                    {selectedEvent.zone_name || "N/A"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-500">Camera</span>
                  <span className="text-white">
                    {getCameraName(selectedEvent.camera_id)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-500">Time</span>
                  <span className="text-white text-xs">
                    {selectedEvent.created_at
                      ? format(
                          new Date(selectedEvent.created_at),
                          "MMM d, yyyy HH:mm:ss"
                        )
                      : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-500">Status</span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      selectedEvent.false_alarm
                        ? "bg-zinc-500/15 text-zinc-400"
                        : selectedEvent.acknowledged
                        ? "bg-emerald-500/15 text-emerald-400"
                        : "bg-amber-500/15 text-amber-400"
                    }`}
                  >
                    {selectedEvent.false_alarm
                      ? "False Alarm"
                      : selectedEvent.acknowledged
                      ? "Acknowledged"
                      : "Pending"}
                  </span>
                </div>
              </div>

              {/* AI Narration — optional enrichment, renders nothing if disabled */}
              <AINarration eventId={selectedEvent.id} />

              {/* Actions */}
              {!selectedEvent.acknowledged && (
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={() => handleAck(selectedEvent.id, false)}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-all duration-200"
                  >
                    <CheckCircle className="w-4 h-4" />
                    Acknowledge
                  </button>
                  <button
                    onClick={() => handleAck(selectedEvent.id, true)}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-[#27272a] hover:bg-[#333] rounded-lg text-sm font-medium transition-all duration-200"
                  >
                    <AlertTriangle className="w-4 h-4" />
                    False Alarm
                  </button>
                </div>
              )}

              <button className="w-full flex items-center justify-center gap-2 py-2.5 border border-[#27272a] hover:border-[#333] rounded-lg text-sm font-medium text-zinc-400 hover:text-white transition-all duration-200">
                <Eye className="w-4 h-4" />
                View Camera
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
