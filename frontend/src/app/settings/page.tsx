"use client";

import { useState } from "react";
import { Settings, Server, Cpu, Mail, Shield } from "lucide-react";

export default function SettingsPage() {
  const [apiUrl] = useState(
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  );

  return (
    <div className="min-h-full">
      <div className="flex items-center gap-3 mb-8">
        <h1 className="text-2xl font-bold text-white">Settings</h1>
      </div>

      <div className="max-w-2xl space-y-6">
        {/* API Connection */}
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2 text-white">
            <Server className="w-4 h-4 text-blue-400" />
            Backend Connection
          </h3>
          <div className="mb-4">
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">
              API URL
            </label>
            <input
              type="text"
              value={apiUrl}
              readOnly
              className="w-full px-3 py-2.5 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-zinc-300 focus:outline-none"
            />
            <p className="text-[11px] text-zinc-600 mt-1.5">
              Set NEXT_PUBLIC_API_URL in .env.local to change the backend URL
            </p>
          </div>
        </div>

        {/* Detection Settings */}
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2 text-white">
            <Cpu className="w-4 h-4 text-purple-400" />
            Detection Settings
          </h3>
          <p className="text-sm text-zinc-500 mb-4">
            Detection settings are configured on the backend via environment
            variables:
          </p>
          <div className="space-y-0">
            {[
              { key: "OPENCAM_YOLO_MODEL", value: "yolov8n.pt" },
              { key: "OPENCAM_DETECTION_CONFIDENCE", value: "0.5" },
              { key: "OPENCAM_FRAME_SKIP", value: "3" },
              { key: "OPENCAM_MAX_CAMERAS", value: "16" },
            ].map((item, i, arr) => (
              <div
                key={item.key}
                className={`flex justify-between items-center py-3 ${
                  i < arr.length - 1 ? "border-b border-[#27272a]" : ""
                }`}
              >
                <code className="text-xs text-blue-400 font-mono">
                  {item.key}
                </code>
                <span className="text-sm text-zinc-400">{item.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Alert Settings */}
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2 text-white">
            <Mail className="w-4 h-4 text-amber-400" />
            Alert Configuration
          </h3>
          <p className="text-sm text-zinc-500 mb-4">
            Email alerts require SMTP configuration:
          </p>
          <div className="space-y-0">
            {[
              { key: "OPENCAM_SMTP_HOST", value: "not set", dim: true },
              { key: "OPENCAM_SMTP_PORT", value: "587", dim: false },
              { key: "OPENCAM_SMTP_USER", value: "not set", dim: true },
            ].map((item, i, arr) => (
              <div
                key={item.key}
                className={`flex justify-between items-center py-3 ${
                  i < arr.length - 1 ? "border-b border-[#27272a]" : ""
                }`}
              >
                <code className="text-xs text-blue-400 font-mono">
                  {item.key}
                </code>
                <span
                  className={`text-sm ${
                    item.dim ? "text-zinc-600" : "text-zinc-400"
                  }`}
                >
                  {item.value}
                </span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-zinc-600 mt-4">
            Webhook alerts can be configured per-rule when creating detection
            rules.
          </p>
        </div>

        {/* System Info */}
        <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2 text-white">
            <Shield className="w-4 h-4 text-emerald-400" />
            System Information
          </h3>
          <div className="space-y-0">
            {[
              { key: "Version", value: "0.1.0" },
              { key: "AI Engine", value: "YOLOv8n + ArcFace" },
              { key: "Database", value: "SQLite (dev)" },
              { key: "Framework", value: "Next.js + FastAPI" },
            ].map((item, i, arr) => (
              <div
                key={item.key}
                className={`flex justify-between items-center py-3 ${
                  i < arr.length - 1 ? "border-b border-[#27272a]" : ""
                }`}
              >
                <span className="text-sm text-zinc-500">{item.key}</span>
                <span className="text-sm text-zinc-400">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
