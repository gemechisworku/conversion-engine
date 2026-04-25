"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { orchestrationFetch, OrchestrationApiError } from "@/lib/api";
import type { EvidenceEdge, LeadStatePayload, ResponseEnvelope } from "@/lib/types";

type EvidenceResponse = { edges: EvidenceEdge[] };

function humanStage(stage: string): string {
  const mapping: Record<string, string> = {
    new_lead: "New lead",
    enriching: "Enrichment in progress",
    brief_ready: "Briefs ready",
    drafting: "Drafting outreach",
    in_review: "Under review",
    queued_to_send: "Queued to send",
    awaiting_reply: "Awaiting reply",
    reply_received: "Reply received",
    qualifying: "Qualifying",
    scheduling: "Scheduling",
    booked: "Booked",
    nurture: "Nurture",
    handoff_required: "Human handoff required",
    disqualified: "Disqualified",
    closed: "Closed",
  };
  return mapping[stage] || stage;
}

function humanEdge(edgeType: string): string {
  const mapping: Record<string, string> = {
    "brief.hiring_signal": "Hiring signal brief saved",
    "brief.competitor_gap": "Competitor gap brief saved",
    "score.ai_maturity": "AI maturity score saved",
    "outreach.grounded_claim": "Grounded outreach claim",
  };
  return mapping[edgeType] || edgeType;
}

function summarizePayload(payload: Record<string, unknown>): string {
  const claim = typeof payload.claim === "string" ? payload.claim : "";
  if (claim) return claim;
  const kind = typeof payload.kind === "string" ? payload.kind : "";
  if (kind) return `Type: ${kind}`;
  const scoreId = typeof payload.score_id === "string" ? payload.score_id : "";
  if (scoreId) return `Score id: ${scoreId}`;
  const briefId = typeof payload.brief_id === "string" ? payload.brief_id : "";
  if (briefId) return `Brief id: ${briefId}`;
  const gapId = typeof payload.gap_brief_id === "string" ? payload.gap_brief_id : "";
  if (gapId) return `Gap brief id: ${gapId}`;
  return "Evidence linked to this lead.";
}

export function LeadDetail({ leadId }: { leadId: string }) {
  const [state, setState] = useState<ResponseEnvelope<LeadStatePayload> | null>(null);
  const [evidence, setEvidence] = useState<EvidenceEdge[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const s = await orchestrationFetch<LeadStatePayload>(`/lead/${encodeURIComponent(leadId)}/state`);
      setState(s);
      if (s.status !== "success") {
        setEvidence([]);
        return;
      }
      const e = await orchestrationFetch<EvidenceResponse>(
        `/memory/evidence/${encodeURIComponent(leadId)}?limit=100`,
      );
      setEvidence(e.status === "success" && Array.isArray(e.data.edges) ? e.data.edges : []);
    } catch (err) {
      setState(null);
      setEvidence(null);
      setError(err instanceof OrchestrationApiError ? err.message : "Failed to load lead");
    } finally {
      setLoading(false);
    }
  }, [leadId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-muted">Loading lead…</p>;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
        {error}
        <button type="button" className="ml-3 underline" onClick={() => void load()}>
          Retry
        </button>
      </div>
    );
  }

  if (!state || state.status !== "success" || !state.data) {
    return (
      <p className="text-muted">
        {state?.error?.error_message || "Lead not found or API returned non-success."}{" "}
        <button type="button" className="text-primary underline" onClick={() => void load()}>
          Retry
        </button>
      </p>
    );
  }

  const d = state.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{d.lead_id}</h1>
          <p className="text-sm text-muted">
            Trace <code className="rounded bg-background px-1">{state.trace_id}</code>
          </p>
        </div>
        <Link href="/pipeline" className="text-sm font-medium text-primary hover:underline">
          ← Pipeline
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border border-border bg-surface p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-foreground">State</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Stage</dt>
              <dd className="font-medium text-foreground">{humanStage(d.state)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Segment</dt>
              <dd className="text-right text-foreground">{d.segment ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Segment confidence</dt>
              <dd className="text-foreground">
                {typeof d.segment_confidence === "number" ? `${Math.round(d.segment_confidence * 100)}%` : "—"}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted">AI maturity</dt>
              <dd className="text-foreground">{d.ai_maturity_score ?? "—"}</dd>
            </div>
          </dl>
        </section>

        <section className="rounded-lg border border-border bg-surface p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-foreground">Actions</h2>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-3 rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground hover:bg-background"
          >
            Refresh
          </button>
        </section>
      </div>

      <section className="rounded-lg border border-border bg-surface p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-foreground">Evidence graph (recent)</h2>
        {evidence && evidence.length > 0 ? (
          <ul className="mt-3 max-h-80 space-y-2 overflow-y-auto text-sm">
            {evidence.map((row) => (
              <li key={row.id} className="rounded-md border border-border bg-background px-3 py-2">
                <p className="font-medium text-foreground">{humanEdge(row.edge_type)}</p>
                <p className="mt-1 text-xs text-muted">{summarizePayload(row.payload)}</p>
                <p className="mt-1 text-[11px] text-muted">
                  {row.brief_id ? `Brief: ${row.brief_id} · ` : ""}
                  {new Date(row.created_at).toLocaleString()}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted">No edges stored yet, or evidence endpoint unavailable.</p>
        )}
      </section>
    </div>
  );
}
