"use client";

import { formatDistanceToNow } from "date-fns";
import type { Event } from "@/lib/api";

interface EventRowProps {
  event: Event;
  onAcknowledge?: (id: number, falseAlarm: boolean) => void;
}

const TYPE_COLORS: Record<string, string> = {
  enter: "bg-red-500/15 text-red-400",
  exit: "bg-yellow-500/15 text-yellow-400",
  loiter: "bg-orange-500/15 text-orange-400",
  count_above: "bg-purple-500/15 text-purple-400",
};

export default function EventRow({ event, onAcknowledge }: EventRowProps) {
  const typeColor = TYPE_COLORS[event.event_type] || "bg-zinc-500/15 text-zinc-400";
  const timeAgo = event.created_at
    ? formatDistanceToNow(new Date(event.created_at), { addSuffix: true })
    : "";

  return (
    <div className={`flex items-center gap-4 px-4 py-3 border-b border-[#1e1e1e] hover:bg-[#1a1a1a] transition-colors ${
      event.acknowledged ? "opacity-50" : ""
    }`}>
      <div className={`px-2 py-1 rounded text-xs font-medium ${typeColor}`}>
        {event.event_type}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm">
          <span className="font-medium">{event.object_type}</span>
          {event.zone_name && (
            <span className="text-zinc-500"> in {event.zone_name}</span>
          )}
        </div>
        <div className="text-xs text-zinc-600">
          Camera #{event.camera_id} &middot; {(event.confidence * 100).toFixed(0)}% confidence
        </div>
      </div>
      <div className="text-xs text-zinc-500 whitespace-nowrap">{timeAgo}</div>
      {!event.acknowledged && onAcknowledge && (
        <div className="flex gap-1">
          <button
            onClick={() => onAcknowledge(event.id, false)}
            className="px-2 py-1 text-xs bg-blue-600/20 text-blue-400 rounded hover:bg-blue-600/30 transition-colors"
          >
            ACK
          </button>
          <button
            onClick={() => onAcknowledge(event.id, true)}
            className="px-2 py-1 text-xs bg-zinc-600/20 text-zinc-400 rounded hover:bg-zinc-600/30 transition-colors"
          >
            False
          </button>
        </div>
      )}
    </div>
  );
}
