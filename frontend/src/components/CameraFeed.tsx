"use client";

import { useEffect, useRef, useState } from "react";
import { getWsUrl } from "@/lib/api";
import { Wifi, WifiOff } from "lucide-react";

interface CameraFeedProps {
  cameraId: number;
  cameraName: string;
  className?: string;
}

export default function CameraFeed({ cameraId, cameraName, className = "" }: CameraFeedProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [connected, setConnected] = useState(false);
  const [detectionCount, setDetectionCount] = useState(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      ws = new WebSocket(getWsUrl(cameraId));

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

          // Draw frame on canvas
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
  }, [cameraId]);

  return (
    <div className={`bg-[#141414] border border-[#262626] rounded-xl overflow-hidden ${className}`}>
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#262626]">
        <div className="flex items-center gap-2">
          {connected ? (
            <Wifi className="w-3.5 h-3.5 text-green-400" />
          ) : (
            <WifiOff className="w-3.5 h-3.5 text-red-400" />
          )}
          <span className="text-sm font-medium">{cameraName}</span>
        </div>
        {detectionCount > 0 && (
          <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">
            {detectionCount} detected
          </span>
        )}
      </div>
      <div className="relative aspect-video bg-black flex items-center justify-center">
        <canvas ref={canvasRef} className="w-full h-full object-contain" />
        {!connected && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80">
            <span className="text-sm text-zinc-500">Connecting...</span>
          </div>
        )}
      </div>
    </div>
  );
}
