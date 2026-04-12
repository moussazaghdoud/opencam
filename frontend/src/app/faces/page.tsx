"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import {
  Plus,
  Trash2,
  Camera,
  Upload,
  ScanFace,
  Shield,
  UserCheck,
  UserX,
  User,
  ChevronDown,
} from "lucide-react";
import CameraFeed from "@/components/CameraFeed";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface KnownFace {
  id: number;
  name: string;
  role: string;
  photo_path: string;
  created_at: string;
}

interface RecognitionResult {
  name: string;
  role: string;
  known: boolean;
  confidence: number;
  lbph_distance?: number;
  bbox: number[];
}

interface CameraItem {
  id: number;
  name: string;
  status: string;
}

const roleColors: Record<string, string> = {
  admin: "bg-purple-500/15 text-purple-400 border border-purple-500/20",
  employee: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20",
  vip: "bg-amber-500/15 text-amber-400 border border-amber-500/20",
  visitor: "bg-blue-500/15 text-blue-400 border border-blue-500/20",
  blocked: "bg-red-500/15 text-red-400 border border-red-500/20",
};

export default function FacesPage() {
  const [faces, setFaces] = useState<KnownFace[]>([]);
  const [cameras, setCameras] = useState<CameraItem[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [formName, setFormName] = useState("");
  const [formRole, setFormRole] = useState("");
  const [formMode, setFormMode] = useState<"capture" | "upload">("capture");
  const [formCameraId, setFormCameraId] = useState<number | null>(null);
  const [formFile, setFormFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [captureProgress, setCaptureProgress] = useState(0);
  const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [recognizing, setRecognizing] = useState(false);
  const [registrationQuality, setRegistrationQuality] = useState<{
    quality: string;
    embeddings_generated: number;
    faces_detected: number;
    total_frames: number;
    angles_covered: string[];
  } | null>(null);
  const [recognitionResults, setRecognitionResults] = useState<
    RecognitionResult[]
  >([]);
  const [recognitionCameraId, setRecognitionCameraId] = useState<number | null>(
    null
  );
  const [hoveredFace, setHoveredFace] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchFaces = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/faces/`);
      setFaces(await res.json());
    } catch {
      /* backend offline */
    }
  }, []);

  const fetchCameras = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/cameras/`);
      const cams = await res.json();
      setCameras(cams);
      const online = cams.filter((c: CameraItem) => c.status === "online");
      if (online.length > 0) {
        if (!formCameraId) setFormCameraId(online[0].id);
        if (!recognitionCameraId) setRecognitionCameraId(online[0].id);
      }
    } catch {
      /* backend offline */
    }
  }, [formCameraId, recognitionCameraId]);

  useEffect(() => {
    fetchFaces();
    fetchCameras();
    const interval = setInterval(fetchFaces, 5000);
    return () => clearInterval(interval);
  }, [fetchFaces, fetchCameras]);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName || submitting) return;

    const formData = new FormData();
    formData.append("name", formName);
    formData.append("role", formRole);

    if (formMode === "upload" && formFile) {
      formData.append("photo", formFile);
    } else if (formMode === "capture" && formCameraId) {
      formData.append("camera_id", String(formCameraId));
    } else {
      return;
    }

    setSubmitting(true);
    setCaptureProgress(0);

    setRegistrationQuality(null);

    // Animate progress bar during camera capture (~6s for 30 frames)
    if (formMode === "capture") {
      let progress = 0;
      captureIntervalRef.current = setInterval(() => {
        progress += 100 / 30; // 30 steps over 6s
        setCaptureProgress(Math.min(progress, 92));
      }, 200);
    }

    try {
      const res = await fetch(`${API}/api/faces/register`, {
        method: "POST",
        body: formData,
      });
      if (captureIntervalRef.current) {
        clearInterval(captureIntervalRef.current);
        captureIntervalRef.current = null;
      }
      setCaptureProgress(100);
      if (res.ok) {
        const data = await res.json();
        if (data.quality) {
          setRegistrationQuality(data.quality);
        }
        setTimeout(() => {
          setFormName("");
          setFormRole("");
          setFormFile(null);
          setCaptureProgress(0);
          if (!data.quality || data.quality.quality !== "poor") {
            setShowAdd(false);
            setRegistrationQuality(null);
          }
          fetchFaces();
        }, data.quality ? 3000 : 400);
      }
    } catch {
      if (captureIntervalRef.current) {
        clearInterval(captureIntervalRef.current);
        captureIntervalRef.current = null;
      }
      setCaptureProgress(0);
    }
    setSubmitting(false);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Remove this face?")) return;
    try {
      await fetch(`${API}/api/faces/${id}`, { method: "DELETE" });
      fetchFaces();
    } catch {
      /* error */
    }
  };

  const handleRecognize = async () => {
    if (!recognitionCameraId) return;
    setRecognizing(true);
    try {
      const res = await fetch(
        `${API}/api/faces/recognize?camera_id=${recognitionCameraId}`,
        { method: "POST" }
      );
      const data = await res.json();
      setRecognitionResults(data.faces || []);
    } catch {
      setRecognitionResults([]);
    }
    setRecognizing(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith("image/")) {
      setFormFile(file);
    }
  };

  const onlineCameras = cameras.filter((c) => c.status === "online");

  return (
    <div className="min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white">Face Recognition</h1>
          <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-500/15 text-zinc-400">
            {faces.length} registered
          </span>
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-all duration-200"
        >
          <Plus className="w-4 h-4" />
          Register Face
        </button>
      </div>

      {/* Register Face Panel */}
      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          showAdd ? "max-h-[1000px] opacity-100 mb-6" : "max-h-0 opacity-0 mb-0"
        }`}
      >
        <form
          onSubmit={handleRegister}
          className="bg-[#18181b] border border-[#27272a] rounded-xl p-6"
        >
          <h3 className="text-base font-semibold mb-5 text-white">
            Register New Face
          </h3>

          {/* Mode Toggle */}
          <div className="flex gap-1 p-1 bg-[#09090b] rounded-lg w-fit mb-5">
            <button
              type="button"
              onClick={() => setFormMode("capture")}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 ${
                formMode === "capture"
                  ? "bg-blue-600 text-white"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <Camera className="w-3.5 h-3.5" />
              Camera Capture
            </button>
            <button
              type="button"
              onClick={() => setFormMode("upload")}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 ${
                formMode === "upload"
                  ? "bg-blue-600 text-white"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <Upload className="w-3.5 h-3.5" />
              Upload Photo
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-5">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Name
              </label>
              <input
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="John Doe"
                required
                className="w-full px-3 py-2.5 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white placeholder:text-zinc-600 focus:border-blue-500 focus:outline-none transition-all duration-200"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Role
              </label>
              <div className="relative">
                <select
                  value={formRole}
                  onChange={(e) => setFormRole(e.target.value)}
                  className="appearance-none w-full px-3 py-2.5 pr-8 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white focus:border-blue-500 focus:outline-none transition-all duration-200 cursor-pointer"
                >
                  <option value="">Select role</option>
                  <option value="admin">Admin</option>
                  <option value="employee">Employee</option>
                  <option value="vip">VIP</option>
                  <option value="visitor">Visitor</option>
                  <option value="blocked">Blocked</option>
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-zinc-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>
          </div>

          {formMode === "capture" && (
            <div className="mb-5">
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Camera
              </label>
              <div className="relative mb-3">
                <select
                  value={formCameraId || ""}
                  onChange={(e) => setFormCameraId(Number(e.target.value))}
                  className="appearance-none w-full px-3 py-2.5 pr-8 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white focus:border-blue-500 focus:outline-none transition-all duration-200 cursor-pointer"
                >
                  {onlineCameras.map((cam) => (
                    <option key={cam.id} value={cam.id}>
                      {cam.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-zinc-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>

              {/* Live preview during registration — compact size */}
              {formCameraId && (() => {
                const cam = cameras.find((c) => c.id === formCameraId);
                return cam ? (
                  <div className="rounded-lg overflow-hidden border border-[#27272a] w-[40%]">
                    <CameraFeed cameraId={cam.id} cameraName={cam.name} />
                  </div>
                ) : null;
              })()}
              <p className="text-[11px] text-zinc-500 mt-2">
                Position yourself so your face is clearly visible, then click Register Face
              </p>
            </div>
          )}

          {formMode === "upload" && (
            <div className="mb-5">
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Photo
              </label>
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-lg cursor-pointer transition-all duration-200 ${
                  dragOver
                    ? "border-blue-500 bg-blue-500/5"
                    : formFile
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-[#27272a] hover:border-[#333] bg-[#09090b]"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={(e) => setFormFile(e.target.files?.[0] || null)}
                  className="hidden"
                />
                {formFile ? (
                  <div className="text-center">
                    <Upload className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
                    <span className="text-sm text-emerald-400">
                      {formFile.name}
                    </span>
                    <p className="text-[11px] text-zinc-600 mt-1">
                      Click to change
                    </p>
                  </div>
                ) : (
                  <div className="text-center">
                    <Upload className="w-8 h-8 text-zinc-600 mx-auto mb-2" />
                    <span className="text-sm text-zinc-400">
                      Drop image here or click to browse
                    </span>
                    <p className="text-[11px] text-zinc-600 mt-1">
                      PNG, JPG up to 10MB
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-all duration-200"
            >
              {submitting ? "Capturing..." : "Register Face"}
            </button>
            <button
              type="button"
              onClick={() => setShowAdd(false)}
              disabled={submitting}
              className="px-5 py-2.5 bg-[#27272a] hover:bg-[#333] disabled:opacity-50 rounded-lg text-sm transition-all duration-200"
            >
              Cancel
            </button>
          </div>

          {/* Capture progress bar */}
          {submitting && formMode === "capture" && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs text-zinc-400">Capturing multi-angle frames…</span>
                <span className="text-xs text-zinc-500">{Math.round(captureProgress)}%</span>
              </div>
              <div className="h-1.5 bg-[#27272a] rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all duration-100"
                  style={{ width: `${captureProgress}%` }}
                />
              </div>
              <p className="text-[11px] text-zinc-600 mt-1.5">
                {captureProgress < 30
                  ? "Look at the camera — capturing frontal view..."
                  : captureProgress < 60
                  ? "Slowly turn your head left and right..."
                  : captureProgress < 92
                  ? "Almost done — tilt your head slightly..."
                  : "Processing embeddings…"}
              </p>
            </div>
          )}

          {registrationQuality && (
            <div className={`mt-4 p-3 rounded-lg border ${
              registrationQuality.quality === "excellent"
                ? "bg-emerald-500/10 border-emerald-500/20"
                : registrationQuality.quality === "good"
                ? "bg-blue-500/10 border-blue-500/20"
                : registrationQuality.quality === "fair"
                ? "bg-amber-500/10 border-amber-500/20"
                : "bg-red-500/10 border-red-500/20"
            }`}>
              <div className="flex items-center justify-between mb-2">
                <span className={`text-xs font-bold uppercase ${
                  registrationQuality.quality === "excellent" ? "text-emerald-400"
                    : registrationQuality.quality === "good" ? "text-blue-400"
                    : registrationQuality.quality === "fair" ? "text-amber-400"
                    : "text-red-400"
                }`}>
                  Registration: {registrationQuality.quality}
                </span>
                <span className="text-xs text-zinc-500">
                  {registrationQuality.embeddings_generated} embeddings
                </span>
              </div>
              <div className="text-[11px] text-zinc-400 space-y-0.5">
                <p>Frames captured: {registrationQuality.total_frames} | Faces detected: {registrationQuality.faces_detected}</p>
                {registrationQuality.angles_covered.length > 0 && (
                  <p>Angles: {registrationQuality.angles_covered.join(", ")}</p>
                )}
                {(registrationQuality.quality === "poor" || registrationQuality.quality === "failed") && (
                  <p className="text-amber-400 mt-1">Try again with better lighting or closer to the camera.</p>
                )}
              </div>
            </div>
          )}
        </form>
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Registered Faces Grid */}
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">
            Registered Faces
          </h2>
          {faces.length > 0 ? (
            <div className="grid grid-cols-2 gap-4">
              {faces.map((face) => (
                <div
                  key={face.id}
                  className="group relative bg-[#18181b] border border-[#27272a] rounded-xl overflow-hidden hover:border-[#333] transition-all duration-200"
                  onMouseEnter={() => setHoveredFace(face.id)}
                  onMouseLeave={() => setHoveredFace(null)}
                >
                  {/* Photo */}
                  <div className="w-full aspect-square bg-[#09090b] overflow-hidden">
                    <img
                      src={`${API}/api/faces/${face.id}/photo?t=${face.created_at || face.id}`}
                      alt={face.name}
                      className="w-full h-full object-cover"
                    />
                  </div>

                  {/* Delete overlay */}
                  <div
                    className={`absolute top-2 right-2 transition-all duration-200 ${
                      hoveredFace === face.id
                        ? "opacity-100"
                        : "opacity-0"
                    }`}
                  >
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(face.id);
                      }}
                      className="p-1.5 bg-red-500/90 hover:bg-red-600 rounded-lg transition-all duration-200"
                      title="Remove"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-white" />
                    </button>
                  </div>

                  {/* Info */}
                  <div className="p-3">
                    <div className="font-medium text-sm text-white">
                      {face.name}
                    </div>
                    <div className="flex items-center gap-2 mt-1.5">
                      {face.role && (
                        <span
                          className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                            roleColors[face.role] ||
                            "bg-zinc-500/15 text-zinc-400"
                          }`}
                        >
                          {face.role}
                        </span>
                      )}
                      <span className="text-[11px] text-zinc-600">
                        {face.created_at
                          ? new Date(face.created_at).toLocaleDateString()
                          : ""}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-12 text-center">
              <User className="w-14 h-14 text-zinc-700 mx-auto mb-3" />
              <div className="text-zinc-400 font-medium">
                No faces registered
              </div>
              <div className="text-sm text-zinc-600 mt-1">
                Click &quot;Register Face&quot; to add someone
              </div>
            </div>
          )}
        </div>

        {/* Live Recognition Panel */}
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">
            Live Recognition
          </h2>
          <div className="bg-[#18181b] border border-[#27272a] rounded-xl overflow-hidden">
            {/* Camera selector + scan button */}
            <div className="p-4 border-b border-[#27272a]">
              <div className="flex items-center gap-3">
                <div className="relative flex-1">
                  <select
                    value={recognitionCameraId || ""}
                    onChange={(e) =>
                      setRecognitionCameraId(Number(e.target.value))
                    }
                    className="appearance-none w-full px-3 py-2.5 pr-8 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white focus:border-blue-500 focus:outline-none transition-all duration-200 cursor-pointer"
                  >
                    {onlineCameras.map((cam) => (
                      <option key={cam.id} value={cam.id}>
                        {cam.name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="w-3.5 h-3.5 text-zinc-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>
                <button
                  onClick={handleRecognize}
                  disabled={recognizing || !recognitionCameraId}
                  className="flex items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-all duration-200"
                >
                  <ScanFace className="w-4 h-4" />
                  {recognizing ? "Scanning..." : "Scan Now"}
                </button>
              </div>
            </div>

            {/* Live feed */}
            {recognitionCameraId && (
              <div className={`relative ${recognizing ? "ring-2 ring-emerald-500/50" : ""}`}>
                {(() => {
                  const cam = cameras.find((c) => c.id === recognitionCameraId);
                  return cam ? (
                    <CameraFeed cameraId={cam.id} cameraName={cam.name} />
                  ) : null;
                })()}
                {recognizing && (
                  <div className="absolute inset-0 border-2 border-emerald-500/40 pointer-events-none animate-pulse" />
                )}
              </div>
            )}

            {/* Results */}
            {recognitionResults.length > 0 && (
              <div className="p-4">
                <div className="text-xs text-zinc-500 mb-3 font-medium">
                  {recognitionResults.length} face
                  {recognitionResults.length > 1 ? "s" : ""} detected
                </div>
                <div className="space-y-2">
                  {recognitionResults.map((face, idx) => (
                    <div
                      key={idx}
                      className={`flex items-center gap-3 p-3.5 rounded-xl transition-all duration-200 ${
                        face.known
                          ? "bg-emerald-500/5 border border-emerald-500/20"
                          : "bg-red-500/5 border border-red-500/20"
                      }`}
                    >
                      {face.known ? (
                        <UserCheck className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                      ) : (
                        <UserX className="w-5 h-5 text-red-400 flex-shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm text-white">
                          {face.known ? face.name : "Unknown Person"}
                        </div>
                        {face.known ? (
                          <div className="flex items-center gap-2 mt-1">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                                roleColors[face.role] ||
                                "bg-zinc-500/15 text-zinc-400"
                              }`}
                            >
                              {face.role}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <div className="w-12 h-1 bg-[#27272a] rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-emerald-500 rounded-full"
                                  style={{
                                    width: `${face.confidence * 100}%`,
                                  }}
                                />
                              </div>
                              <span className="text-[11px] text-zinc-500">
                                {(face.confidence * 100).toFixed(0)}%
                              </span>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 mt-1">
                            <div className="w-12 h-1 bg-[#27272a] rounded-full overflow-hidden">
                              <div
                                className="h-full bg-red-500 rounded-full"
                                style={{
                                  width: `${face.confidence * 100}%`,
                                }}
                              />
                            </div>
                            <span className="text-[11px] text-zinc-500">
                              {(face.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        )}
                      </div>
                      {face.role === "blocked" && (
                        <Shield className="w-5 h-5 text-red-500 flex-shrink-0" />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Empty state — only shown when no camera selected */}
            {!recognitionCameraId && (
              <div className="p-12 text-center">
                <ScanFace className="w-12 h-12 text-zinc-700 mx-auto mb-3" />
                <div className="text-zinc-400 font-medium text-sm">
                  Select a camera and click Scan Now
                </div>
                <div className="text-zinc-600 text-xs mt-1">
                  The system will detect and identify faces in view
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
