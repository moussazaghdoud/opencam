"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Settings,
  Server,
  Cpu,
  Mail,
  Shield,
  Eye,
  AlertTriangle,
  Volume2,
  Search,
  Check,
  X,
  Loader2,
  Plus,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DetectionPrefs {
  enabled: string[];
  high_alert: string[];
  announce: string[];
}

export default function SettingsPage() {
  const [apiUrl] = useState(API);
  const [prefs, setPrefs] = useState<DetectionPrefs | null>(null);
  const [allClasses, setAllClasses] = useState<string[]>([]);
  const [objEnabled, setObjEnabled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);

  const fetchPrefs = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/ai/detection-prefs`);
      if (res.ok) {
        const data = await res.json();
        setPrefs(data.prefs);
        setAllClasses(data.available_classes);
        setObjEnabled(data.object_identification_enabled);
      }
    } catch {}
  }, []);

  useEffect(() => {
    fetchPrefs();
  }, [fetchPrefs]);

  const savePrefs = async (updated: DetectionPrefs) => {
    setSaving(true);
    try {
      await fetch(`${API}/api/ai/detection-prefs`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated),
      });
      setPrefs(updated);
    } catch {}
    setSaving(false);
  };

  const toggleEnabled = (label: string) => {
    if (!prefs) return;
    const updated = { ...prefs };
    if (updated.enabled.includes(label)) {
      updated.enabled = updated.enabled.filter((l) => l !== label);
      updated.announce = updated.announce.filter((l) => l !== label);
      updated.high_alert = updated.high_alert.filter((l) => l !== label);
    } else {
      updated.enabled = [...updated.enabled, label];
    }
    savePrefs(updated);
  };

  const toggleAnnounce = (label: string) => {
    if (!prefs) return;
    const updated = { ...prefs };
    if (updated.announce.includes(label)) {
      updated.announce = updated.announce.filter((l) => l !== label);
    } else {
      updated.announce = [...updated.announce, label];
      if (!updated.enabled.includes(label)) {
        updated.enabled = [...updated.enabled, label];
      }
    }
    savePrefs(updated);
  };

  const toggleHighAlert = (label: string) => {
    if (!prefs) return;
    const updated = { ...prefs };
    if (updated.high_alert.includes(label)) {
      updated.high_alert = updated.high_alert.filter((l) => l !== label);
    } else {
      updated.high_alert = [...updated.high_alert, label];
      if (!updated.enabled.includes(label)) {
        updated.enabled = [...updated.enabled, label];
      }
    }
    savePrefs(updated);
  };

  const addObject = (label: string) => {
    if (!prefs) return;
    const updated = { ...prefs };
    if (!updated.enabled.includes(label)) {
      updated.enabled = [...updated.enabled, label];
      updated.announce = [...updated.announce, label];
    }
    savePrefs(updated);
    setShowAddModal(false);
    setSearchQuery("");
  };

  const filteredAvailable = allClasses.filter(
    (c) =>
      !prefs?.enabled.includes(c) &&
      c.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-full">
      <div className="flex items-center gap-3 mb-8">
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        {saving && <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />}
      </div>

      <div className="max-w-3xl space-y-6">
        {/* Object Detection Configuration */}
        {objEnabled && prefs && (
          <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold flex items-center gap-2 text-white">
                <Eye className="w-4 h-4 text-cyan-400" />
                Object Detection (601 classes available)
              </h3>
              <button
                onClick={() => setShowAddModal(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-xs font-medium transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Object
              </button>
            </div>

            <p className="text-xs text-zinc-500 mb-4">
              Choose which objects to detect, announce by voice, or flag as high-alert.
            </p>

            {/* Column headers */}
            <div className="flex items-center gap-3 px-3 py-2 text-[10px] text-zinc-600 uppercase tracking-wider font-medium border-b border-[#27272a]">
              <div className="flex-1">Object</div>
              <div className="w-16 text-center">Detect</div>
              <div className="w-16 text-center">Announce</div>
              <div className="w-16 text-center">Alert</div>
            </div>

            <div className="max-h-[400px] overflow-y-auto divide-y divide-[#27272a]">
              {prefs.enabled.sort().map((label) => (
                <div
                  key={label}
                  className="flex items-center gap-3 px-3 py-2.5 hover:bg-[#1f1f23] transition-colors group"
                >
                  <div className="flex-1 text-sm text-zinc-300">{label}</div>

                  {/* Detect toggle */}
                  <div className="w-16 flex justify-center">
                    <button
                      onClick={() => toggleEnabled(label)}
                      className={`w-8 h-5 rounded-full transition-colors ${
                        prefs.enabled.includes(label)
                          ? "bg-blue-600"
                          : "bg-[#27272a]"
                      }`}
                    >
                      <div
                        className={`w-3.5 h-3.5 rounded-full bg-white transition-transform mx-0.5 ${
                          prefs.enabled.includes(label)
                            ? "translate-x-3"
                            : "translate-x-0"
                        }`}
                      />
                    </button>
                  </div>

                  {/* Announce toggle */}
                  <div className="w-16 flex justify-center">
                    <button
                      onClick={() => toggleAnnounce(label)}
                      className={`p-1 rounded transition-colors ${
                        prefs.announce.includes(label)
                          ? "text-cyan-400 bg-cyan-500/10"
                          : "text-zinc-600 hover:text-zinc-400"
                      }`}
                      title={prefs.announce.includes(label) ? "Will announce by voice" : "Click to enable voice announcement"}
                    >
                      <Volume2 className="w-4 h-4" />
                    </button>
                  </div>

                  {/* High alert toggle */}
                  <div className="w-16 flex justify-center">
                    <button
                      onClick={() => toggleHighAlert(label)}
                      className={`p-1 rounded transition-colors ${
                        prefs.high_alert.includes(label)
                          ? "text-red-400 bg-red-500/10"
                          : "text-zinc-600 hover:text-zinc-400"
                      }`}
                      title={prefs.high_alert.includes(label) ? "High alert — will boost suspicion score" : "Click to mark as high-alert"}
                    >
                      <AlertTriangle className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#27272a]">
              <span className="text-[11px] text-zinc-600">
                {prefs.enabled.length} detected · {prefs.announce.length} announced · {prefs.high_alert.length} high-alert
              </span>
            </div>
          </div>
        )}

        {/* Add Object Modal */}
        {showAddModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="bg-[#18181b] border border-[#27272a] rounded-xl w-[480px] max-h-[70vh] flex flex-col">
              <div className="flex items-center justify-between px-4 py-3 border-b border-[#27272a]">
                <h3 className="text-sm font-semibold text-white">Add Object to Detection</h3>
                <button onClick={() => { setShowAddModal(false); setSearchQuery(""); }} className="text-zinc-500 hover:text-white">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="px-4 py-3 border-b border-[#27272a]">
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 w-4 h-4 text-zinc-500" />
                  <input
                    type="text"
                    placeholder="Search 601 object classes..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    autoFocus
                    className="w-full pl-9 pr-3 py-2 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-blue-500/50"
                  />
                </div>
              </div>
              <div className="flex-1 overflow-y-auto px-2 py-2">
                {filteredAvailable.slice(0, 50).map((label) => (
                  <button
                    key={label}
                    onClick={() => addObject(label)}
                    className="w-full flex items-center justify-between px-3 py-2 text-sm text-zinc-300 hover:bg-[#27272a] rounded-lg transition-colors"
                  >
                    <span>{label}</span>
                    <Plus className="w-3.5 h-3.5 text-zinc-600" />
                  </button>
                ))}
                {filteredAvailable.length === 0 && searchQuery && (
                  <p className="text-center text-xs text-zinc-600 py-4">No matching objects found</p>
                )}
                {filteredAvailable.length > 50 && (
                  <p className="text-center text-xs text-zinc-600 py-2">
                    Showing first 50 of {filteredAvailable.length} results — refine your search
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {!objEnabled && (
          <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-6">
            <h3 className="font-semibold flex items-center gap-2 text-white mb-2">
              <Eye className="w-4 h-4 text-cyan-400" />
              Object Detection
            </h3>
            <p className="text-sm text-zinc-500">
              Object identification is disabled. Set <code className="text-blue-400">OPENCAM_ENABLE_OBJECT_IDENTIFICATION=true</code> to enable.
            </p>
          </div>
        )}

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
              { key: "OPENCAM_ENABLE_OBJECT_IDENTIFICATION", value: objEnabled ? "true" : "false" },
              { key: "OPENCAM_ENABLE_AI_NARRATOR", value: "env" },
              { key: "OPENCAM_ENABLE_CLIP_RECORDING", value: "env" },
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
              { key: "AI Engines", value: "YOLOv8n (COCO) + YOLOv8n (Open Images) + ArcFace" },
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
