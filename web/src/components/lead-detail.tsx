"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { OrchestrationApiError, orchestrationFetch } from "@/lib/api";
import { readApiTraces } from "@/lib/api-trace";
import type {
  EvidenceEdge,
  LeadBriefsPayload,
  LeadConversationPayload,
  LeadScheduleBookPayload,
  LeadSchedulePreparePayload,
  LeadRespondPayload,
  LeadStatePayload,
  MessageLogItem,
  OutreachDetailPayload,
  ResponseEnvelope,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, DataTableElement } from "@/components/ui/data-table";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";

type EvidenceResponse = { edges: EvidenceEdge[] };
type DraftPayload = { draft_id: string; subject?: string; body?: string };
type ReviewPayload = { review_id: string; status: string; final_send_ok: boolean };
type SendPayload = { message_id?: string | null; delivery_status?: string };
type MemorySessionPayload = { lead_id: string; session_state: Record<string, unknown> };
type HandoffPayload = { lead_id: string; state: string; handoff_id?: string };

const transitionAllowList: Record<string, string[]> = {
  new_lead: ["enriching", "handoff_required", "disqualified"],
  enriching: ["brief_ready", "handoff_required", "disqualified"],
  brief_ready: ["drafting", "handoff_required", "disqualified"],
  drafting: ["in_review", "handoff_required", "disqualified"],
  in_review: ["queued_to_send", "handoff_required", "disqualified"],
  queued_to_send: ["awaiting_reply", "handoff_required", "disqualified"],
  awaiting_reply: ["reply_received", "handoff_required", "disqualified"],
  reply_received: ["qualifying", "scheduling", "nurture", "handoff_required", "disqualified"],
  qualifying: ["scheduling", "nurture", "handoff_required", "disqualified"],
  scheduling: ["booked", "awaiting_reply", "handoff_required", "disqualified"],
  booked: ["closed"],
  nurture: ["qualifying", "scheduling", "handoff_required", "disqualified"],
  handoff_required: [],
  disqualified: [],
  closed: [],
};

function makeIdem(prefix: string, leadId: string): string {
  return `${prefix}:${leadId}:${Date.now().toString(36)}:${Math.random().toString(36).slice(2, 9)}`;
}

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
  return "Evidence linked to this lead.";
}

function formatDate(raw?: string | null): string {
  if (!raw) return "—";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}

