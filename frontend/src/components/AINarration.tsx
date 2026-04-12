"use client";

import { useEffect, useState, useCallback } from "react";
import { getAIStatus, getEnrichment, enrichEvent } from "@/lib/ai-api";
import type { AIEnrichment, AIStatus } from "@/lib/ai-api";
import { Brain, Sparkles, AlertTriangle, Shield, Eye, Loader2, RefreshCw } from "lucide-react";

const LABEL_CONFIG = {
  normal: {
    color: "emerald",
    icon: Shield,
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
    text: "text-emerald-400",
    badge: "bg-emerald-500/15",
  },
  noteworthy: {
    color: "blue",
    icon: Eye,
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
    text: "text-blue-400",
    badge: "bg-blue-500/15",
  },
  unusual: {
    color: "amber",
    icon: AlertTriangle,
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
    text: "text-amber-400",
    badge: "bg-amber-500/15",
  },
  suspicious: {
    color: "red",
    icon: AlertTriangle,
    bg: "bg-red-500/10",
    border: "border-red-500/20",
    text: "text-red-400",
    badge: "bg-red-500/15",
  },
};

interface Props {
  eventId: number;
}

export default function AINarration({ eventId }: Props) {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [enrichment, setEnrichment] = useState<AIEnrichment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [checked, setChecked] = useState(false);

  // Check if AI is enabled (once)
  useEffect(() => {
    getAIStatus().then((s) => {
      setStatus(s);
      setChecked(true);
    });
  }, []);

  // Try to load cached enrichment when event changes
  useEffect(() => {
    setEnrichment(null);
    setError(false);
    setLoading(false);
    if (!status?.enabled) return;
    getEnrichment(eventId).then((e) => {
      if (e) setEnrichment(e);
    });
  }, [eventId, status]);

  const handleAnalyze = useCallback(async (force = false) => {
    setLoading(true);
    setError(false);
    const result = await enrichEvent(eventId, force);
    if (result) {
      setEnrichment(result);
    } else {
      setError(true);
    }
    setLoading(false);
  }, [eventId]);

  // Don't render anything if AI is disabled or status unknown
  if (!checked || !status?.enabled) return null;

  // Already enriched — show results
  if (enrichment) {
    const config = LABEL_CONFIG[enrichment.suspicion_label] || LABEL_CONFIG.normal;
    const Icon = config.icon;
    const scorePct = Math.round(enrichment.suspicion_score * 100);

    return (
      <div className={`${config.bg} border ${config.border} rounded-xl p-4 mt-4`}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Brain className={`w-4 h-4 ${config.text}`} />
            <span className={`text-xs font-semibold uppercase tracking-wider ${config.text}`}>
              AI Analysis
            </span>
          </div>
          <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md ${config.badge}`}>
            <Icon className={`w-3 h-3 ${config.text}`} />
            <span className={`text-xs font-bold ${config.text}`}>
              {enrichment.suspicion_label.toUpperCase()} ({scorePct}%)
            </span>
          </div>
        </div>

        <p className="text-sm text-zinc-300 leading-relaxed mb-2">
          {enrichment.narration}
        </p>

        {enrichment.suspicion_reason && (
          <div className="mt-2 pt-2 border-t border-[#27272a]">
            <span className="text-xs text-zinc-500 font-medium">Why {enrichment.suspicion_label}: </span>
            <span className="text-xs text-zinc-400">{enrichment.suspicion_reason}</span>
          </div>
        )}

        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-zinc-600" />
            <span className="text-[10px] text-zinc-600">
              Powered by {enrichment.powered_by === "claude" ? "Claude AI" : "rule engine"}
            </span>
          </div>
          <button
            onClick={() => handleAnalyze(true)}
            disabled={loading}
            className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
            Re-analyze
          </button>
        </div>
      </div>
    );
  }

  // Not yet enriched — show analyze button
  return (
    <div className="mt-4">
      {error && (
        <p className="text-xs text-red-400 mb-2">AI analysis unavailable. Try again later.</p>
      )}
      <button
        onClick={handleAnalyze}
        disabled={loading}
        className="flex items-center gap-2 px-3 py-2 w-full justify-center rounded-lg text-sm font-medium bg-[#18181b] border border-[#27272a] text-zinc-400 hover:text-zinc-200 hover:border-[#3f3f46] transition-all duration-200 disabled:opacity-50"
      >
        {loading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Analyzing...
          </>
        ) : (
          <>
            <Brain className="w-4 h-4" />
            Analyze with AI
          </>
        )}
      </button>
    </div>
  );
}
