/**
 * AI Enrichment API client — separate from core api.ts to keep isolation.
 * All functions handle errors gracefully and return null on failure,
 * so the UI can render normally without AI data.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AIEnrichment {
  event_id: number;
  narration: string;
  suspicion_score: number;
  suspicion_label: "normal" | "noteworthy" | "unusual" | "suspicious";
  suspicion_reason: string | null;
  powered_by: "claude" | "rules";
}

export interface AIStatus {
  enabled: boolean;
  mode: "claude" | "rules";
  feature: string;
}

/** Check if AI narrator is enabled. Returns null on error. */
export async function getAIStatus(): Promise<AIStatus | null> {
  try {
    const res = await fetch(`${API_BASE}/api/ai/status`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/** Get cached enrichment (no LLM call). Returns null if not yet enriched or disabled. */
export async function getEnrichment(eventId: number): Promise<AIEnrichment | null> {
  try {
    const res = await fetch(`${API_BASE}/api/ai/enrichment/${eventId}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/** Trigger enrichment for an event (may call LLM). Returns null on failure. */
export async function enrichEvent(eventId: number, force = false): Promise<AIEnrichment | null> {
  try {
    const url = `${API_BASE}/api/ai/enrich/${eventId}${force ? "?force=true" : ""}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
