"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { orchestrationFetch, OrchestrationApiError } from "@/lib/api";
import type { EvidenceEdge, LeadBriefsPayload, LeadStatePayload, OutreachDetailPayload, ResponseEnvelope } from "@/lib/types";

type EvidenceResponse = { edges: EvidenceEdge[] };
type DraftPayload = { draft_id: string; subject?: string; body?: string };
type ReviewPayload = { review_id: string; status: string; final_send_ok: boolean };
type SendPayload = { message_id?: string | null; delivery_status?: string };

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
  const [briefs, setBriefs] = useState<LeadBriefsPayload["briefs"] | null>(null);
  const [outreach, setOutreach] = useState<OutreachDetailPayload | null>(null);
  const [outreachToEmail, setOutreachToEmail] = useState("");
  const [outreachMessage, setOutreachMessage] = useState<string | null>(null);
  const [outreachError, setOutreachError] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadOutreach = useCallback(async () => {
    try {
      const o = await orchestrationFetch<OutreachDetailPayload>(`/outreachs/${encodeURIComponent(leadId)}`);
      if (o.status === "success") {
        setOutreach(o.data);
        const outboundTo = typeof o.data.outbound?.to_email === "string" ? o.data.outbound.to_email : "";
        if (outboundTo) setOutreachToEmail(outboundTo);
      } else {
        setOutreach(null);
      }
    } catch {
      setOutreach(null);
    }
  }, [leadId]);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const s = await orchestrationFetch<LeadStatePayload>(`/lead/${encodeURIComponent(leadId)}/state`);
      setState(s);
      if (s.status !== "success") {
        setEvidence([]);
        setBriefs(null);
        setOutreach(null);
        return;
      }
      const [e, b] = await Promise.all([
        orchestrationFetch<EvidenceResponse>(`/memory/evidence/${encodeURIComponent(leadId)}?limit=100`),
        orchestrationFetch<LeadBriefsPayload>(`/lead/${encodeURIComponent(leadId)}/briefs`),
      ]);
      setEvidence(e.status === "success" && Array.isArray(e.data.edges) ? e.data.edges : []);
      setBriefs(b.status === "success" ? b.data.briefs : null);
      await loadOutreach();
    } catch (err) {
      setState(null);
      setEvidence(null);
      setBriefs(null);
      setOutreach(null);
      setError(err instanceof OrchestrationApiError ? err.message : "Failed to load lead");
    } finally {
      setLoading(false);
    }
  }, [leadId, loadOutreach]);

  const makeIdempotencyKey = useCallback((prefix: string) => {
    return `${prefix}:${leadId}:${Date.now().toString(36)}:${Math.random().toString(36).slice(2, 8)}`;
  }, [leadId]);

  async function onDraft() {
    setOutreachMessage(null);
    setOutreachError(null);
    setDrafting(true);
    try {
      const env = await orchestrationFetch<DraftPayload>("/outreach/draft", {
        method: "POST",
        body: JSON.stringify({
          lead_id: leadId,
          to_email: outreachToEmail || undefined,
          idempotency_key: makeIdempotencyKey("ui_outreach_draft"),
        }),
      });
      if (env.status === "success") {
        setOutreachMessage(`Draft created: ${env.data.draft_id}`);
        await loadOutreach();
      } else {
        setOutreachError(env.error?.error_message || "Draft failed.");
      }
    } catch (err) {
      setOutreachError(err instanceof OrchestrationApiError ? err.message : "Draft failed.");
    } finally {
      setDrafting(false);
    }
  }

  async function onReview() {
    setOutreachMessage(null);
    setOutreachError(null);
    const draftId = typeof outreach?.outbound?.draft_id === "string" ? outreach.outbound.draft_id : "";
    if (!draftId) {
      setOutreachError("Create a draft first.");
      return;
    }
    setReviewing(true);
    try {
      const env = await orchestrationFetch<ReviewPayload>("/outreach/review", {
        method: "POST",
        body: JSON.stringify({ lead_id: leadId, draft_id: draftId }),
      });
      if (env.status === "success") {
        setOutreachMessage(`Review complete: ${env.data.status}`);
        await loadOutreach();
      } else {
        setOutreachError(env.error?.error_message || "Review failed.");
      }
    } catch (err) {
      setOutreachError(err instanceof OrchestrationApiError ? err.message : "Review failed.");
    } finally {
      setReviewing(false);
    }
  }

  async function onSend() {
    setOutreachMessage(null);
    setOutreachError(null);
    const draftId = typeof outreach?.outbound?.draft_id === "string" ? outreach.outbound.draft_id : "";
    const reviewId = typeof outreach?.review?.review_id === "string" ? outreach.review.review_id : "";
    if (!draftId || !reviewId) {
      setOutreachError("Review the draft first so review_id is available.");
      return;
    }
    if (!confirm("Send this outreach now?")) return;
    setSending(true);
    try {
      const env = await orchestrationFetch<SendPayload>("/outreach/send", {
        method: "POST",
        body: JSON.stringify({
          lead_id: leadId,
          draft_id: draftId,
          review_id: reviewId,
          to_email: outreachToEmail || undefined,
          idempotency_key: makeIdempotencyKey("ui_outreach_send"),
        }),
      });
      if (env.status === "success") {
        setOutreachMessage(`Send result: ${env.data.delivery_status || "queued"}`);
        await loadOutreach();
      } else {
        setOutreachError(env.error?.error_message || "Send failed.");
      }
    } catch (err) {
      setOutreachError(err instanceof OrchestrationApiError ? err.message : "Send failed.");
    } finally {
      setSending(false);
    }
  }

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
  const companyTitle = d.company_name || d.company_id || "Company";
  const companySubtitle = d.company_domain || d.company_id || "";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{companyTitle}</h1>
          {companySubtitle && <p className="text-sm text-muted">{companySubtitle}</p>}
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
        <h2 className="text-sm font-semibold text-foreground">Briefs</h2>
        <p className="mt-1 text-xs text-muted">Open each brief to inspect JSON details.</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <details className="rounded-md border border-border bg-background p-3">
            <summary className="cursor-pointer text-sm font-medium text-foreground">Hiring signal brief</summary>
            <pre className="mt-2 max-h-64 overflow-auto text-xs text-muted">
              {JSON.stringify(briefs?.hiring_signal_brief || {}, null, 2)}
            </pre>
          </details>
          <details className="rounded-md border border-border bg-background p-3">
            <summary className="cursor-pointer text-sm font-medium text-foreground">Competitor gap brief</summary>
            <pre className="mt-2 max-h-64 overflow-auto text-xs text-muted">
              {JSON.stringify(briefs?.competitor_gap_brief || {}, null, 2)}
            </pre>
          </details>
          <details className="rounded-md border border-border bg-background p-3">
            <summary className="cursor-pointer text-sm font-medium text-foreground">AI maturity score</summary>
            <pre className="mt-2 max-h-64 overflow-auto text-xs text-muted">
              {JSON.stringify(briefs?.ai_maturity_score || {}, null, 2)}
            </pre>
          </details>
        </div>
      </section>

      <section className="rounded-lg border border-border bg-surface p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-foreground">Outreach</h2>
        <p className="mt-1 text-xs text-muted">Draft, review, and send outreach for this lead.</p>
        <div className="mt-3 grid gap-3 md:grid-cols-[1fr_auto_auto_auto] md:items-end">
          <label className="text-sm">
            <span className="font-medium text-foreground">To email (optional)</span>
            <input
              value={outreachToEmail}
              onChange={(e) => setOutreachToEmail(e.target.value)}
              placeholder="Use server default if empty"
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground outline-none ring-primary focus:ring-2"
            />
          </label>
          <button
            type="button"
            onClick={() => void onDraft()}
            disabled={drafting}
            className="rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground hover:bg-background disabled:opacity-50"
          >
            {drafting ? "Drafting..." : "Draft"}
          </button>
          <button
            type="button"
            onClick={() => void onReview()}
            disabled={reviewing}
            className="rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground hover:bg-background disabled:opacity-50"
          >
            {reviewing ? "Reviewing..." : "Review"}
          </button>
          <button
            type="button"
            onClick={() => void onSend()}
            disabled={sending}
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {sending ? "Sending..." : "Send"}
          </button>
        </div>
        {outreachMessage && <p className="mt-3 text-sm text-primary">{outreachMessage}</p>}
        {outreachError && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{outreachError}</p>}
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <details className="rounded-md border border-border bg-background p-3" open>
            <summary className="cursor-pointer text-sm font-medium text-foreground">Current draft</summary>
            <pre className="mt-2 max-h-64 overflow-auto text-xs text-muted">
              {JSON.stringify(outreach?.outbound || {}, null, 2)}
            </pre>
          </details>
          <details className="rounded-md border border-border bg-background p-3" open>
            <summary className="cursor-pointer text-sm font-medium text-foreground">Current review</summary>
            <pre className="mt-2 max-h-64 overflow-auto text-xs text-muted">
              {JSON.stringify(outreach?.review || {}, null, 2)}
            </pre>
          </details>
        </div>
      </section>

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
