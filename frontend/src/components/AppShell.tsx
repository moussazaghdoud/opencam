"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Shield,
  Search,
  Bell,
  Settings,
  LayoutDashboard,
  MonitorPlay,
  Camera,
  ScanFace,
  Activity,
  BarChart3,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  X,
  Loader2,
  Eye,
  Lightbulb,
  Cpu,
} from "lucide-react";

interface AISearchResponse {
  query: string;
  response: {
    summary: string;
    matching_event_ids: number[];
    insights: string;
    camera_focus: string;
  };
  total_events_searched: number;
  powered_by: "claude" | "keyword";
}

const NAV_SECTIONS = [
  {
    label: "MONITORING",
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/live", label: "Live View", icon: MonitorPlay },
      { href: "/cameras", label: "Cameras", icon: Camera },
    ],
  },
  {
    label: "INTELLIGENCE",
    items: [
      { href: "/faces", label: "Face Recognition", icon: ScanFace },
      { href: "/operations", label: "Operations", icon: Activity },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    label: "MANAGEMENT",
    items: [
      { href: "/events", label: "Events", icon: Bell },
      { href: "/alerts", label: "Alerts", icon: AlertTriangle },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const isDev = process.env.NODE_ENV === "development";

  // AI Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<AISearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  const closeSearch = useCallback(() => {
    setSearchOpen(false);
    setSearchResults(null);
  }, []);

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        closeSearch();
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [closeSearch]);

  // Close on Escape
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") closeSearch();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [closeSearch]);

  const handleSearch = async () => {
    const q = searchQuery.trim();
    if (!q) return;
    setSearchLoading(true);
    setSearchOpen(true);
    setSearchResults(null);
    try {
      const apiBase =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(
        `${apiBase}/api/ops/search?q=${encodeURIComponent(q)}`
      );
      if (!res.ok) throw new Error("Search failed");
      const data: AISearchResponse = await res.json();
      setSearchResults(data);
    } catch {
      setSearchResults({
        query: q,
        response: {
          summary: "Search failed. Please try again.",
          matching_event_ids: [],
          insights: "",
          camera_focus: "",
        },
        total_events_searched: 0,
        powered_by: "keyword",
      });
    } finally {
      setSearchLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#09090b]">
      {/* Top Navigation Bar */}
      <header className="fixed top-0 left-0 right-0 z-50 h-14 bg-[#111113] border-b border-[#27272a] flex items-center px-4 gap-4">
        {/* Left: Logo */}
        <div className="flex items-center gap-2.5 min-w-[200px]">
          <div className="w-8 h-8 bg-blue-500/10 rounded-lg flex items-center justify-center">
            <Shield className="w-4.5 h-4.5 text-blue-500" />
          </div>
          <span className="text-lg font-bold tracking-tight text-white">
            OpenCam
          </span>
          <span
            className={`ml-1 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
              isDev
                ? "bg-amber-500/15 text-amber-400 border border-amber-500/20"
                : "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
            }`}
          >
            {isDev ? "DEV" : "LIVE"}
          </span>
        </div>

        {/* Center: AI Search */}
        <div className="flex-1 flex justify-center">
          <div className="relative w-full max-w-md" ref={searchRef}>
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input
              type="text"
              placeholder='AI Search — "show me all people near gate B"'
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSearch();
              }}
              className="w-full h-9 pl-9 pr-10 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all duration-200"
            />
            {searchQuery && (
              <button
                onClick={() => {
                  setSearchQuery("");
                  closeSearch();
                }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}

            {/* Search Results Dropdown */}
            {searchOpen && (
              <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 w-[600px] bg-[#18181b] border border-[#27272a] rounded-xl shadow-2xl max-h-[500px] overflow-y-auto z-[100]">
                {/* Loading State */}
                {searchLoading && (
                  <div className="flex flex-col items-center justify-center py-12 gap-3">
                    <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />
                    <p className="text-sm text-zinc-400">
                      Analyzing events with AI...
                    </p>
                    <div className="flex gap-1">
                      <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
                      <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse [animation-delay:150ms]" />
                      <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse [animation-delay:300ms]" />
                    </div>
                  </div>
                )}

                {/* Results */}
                {searchResults && !searchLoading && (
                  <div className="p-4 space-y-4">
                    {/* AI Summary */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-blue-400" />
                        <h3 className="text-sm font-semibold text-blue-400">
                          AI Analysis
                        </h3>
                      </div>
                      <p className="text-sm text-zinc-300 leading-relaxed bg-[#111113] rounded-lg p-3 border border-[#27272a]">
                        {searchResults.response.summary}
                      </p>
                    </div>

                    {/* Matching Events */}
                    {searchResults.response.matching_event_ids.length > 0 && (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <Eye className="w-4 h-4 text-emerald-400" />
                          <h3 className="text-sm font-semibold text-emerald-400">
                            Matching Events
                          </h3>
                          <span className="ml-auto text-xs text-zinc-500">
                            {searchResults.response.matching_event_ids.length} found
                          </span>
                        </div>
                        <div className="bg-[#111113] rounded-lg border border-[#27272a] divide-y divide-[#27272a] max-h-[200px] overflow-y-auto">
                          {searchResults.response.matching_event_ids
                            .slice(0, 20)
                            .map((id) => (
                              <div
                                key={id}
                                className="flex items-center gap-3 px-3 py-2 hover:bg-[#1a1a1e] transition-colors cursor-pointer"
                              >
                                <span className="px-2 py-0.5 bg-blue-500/10 text-blue-400 text-[10px] font-semibold rounded uppercase">
                                  Event
                                </span>
                                <span className="text-sm text-zinc-300">
                                  Event #{id}
                                </span>
                                <Link
                                  href="/events"
                                  className="ml-auto text-xs text-zinc-500 hover:text-blue-400 transition-colors"
                                  onClick={closeSearch}
                                >
                                  View
                                </Link>
                              </div>
                            ))}
                        </div>
                        {searchResults.response.matching_event_ids.length > 20 && (
                          <p className="text-xs text-zinc-500 text-center">
                            +{searchResults.response.matching_event_ids.length - 20} more events
                          </p>
                        )}
                      </div>
                    )}

                    {/* Insights */}
                    {searchResults.response.insights && (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <Lightbulb className="w-4 h-4 text-amber-400" />
                          <h3 className="text-sm font-semibold text-amber-400">
                            Insights
                          </h3>
                        </div>
                        <p className="text-sm text-zinc-400 bg-[#111113] rounded-lg p-3 border border-[#27272a]">
                          {searchResults.response.insights}
                        </p>
                      </div>
                    )}

                    {/* Camera Focus */}
                    {searchResults.response.camera_focus && (
                      <div className="flex items-center gap-2 text-xs text-zinc-500">
                        <Camera className="w-3.5 h-3.5" />
                        <span>Focus: {searchResults.response.camera_focus}</span>
                      </div>
                    )}

                    {/* Footer */}
                    <div className="flex items-center justify-between pt-2 border-t border-[#27272a]">
                      <div className="flex items-center gap-1.5 text-[11px] text-zinc-600">
                        <Cpu className="w-3 h-3" />
                        <span>
                          {searchResults.powered_by === "claude"
                            ? "Powered by Claude AI"
                            : "Keyword search"}
                        </span>
                      </div>
                      <span className="text-[11px] text-zinc-600">
                        {searchResults.total_events_searched} events searched
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-1 min-w-[200px] justify-end">
          <button className="relative p-2 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-[#1a1a1e] transition-all duration-200">
            <Bell className="w-5 h-5" />
            <span className="absolute top-1.5 right-1.5 w-4 h-4 bg-red-500 rounded-full text-[10px] font-bold text-white flex items-center justify-center">
              3
            </span>
          </button>
          <Link
            href="/settings"
            className="p-2 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-[#1a1a1e] transition-all duration-200"
          >
            <Settings className="w-5 h-5" />
          </Link>
          <div className="ml-2 w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-xs font-bold text-white cursor-pointer hover:bg-blue-400 transition-all duration-200">
            MZ
          </div>
        </div>
      </header>

      {/* Body below topbar */}
      <div className="flex flex-1 pt-14 overflow-hidden">
        {/* Left Sidebar */}
        <aside
          className={`${
            sidebarCollapsed ? "w-16" : "w-64"
          } bg-[#111113] border-r border-[#27272a] flex flex-col transition-all duration-300 overflow-hidden flex-shrink-0`}
        >
          {/* Collapse toggle */}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="absolute bottom-20 left-0 z-10 w-5 h-10 bg-[#111113] border border-[#27272a] border-l-0 rounded-r-md flex items-center justify-center text-zinc-500 hover:text-zinc-300 transition-all duration-200"
            style={{
              left: sidebarCollapsed ? "64px" : "256px",
            }}
          >
            {sidebarCollapsed ? (
              <ChevronRight className="w-3 h-3" />
            ) : (
              <ChevronLeft className="w-3 h-3" />
            )}
          </button>

          {/* Nav sections */}
          <nav className="flex-1 py-4 overflow-y-auto overflow-x-hidden">
            {NAV_SECTIONS.map((section) => (
              <div key={section.label} className="mb-6">
                {!sidebarCollapsed && (
                  <div className="text-[10px] text-zinc-500 uppercase tracking-widest px-4 mb-2 font-medium">
                    {section.label}
                  </div>
                )}
                <div className="space-y-0.5 px-2">
                  {section.items.map(({ href, label, icon: Icon }) => {
                    const active =
                      pathname === href ||
                      (href !== "/" && pathname.startsWith(href));
                    return (
                      <Link
                        key={href}
                        href={href}
                        className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-200 group relative ${
                          active
                            ? "bg-blue-500/10 text-blue-400 border-l-2 border-blue-500 ml-0 pl-2.5"
                            : "text-zinc-400 hover:bg-[#1a1a1e] hover:text-zinc-200 border-l-2 border-transparent ml-0 pl-2.5"
                        }`}
                        title={sidebarCollapsed ? label : undefined}
                      >
                        <Icon
                          className={`w-4 h-4 flex-shrink-0 ${
                            active ? "text-blue-400" : "text-zinc-500 group-hover:text-zinc-300"
                          } transition-colors duration-200`}
                        />
                        {!sidebarCollapsed && (
                          <span className="truncate">{label}</span>
                        )}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* Bottom status bar */}
          {!sidebarCollapsed && (
            <div className="p-4 border-t border-[#27272a]">
              <div className="flex items-center gap-2 mb-1.5">
                <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                <span className="text-xs text-zinc-400">5 cameras online</span>
              </div>
              <div className="text-[11px] text-zinc-600">System healthy</div>
            </div>
          )}
          {sidebarCollapsed && (
            <div className="p-2 border-t border-[#27272a] flex justify-center">
              <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            </div>
          )}
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-auto bg-[#09090b] p-6">{children}</main>
      </div>
    </div>
  );
}
