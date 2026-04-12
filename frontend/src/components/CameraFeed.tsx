"use client";

import { useEffect, useRef, useState } from "react";
import { getWsUrl } from "@/lib/api";
import { Wifi, WifiOff } from "lucide-react";

interface CameraFeedProps {
  cameraId: number;
  cameraName: string;
  className?: string;
}

// Shared AudioContext — initialized on first user interaction to satisfy browser autoplay policy
let _audioCtx: AudioContext | null = null;
let _audioAvailable = typeof window !== "undefined" && typeof window.AudioContext !== "undefined";

function getAudioCtx(): AudioContext | null {
  if (!_audioAvailable) return null;
  try {
    if (!_audioCtx) {
      _audioCtx = new AudioContext();
    }
    if (_audioCtx.state === "suspended") {
      _audioCtx.resume();
    }
    return _audioCtx;
  } catch {
    _audioAvailable = false;
    return null;
  }
}

// Initialize audio on first user click/touch anywhere on the page
if (typeof window !== "undefined" && _audioAvailable) {
  const unlock = () => {
    getAudioCtx();
    window.removeEventListener("click", unlock);
    window.removeEventListener("touchstart", unlock);
  };
  window.addEventListener("click", unlock, { once: true });
  window.addEventListener("touchstart", unlock, { once: true });
}

// Per-name cooldown: don't announce same person more than once per 30s (shared across all feeds)
const _announcedAt: Record<string, number> = {};

function playBeep() {
  try {
    const ctx = getAudioCtx();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    gain.gain.value = 0.3;
    osc.start();
    osc.stop(ctx.currentTime + 0.15);
  } catch { /* audio not available */ }
}

function announce(key: string, message: string) {
  const now = Date.now();
  if (_announcedAt[key] && now - _announcedAt[key] < 30_000) return;
  _announcedAt[key] = now;

  playBeep();

  if (!("speechSynthesis" in window)) return;
  setTimeout(() => {
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(message);
    utt.lang = "en-US";
    utt.rate = 0.95;
    utt.pitch = 1.05;
    window.speechSynthesis.speak(utt);
  }, 200);
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

          // Announce known faces by name
          if (Array.isArray(data.faces)) {
            for (const face of data.faces) {
              if (face.known && face.name) {
                announce(`face_${face.name}`, `Hello ${face.name}`);
              }
            }
          }

          // Announce safety jacket detection
          if (data.safety_jacket_detected) {
            announce("safety_jacket", "Security jacket detected");
          }

          // Announce detected objects
          if (Array.isArray(data.objects)) {
            for (const obj of data.objects) {
              announce(`obj_${obj}`, `${obj} detected`);
            }
          }

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