function normalizeError(err: unknown, fallback: string): string {
  if (err instanceof OrchestrationApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function renderJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function inferTraceIds(leadId: string): string[] {
  const entries = readApiTraces().filter(
    (entry) => entry.path.includes(encodeURIComponent(leadId)) || entry.path.includes(leadId),
  );
  const set = new Set<string>();
  for (const item of entries) {
    if (item.traceId) set.add(item.traceId);
  }
  return [...set];
}

export function LeadDetail({ leadId }: { leadId: string }) {
  const { pushToast } = useToast();
  const [state, setState] = useState<ResponseEnvelope<LeadStatePayload> | null>(null);
  const [briefs, setBriefs] = useState<LeadBriefsPayload["briefs"] | null>(null);
  const [evidence, setEvidence] = useState<EvidenceEdge[]>([]);
  const [conversation, setConversation] = useState<LeadConversationPayload | null>(null);
  const [outreach, setOutreach] = useState<OutreachDetailPayload | null>(null);
  const [session, setSession] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const [outreachToEmail, setOutreachToEmail] = useState("");
  const [replyBody, setReplyBody] = useState("");
  const [replySubject, setReplySubject] = useState("");
  const [replyChannel, setReplyChannel] = useState<"email" | "sms">("email");
  const [replyToEmail, setReplyToEmail] = useState("");
  const [escalationReason, setEscalationReason] = useState("manual_escalation");
  const [escalationSummary, setEscalationSummary] = useState("");
  const [escalationEvidenceRefs, setEscalationEvidenceRefs] = useState("");
  const [sessionPatch, setSessionPatch] = useState("{\n  \"next_best_action\": \"clarify\"\n}");
  const [transitionReason, setTransitionReason] = useState("Operator transition");
  const [transitionTarget, setTransitionTarget] = useState<string>("");

  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [sendDialogOpen, setSendDialogOpen] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [schedulePrepare, setSchedulePrepare] = useState<LeadSchedulePreparePayload | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [stateEnv, evidenceEnv, briefsEnv, outreachEnv, convEnv, memEnv] = await Promise.all([
        orchestrationFetch<LeadStatePayload>(`/lead/${encodeURIComponent(leadId)}/state`),
        orchestrationFetch<EvidenceResponse>(`/memory/evidence/${encodeURIComponent(leadId)}?limit=150`),
        orchestrationFetch<LeadBriefsPayload>(`/lead/${encodeURIComponent(leadId)}/briefs`),
        orchestrationFetch<OutreachDetailPayload>(`/outreachs/${encodeURIComponent(leadId)}`),
        orchestrationFetch<LeadConversationPayload>(`/lead/${encodeURIComponent(leadId)}/conversation?limit=150`),
        orchestrationFetch<MemorySessionPayload>(`/memory/session/${encodeURIComponent(leadId)}`),
      ]);
      setState(stateEnv);
      setEvidence(evidenceEnv.status === "success" ? evidenceEnv.data.edges || [] : []);
      setBriefs(briefsEnv.status === "success" ? briefsEnv.data.briefs : null);
      if (outreachEnv.status === "success") {
        setOutreach(outreachEnv.data);
        const to = typeof outreachEnv.data.outbound?.to_email === "string" ? outreachEnv.data.outbound.to_email : "";
        if (to) setOutreachToEmail(to);
      } else {
        setOutreach(null);
      }
      setConversation(convEnv.status === "success" ? convEnv.data : null);
      setSession(memEnv.status === "success" ? memEnv.data.session_state : null);
    } catch (err) {
      setError(normalizeError(err, "Failed to load lead."));
    } finally {
      setLoading(false);
    }
  }, [leadId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setSchedulePrepare(null);
  }, [leadId]);

  const currentState = state?.status === "success" ? state.data.state : "";
  const allowedTransitions = useMemo(() => transitionAllowList[currentState] ?? [], [currentState]);
  const traceIds = inferTraceIds(leadId);

  useEffect(() => {
    if (!transitionTarget && allowedTransitions.length > 0) {
      setTransitionTarget(allowedTransitions[0]);
    }
  }, [allowedTransitions, transitionTarget]);

  useEffect(() => {
    const rows = conversation?.messages || [];
    if (!replyToEmail) {
      for (const row of rows) {
        if (row.direction !== "inbound" || row.channel !== "email") continue;
        const candidate = typeof row.metadata?.from_email === "string" ? row.metadata.from_email : "";
        if (candidate) {
          setReplyToEmail(candidate);
          break;
        }
      }
    }
    if (!replyBody || !replySubject) {
      for (const row of rows) {
        if (row.direction !== "outbound" || row.channel !== "email") continue;
        const kind = typeof row.metadata?.kind === "string" ? row.metadata.kind : "";
        if (kind !== "suggested_reply_email") continue;
        if (!replyBody && row.content) setReplyBody(row.content);
        const suggestedSubject = typeof row.metadata?.subject === "string" ? row.metadata.subject : "";
        if (!replySubject && suggestedSubject) setReplySubject(suggestedSubject);
        break;
      }
    }
  }, [conversation, replyBody, replySubject, replyToEmail]);

  useEffect(() => {
    const nextAction = String((conversation?.session_state as Record<string, unknown> | undefined)?.next_best_action || "");
    if (nextAction !== "schedule") return;
    if (schedulePrepare !== null) return;
    let cancelled = false;
    void (async () => {
      try {
        const env = await orchestrationFetch<LeadSchedulePreparePayload>("/lead/schedule/prepare", {
          method: "POST",
          body: JSON.stringify({ lead_id: leadId }),
        });
        if (!cancelled && env.status === "success") {
          setSchedulePrepare(env.data);
        }
      } catch {
        // Keep UI usable even if schedule prepare prefetch fails.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversation, leadId, schedulePrepare]);

  async function withAction(key: string, fn: () => Promise<void>) {
    setBusyKey(key);
    setActionError(null);
    setActionMessage(null);
    try {
      await fn();
    } catch (err) {
      const msg = normalizeError(err, "Action failed.");
      setActionError(msg);
      pushToast({ tone: "error", title: "Action failed", description: msg });
    } finally {
      setBusyKey(null);
    }
  }

  function setSuccess(message: string) {
    setActionMessage(message);
    pushToast({ tone: "success", title: "Done", description: message });
  }

  async function onDraft() {
    await withAction("draft", async () => {
      const env = await orchestrationFetch<DraftPayload>("/outreach/draft", {
        method: "POST",
        body: JSON.stringify({
          lead_id: leadId,
          to_email: outreachToEmail || undefined,
          idempotency_key: makeIdem("ui_outreach_draft", leadId),
        }),
      });
      if (env.status !== "success") throw new Error(env.error?.error_message || "Draft failed.");
      setSuccess(`Draft created: ${env.data.draft_id}`);
      await load();
    });
  }

  async function onReview() {
    const draftId = typeof outreach?.outbound?.draft_id === "string" ? outreach.outbound.draft_id : "";
    if (!draftId) {
      setActionError("Create a draft first.");
      return;
    }
    await withAction("review", async () => {
      const env = await orchestrationFetch<ReviewPayload>("/outreach/review", {
        method: "POST",
        body: JSON.stringify({ lead_id: leadId, draft_id: draftId }),
      });
      if (env.status !== "success") throw new Error(env.error?.error_message || "Review failed.");
      setSuccess(`Review complete: ${env.data.status}`);
      await load();
    });
  }

  async function onSend() {
    const draftId = typeof outreach?.outbound?.draft_id === "string" ? outreach.outbound.draft_id : "";
    const reviewId = typeof outreach?.review?.review_id === "string" ? outreach.review.review_id : "";
    if (!draftId || !reviewId) {
      setActionError("Review the draft first so review_id is available.");
      return;
    }
    await withAction("send", async () => {
      const env = await orchestrationFetch<SendPayload>("/outreach/send", {
        method: "POST",
        body: JSON.stringify({
          lead_id: leadId,
          draft_id: draftId,
          review_id: reviewId,
          to_email: outreachToEmail || undefined,
          idempotency_key: makeIdem("ui_outreach_send", leadId),
        }),
      });
      if (env.status !== "success") throw new Error(env.error?.error_message || "Send failed.");
      setSuccess(`Send result: ${env.data.delivery_status || "queued"}`);
      await load();
    });
  }

  async function onSendReply() {
    if (!replyBody.trim()) {
      setActionError("Outbound reply content is required.");
      return;
    }
    await withAction("respond", async () => {
      const env = await orchestrationFetch<LeadRespondPayload>("/lead/respond", {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: makeIdem("ui_lead_respond", leadId),
          lead_id: leadId,
          channel: replyChannel,
          content: replyBody.trim(),
          subject: replySubject.trim() || undefined,
          to_email: replyToEmail.trim() || undefined,
        }),
      });
      if (env.status !== "success") {
        throw new Error(env.error?.error_message || "Outbound reply send failed.");
      }
      setSuccess(`Outbound reply queued (${env.data.message_id}).`);
      setReplyBody("");
      await load();
    });
  }

  async function onPrepareScheduling() {
    await withAction("prepare_schedule", async () => {
      const env = await orchestrationFetch<LeadSchedulePreparePayload>("/lead/schedule/prepare", {
        method: "POST",
        body: JSON.stringify({
          lead_id: leadId,
        }),
      });
      if (env.status !== "success") {
        throw new Error(env.error?.error_message || "Failed to prepare scheduling context.");
      }
      setSchedulePrepare(env.data);
      setSuccess("Scheduling context prepared from conversation history.");
      await load();
    });
  }

  async function onBookScheduling() {
    await withAction("book_schedule", async () => {
      const env = await orchestrationFetch<LeadScheduleBookPayload>("/lead/schedule/book", {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: makeIdem("ui_schedule_book", leadId),
          lead_id: leadId,
          confirmed_by_prospect: true,
          starts_at_iso: schedulePrepare?.meeting_time_start_at || undefined,
          timezone: schedulePrepare?.meeting_timezone || undefined,
        }),
      });
      if (env.status !== "success") {
        throw new Error(env.error?.error_message || "Scheduling booking failed.");
      }
      setSuccess(`Booking confirmed (${env.data.booking_id || env.data.slot_id || "booked"}).`);
      await load();
    });
  }

  async function onAdvance() {
    if (!transitionTarget) {
      setActionError("Select a target state first.");
      return;
    }
    await withAction("advance", async () => {
      const env = await orchestrationFetch<{ current_state: string }>("/lead/advance", {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: makeIdem("ui_lead_advance", leadId),
          lead_id: leadId,
          from_state: currentState,
          to_state: transitionTarget,
          reason: transitionReason || "Operator transition",
        }),
      });
      if (env.status !== "success") throw new Error(env.error?.error_message || "Transition failed.");
      setSuccess(`Lead transitioned to ${transitionTarget}.`);
      await load();
    });
  }

  async function onEscalate() {
    if (!escalationSummary.trim()) {
      setActionError("Escalation summary is required.");
      return;
    }
    await withAction("escalate", async () => {
      const refs = escalationEvidenceRefs
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
      const env = await orchestrationFetch<HandoffPayload>("/lead/escalate", {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: makeIdem("ui_lead_escalate", leadId),
          lead_id: leadId,
          reason_code: escalationReason,
          summary: escalationSummary.trim(),
          evidence_refs: refs,
        }),
      });
      if (env.status !== "success") throw new Error(env.error?.error_message || "Escalation failed.");
      setSuccess(`Escalated to handoff queue (${env.data.handoff_id || "handoff_created"}).`);
      await load();
    });
  }

  async function onMemoryWrite() {
    await withAction("memory_write", async () => {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(sessionPatch);
      } catch {
        throw new Error("Session patch must be valid JSON.");
      }
      const env = await orchestrationFetch<{ updated_keys: string[] }>("/memory/session/write", {
        method: "POST",
        body: JSON.stringify({ lead_id: leadId, session_state: parsed }),
      });
      if (env.status !== "success") throw new Error(env.error?.error_message || "Session write failed.");
      setSuccess(`Session updated (${env.data.updated_keys.join(", ") || "no keys"}).`);
      await load();
    });
  }

  async function onCompact() {
    await withAction("compact", async () => {
      const env = await orchestrationFetch<{ compaction_ref: string }>("/memory/compact", {
        method: "POST",
        body: JSON.stringify({ lead_id: leadId, reason: "manual_advanced_compact" }),
      });
      if (env.status !== "success") throw new Error(env.error?.error_message || "Compaction failed.");
      setSuccess(`Compacted: ${env.data.compaction_ref}`);
      await load();
    });
  }

  async function onRehydrate() {
    await withAction("rehydrate", async () => {
      const env = await orchestrationFetch<{ rehydrated_state_ref: string }>("/memory/rehydrate", {
        method: "POST",
        body: JSON.stringify({ lead_id: leadId }),
      });
      if (env.status !== "success") throw new Error(env.error?.error_message || "Rehydrate failed.");
      setSuccess(`Rehydrated: ${env.data.rehydrated_state_ref}`);
      await load();
    });
  }

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-2/5" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-56 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <Card className="border-danger/40 bg-danger/10">
        <CardContent className="flex items-center justify-between gap-3">
          <p className="text-sm text-danger">{error}</p>
          <Button onClick={() => void load()}>Retry</Button>
        </CardContent>
      </Card>
    );
  }

  if (!state || state.status !== "success" || !state.data) {
    return (
      <Card>
        <CardContent className="space-y-2">
          <p className="text-sm text-muted">{state?.error?.error_message || "Lead not found."}</p>
          <Button onClick={() => void load()}>Retry</Button>
        </CardContent>
      </Card>
    );
  }

  const leadState = state.data;
  const companyTitle = leadState.company_name || leadState.company_id || "Company";
  const companySubtitle = leadState.company_domain || leadState.company_id || "";
  const pendingActions = asArray(leadState.pending_actions);
  const policyFlags = asArray(leadState.policy_flags).map(String);
  const conversationState = conversation?.conversation_state || null;
  const messages = conversation?.messages || [];
  const schedulingContext = (conversationState?.scheduling_context || {}) as Record<string, unknown>;
  const nextBestAction = String((conversation?.session_state?.next_best_action as string) || "—");
  const lastIntent = String(conversationState?.last_customer_intent || "unknown");
  const outboundReplyActions = new Set(["clarify", "qualify", "handle_objection", "nurture"]);
  const replyActionNeeded = outboundReplyActions.has(nextBestAction);
  const scheduleSlots = Array.isArray(schedulingContext.slots_proposed)
    ? (schedulingContext.slots_proposed as Array<Record<string, unknown>>)
    : [];
  const scheduleTextFromContext =
    typeof schedulingContext.requested_time_text === "string" ? schedulingContext.requested_time_text : "";
  const scheduleTextFromSlots = scheduleSlots.find((slot) => typeof slot.text === "string")?.text as
    | string
    | undefined;
  const scheduleMeetingText = schedulePrepare?.meeting_time_text || scheduleTextFromContext || scheduleTextFromSlots || "";
  const scheduleMeetingStart =
    schedulePrepare?.meeting_time_start_at ||
    (scheduleSlots.find((slot) => typeof slot.start_at === "string")?.start_at as string | undefined) ||
    "";
  const scheduleTimezone = String(schedulePrepare?.meeting_timezone || schedulingContext.timezone || "unknown");
  const schedulingPortalUrl = schedulePrepare?.scheduling_portal_url || "";
  const visibleMessages = messages.filter((row) => {
    const kind = typeof row.metadata?.kind === "string" ? row.metadata.kind : "";
    const sourceNextAction =
      typeof row.metadata?.source_next_action === "string" ? row.metadata.source_next_action : "";
    return !(kind === "suggested_reply_email" && sourceNextAction === "schedule");
  });
  const latestSuggestedReply = messages.find(
    (row) =>
      row.direction === "outbound" &&
      row.channel === "email" &&
      typeof row.metadata?.kind === "string" &&
      row.metadata.kind === "suggested_reply_email",
  );
  const outboundDraft = outreach?.outbound || {};
  const outboundReview = outreach?.review || {};

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{companyTitle}</h1>
          {companySubtitle && <p className="text-sm text-muted">{companySubtitle}</p>}
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={leadState.state === "handoff_required" ? "warning" : "info"}>{humanStage(leadState.state)}</Badge>
          <Button variant="secondary" onClick={() => void load()}>
            Refresh
          </Button>
          <Link href="/pipeline" className="text-sm font-medium text-primary hover:underline">
            Back to pipeline
          </Link>
        </div>
      </div>

      {actionMessage && (
        <Card className="border-primary/30 bg-primary/10">
          <CardContent>
            <p className="text-sm text-foreground">{actionMessage}</p>
          </CardContent>
        </Card>
      )}
      {actionError && (
        <Card className="border-danger/30 bg-danger/10">
          <CardContent>
            <p className="text-sm text-danger">{actionError}</p>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="overview" value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="briefs">Briefs</TabsTrigger>
          <TabsTrigger value="outreach">Outreach</TabsTrigger>
          <TabsTrigger value="conversation">Conversation</TabsTrigger>
          <TabsTrigger value="scheduling">Scheduling</TabsTrigger>
          <TabsTrigger value="escalation">Escalation</TabsTrigger>
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
          <TabsTrigger value="observability">Observability</TabsTrigger>
          <TabsTrigger value="advanced">Advanced</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Lead State</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-muted">Stage</dt>
                    <dd className="font-medium text-foreground">{humanStage(leadState.state)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-muted">Segment</dt>
                    <dd className="text-foreground">{leadState.segment || "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-muted">Segment confidence</dt>
                    <dd className="text-foreground">
                      {typeof leadState.segment_confidence === "number"
                        ? `${Math.round(leadState.segment_confidence * 100)}%`
                        : "—"}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-muted">AI maturity</dt>
                    <dd className="text-foreground">{leadState.ai_maturity_score ?? "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-muted">Updated</dt>
                    <dd className="text-foreground">{formatDate(leadState.updated_at)}</dd>
                  </div>
                </dl>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Next Actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted">Quick transitions enforce a local allow-list before calling API.</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="text-xs text-muted">
                    Target state
                    <select
                      value={transitionTarget}
                      onChange={(e) => setTransitionTarget(e.target.value)}
                      className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                    >
                      {allowedTransitions.length === 0 && <option value="">No valid transition</option>}
                      {allowedTransitions.map((stateName) => (
                        <option key={stateName} value={stateName}>
                          {humanStage(stateName)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs text-muted">
                    Reason
                    <input
                      value={transitionReason}
                      onChange={(e) => setTransitionReason(e.target.value)}
                      className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                    />
                  </label>
                </div>
                <Button
                  variant="primary"
                  onClick={() => void onAdvance()}
                  disabled={!transitionTarget || busyKey !== null}
                >
                  {busyKey === "advance" ? "Transitioning..." : "Apply transition"}
                </Button>
                <div>
                  <p className="text-xs font-medium text-foreground">Pending actions</p>
                  {pendingActions.length === 0 ? (
                    <p className="mt-1 text-xs text-muted">No pending actions.</p>
                  ) : (
                    <ul className="mt-1 space-y-1">
                      {pendingActions.map((row, idx) => (
                        <li key={`${idx}_${String((row as Record<string, unknown>).action_type || "action")}`} className="text-xs text-foreground">
                          {String((row as Record<string, unknown>).action_type || "action")} · {String((row as Record<string, unknown>).status || "pending")}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <p className="text-xs font-medium text-foreground">Policy flags</p>
                  {policyFlags.length === 0 ? (
                    <p className="mt-1 text-xs text-muted">No active policy flags.</p>
                  ) : (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {policyFlags.map((flag) => (
                        <Badge key={flag} tone="warning">
                          {flag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="briefs" className="mt-4">
          <div className="grid gap-3 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Hiring Signal Brief</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="max-h-80 overflow-auto text-xs text-muted">{renderJson(briefs?.hiring_signal_brief || {})}</pre>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Competitor Gap Brief</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="max-h-80 overflow-auto text-xs text-muted">{renderJson(briefs?.competitor_gap_brief || {})}</pre>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>AI Maturity</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="max-h-80 overflow-auto text-xs text-muted">{renderJson(briefs?.ai_maturity_score || {})}</pre>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="outreach" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Outreach Studio</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 lg:grid-cols-[1fr_auto_auto_auto]">
                <label className="text-xs text-muted">
                  To email (optional)
                  <input
                    value={outreachToEmail}
                    onChange={(e) => setOutreachToEmail(e.target.value)}
                    placeholder="Use backend default if empty"
                    className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                  />
                </label>
                <Button variant="secondary" onClick={() => void onDraft()} disabled={busyKey !== null}>
                  {busyKey === "draft" ? "Drafting..." : "Draft"}
                </Button>
                <Button variant="secondary" onClick={() => void onReview()} disabled={busyKey !== null}>
                  {busyKey === "review" ? "Reviewing..." : "Review"}
                </Button>
                <Button variant="primary" onClick={() => setSendDialogOpen(true)} disabled={busyKey !== null}>
                  Send
                </Button>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                <Card className="bg-background">
                  <CardHeader>
                    <CardTitle>Current Draft</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <pre className="max-h-80 overflow-auto text-xs text-muted">{renderJson(outboundDraft)}</pre>
                  </CardContent>
                </Card>
                <Card className="bg-background">
                  <CardHeader>
                    <CardTitle>Current Review</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <pre className="max-h-80 overflow-auto text-xs text-muted">{renderJson(outboundReview)}</pre>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="conversation" className="mt-4">
          <div className="grid gap-4 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader>
                <CardTitle>Thread History</CardTitle>
              </CardHeader>
              <CardContent>
                {visibleMessages.length === 0 ? (
                  <p className="text-sm text-muted">No message history yet.</p>
                ) : (
                  <ul className="max-h-[32rem] space-y-2 overflow-auto">
                    {visibleMessages.map((row: MessageLogItem) => (
                      <li
                        key={`${row.message_id}_${row.recorded_at}`}
                        className="rounded-md border border-border bg-background p-3"
                      >
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <Badge tone={row.direction === "inbound" ? "info" : "neutral"}>{row.direction}</Badge>
                          <span className="text-muted">{row.channel}</span>
                          <span className="text-muted">{formatDate(row.recorded_at)}</span>
                          <span className="text-muted">msg {row.message_id}</span>
                        </div>
                        <p className="mt-2 whitespace-pre-wrap text-sm text-foreground">{row.content}</p>
                        <details className="mt-2">
                          <summary className="cursor-pointer text-xs text-muted">metadata</summary>
                          <pre className="mt-1 max-h-40 overflow-auto text-[11px] text-muted">{renderJson(row.metadata)}</pre>
                        </details>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Next Action</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="rounded-md border border-border bg-background p-2">
                  <p className="text-xs text-muted">Next best action</p>
                  <p className="text-sm font-medium text-foreground">{nextBestAction}</p>
                  <p className="mt-1 text-xs text-muted">Detected intent: {lastIntent}</p>
                </div>
                {nextBestAction === "schedule" && allowedTransitions.includes("scheduling") && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setTransitionTarget("scheduling");
                      void onAdvance();
                    }}
                    disabled={busyKey !== null}
                  >
                    Move lead to scheduling
                  </Button>
                )}
                {nextBestAction === "schedule" ? (
                  <>
                    <div className="pt-1">
                      <p className="text-xs font-medium text-foreground">Scheduling Action</p>
                      <p className="text-xs text-muted">
                        When the orchestrator detects scheduling intent, extract preferred time from thread and proceed to booking.
                      </p>
                    </div>
                    <div className="rounded-md border border-border bg-background p-2 text-xs text-foreground">
                      <p className="text-muted">Extracted meeting preference</p>
                      <p className="mt-1 whitespace-pre-wrap font-medium">{scheduleMeetingText || "Not extracted yet."}</p>
                      <p className="mt-1 text-muted">
                        Suggested start: {scheduleMeetingStart ? formatDate(scheduleMeetingStart) : "unknown"}
                      </p>
                      <p className="text-muted">Timezone: {scheduleTimezone}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => void onPrepareScheduling()}
                        disabled={busyKey !== null}
                      >
                        {busyKey === "prepare_schedule" ? "Preparing..." : "Refresh extraction"}
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          if (schedulingPortalUrl) window.open(schedulingPortalUrl, "_blank", "noopener,noreferrer");
                        }}
                        disabled={busyKey !== null || !schedulingPortalUrl}
                      >
                        Open scheduling portal
                      </Button>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => void onBookScheduling()}
                        disabled={busyKey !== null || !scheduleMeetingText}
                      >
                        {busyKey === "book_schedule" ? "Booking..." : "Book extracted time (Cal + HubSpot)"}
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="pt-1">
                      <p className="text-xs font-medium text-foreground">Outbound Reply Composer</p>
                      <p className="text-xs text-muted">
                        Outbound response should follow the latest intent and next-best-action selected by the orchestrator.
                      </p>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <label className="text-xs text-muted">
                        Channel
                        <select
                          value={replyChannel}
                          onChange={(e) => setReplyChannel(e.target.value as "email" | "sms")}
                          className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                        >
                          <option value="email">Email</option>
                        </select>
                      </label>
                      <label className="text-xs text-muted">
                        To email
                        <input
                          value={replyToEmail}
                          onChange={(e) => setReplyToEmail(e.target.value)}
                          placeholder="prospect@example.com"
                          className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                        />
                      </label>
                      <label className="text-xs text-muted">
                        Subject (email optional)
                        <input
                          value={replySubject}
                          onChange={(e) => setReplySubject(e.target.value)}
                          className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                        />
                      </label>
                    </div>
                    <label className="block text-xs text-muted">
                      Outbound reply content
                      <textarea
                        value={replyBody}
                        onChange={(e) => setReplyBody(e.target.value)}
                        rows={8}
                        className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                      />
                    </label>
                    {latestSuggestedReply && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setReplyBody(latestSuggestedReply.content || "");
                          const subj =
                            typeof latestSuggestedReply.metadata?.subject === "string"
                              ? latestSuggestedReply.metadata.subject
                              : "";
                          if (subj) setReplySubject(subj);
                        }}
                        disabled={busyKey !== null}
                      >
                        Use suggested outbound draft
                      </Button>
                    )}
                    <Button
                      variant="primary"
                      onClick={() => void onSendReply()}
                      disabled={busyKey !== null || !replyActionNeeded}
                    >
                      {busyKey === "respond" ? "Sending..." : "Send outbound reply"}
                    </Button>
                    {!replyActionNeeded && (
                      <p className="text-xs text-muted">
                        Current next-best-action does not require an outbound reply from this panel.
                      </p>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="scheduling" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Scheduling + CRM Visibility</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-2">
                <p className="text-xs text-muted">Booking status</p>
                <p className="text-sm font-medium text-foreground">
                  {String(schedulingContext.booking_status || "none")}
                </p>
                <p className="text-xs text-muted">Timezone: {String(schedulingContext.timezone || "unknown")}</p>
                <p className="text-xs text-muted">
                  Slots proposed: {Array.isArray(schedulingContext.slots_proposed) ? schedulingContext.slots_proposed.length : 0}
                </p>
                <div className="flex flex-wrap gap-2 pt-2">
                  {allowedTransitions.includes("scheduling") && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setTransitionTarget("scheduling");
                        void onAdvance();
                      }}
                      disabled={busyKey !== null}
                    >
                      Move to scheduling
                    </Button>
                  )}
                  {allowedTransitions.includes("booked") && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setTransitionTarget("booked");
                        void onAdvance();
                      }}
                      disabled={busyKey !== null}
                    >
                      Mark booked
                    </Button>
                  )}
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-xs text-muted">CRM sync visibility (read-only)</p>
                <p className="text-sm text-foreground">
                  CRM updates are emitted on key actions; current API exposes state and trace IDs but not full CRM timeline rows yet.
                </p>
                <p className="text-xs text-muted">
                  Last known trace: {(conversation?.pipeline?.last_trace_id as string) || "—"}
                </p>
                <p className="text-xs text-muted">Qualification status: {conversationState?.qualification_status || "unknown"}</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="escalation" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Escalation & Handoff</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 lg:grid-cols-3">
                <label className="text-xs text-muted">
                  Reason code
                  <input
                    value={escalationReason}
                    onChange={(e) => setEscalationReason(e.target.value)}
                    className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                  />
                </label>
                <label className="text-xs text-muted lg:col-span-2">
                  Evidence refs (comma separated)
                  <input
                    value={escalationEvidenceRefs}
                    onChange={(e) => setEscalationEvidenceRefs(e.target.value)}
                    className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                    placeholder="brief_123,msg_789"
                  />
                </label>
              </div>
              <label className="block text-xs text-muted">
                Summary
                <textarea
                  value={escalationSummary}
                  onChange={(e) => setEscalationSummary(e.target.value)}
                  rows={4}
                  className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                />
              </label>
              <div className="flex items-center gap-2">
                <Button variant="danger" onClick={() => void onEscalate()} disabled={busyKey !== null}>
                  {busyKey === "escalate" ? "Escalating..." : "Escalate to handoff"}
                </Button>
                <Link href="/handoffs" className="text-sm text-primary hover:underline">
                  Open handoff queue
                </Link>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="evidence" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Evidence Graph</CardTitle>
            </CardHeader>
            <CardContent>
              {evidence.length === 0 ? (
                <p className="text-sm text-muted">No evidence edges stored yet.</p>
              ) : (
                <ul className="max-h-[38rem] space-y-2 overflow-auto">
                  {evidence.map((row) => (
                    <li key={row.id} className="rounded-md border border-border bg-background px-3 py-2">
                      <p className="text-sm font-medium text-foreground">{humanEdge(row.edge_type)}</p>
                      <p className="mt-1 text-xs text-muted">{summarizePayload(row.payload)}</p>
                      <p className="mt-1 text-[11px] text-muted">
                        {row.brief_id ? `Brief: ${row.brief_id} · ` : ""}
                        Trace: {row.trace_id} · {formatDate(row.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="observability" className="mt-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Trace IDs</CardTitle>
              </CardHeader>
              <CardContent>
                {traceIds.length === 0 ? (
                  <p className="text-sm text-muted">No trace IDs captured in browser session yet.</p>
                ) : (
                  <ul className="space-y-1">
                    {traceIds.map((traceId) => (
                      <li key={traceId} className="font-mono text-xs text-foreground">
                        {traceId}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Failure Diagnostics</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="text-muted">Policy flags: {policyFlags.length ? policyFlags.join(", ") : "none"}</p>
                <p className="text-muted">
                  Review status: {String((outboundReview as Record<string, unknown>).status || "not reviewed")}
                </p>
                <p className="text-muted">
                  Send-ready: {String((outboundReview as Record<string, unknown>).final_send_ok ?? false)}
                </p>
                <p className="text-muted">
                  Last stage: {conversation?.pipeline?.last_stage || leadState.state}
                </p>
                <p className="text-muted">
                  Last trace: {conversation?.pipeline?.last_trace_id || "—"}
                </p>
              </CardContent>
            </Card>
          </div>
          <Card className="mt-4">
            <CardHeader>
              <CardTitle>LLM Call Explorer (derived from message metadata)</CardTitle>
            </CardHeader>
            <CardContent>
              <DataTable>
                <DataTableElement>
                  <thead className="text-xs uppercase tracking-wide text-muted">
                    <tr>
                      <th className="px-2 py-2">When</th>
                      <th className="px-2 py-2">Kind</th>
                      <th className="px-2 py-2">Intent</th>
                      <th className="px-2 py-2">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {messages
                      .filter((row) => String((row.metadata || {}).kind || "").includes("suggested_reply"))
                      .map((row) => (
                        <tr key={`${row.message_id}_${row.recorded_at}`} className="border-t border-border/70">
                          <td className="px-2 py-2 text-xs text-muted">{formatDate(row.recorded_at)}</td>
                          <td className="px-2 py-2 text-xs text-foreground">{String((row.metadata || {}).kind || "—")}</td>
                          <td className="px-2 py-2 text-xs text-foreground">{String((row.metadata || {}).intent || "—")}</td>
                          <td className="px-2 py-2 text-xs text-foreground">
                            {String((row.metadata || {}).llm_confidence || "—")}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </DataTableElement>
              </DataTable>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="advanced" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Memory & Compaction Tools</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" onClick={() => setAdvancedOpen((v) => !v)}>
                  {advancedOpen ? "Hide advanced panel" : "Show advanced panel"}
                </Button>
                <p className="text-xs text-muted">Advanced actions are intentionally hidden by default.</p>
              </div>
              {advancedOpen && (
                <div className="space-y-3">
                  <div className="grid gap-3 lg:grid-cols-2">
                    <Card className="bg-background">
                      <CardHeader>
                        <CardTitle>Session State (read-only snapshot)</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <pre className="max-h-72 overflow-auto text-xs text-muted">{renderJson(session || {})}</pre>
                      </CardContent>
                    </Card>
                    <Card className="bg-background">
                      <CardHeader>
                        <CardTitle>Write Session Patch</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        <textarea
                          value={sessionPatch}
                          onChange={(e) => setSessionPatch(e.target.value)}
                          rows={12}
                          className="w-full rounded-md border border-border bg-surface px-2 py-2 font-mono text-xs text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                        />
                        <div className="flex flex-wrap gap-2">
                          <Button variant="secondary" size="sm" onClick={() => void onMemoryWrite()} disabled={busyKey !== null}>
                            {busyKey === "memory_write" ? "Writing..." : "Write session"}
                          </Button>
                          <Button variant="secondary" size="sm" onClick={() => void onCompact()} disabled={busyKey !== null}>
                            {busyKey === "compact" ? "Compacting..." : "Compact"}
                          </Button>
                          <Button variant="secondary" size="sm" onClick={() => void onRehydrate()} disabled={busyKey !== null}>
                            {busyKey === "rehydrate" ? "Rehydrating..." : "Rehydrate"}
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog
        open={sendDialogOpen}
        title="Confirm send"
        description="Send the reviewed outreach now?"
        confirmLabel={busyKey === "send" ? "Sending..." : "Send now"}
        onCancel={() => setSendDialogOpen(false)}
        onConfirm={() => {
          setSendDialogOpen(false);
          void onSend();
        }}
      />
    </div>
  );
}
