"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { orchestrationFetch, OrchestrationApiError } from "@/lib/api";
import type { MemorySessionPayload } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function randomId(prefix: string) {
  return `${prefix}_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
}

async function leadIdForCompany(companyId: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(companyId));
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return `lead_${hex.slice(0, 10)}`;
}

const stageMeta: Record<string, { label: string; pct: number }> = {
  new_lead: { label: "Lead created", pct: 8 },
  enriching: { label: "Enrichment running", pct: 22 },
  brief_ready: { label: "Briefs ready", pct: 70 },
  drafting: { label: "Drafting outreach", pct: 80 },
  in_review: { label: "In review", pct: 88 },
  queued_to_send: { label: "Queued to send", pct: 94 },
  awaiting_reply: { label: "Awaiting reply", pct: 100 },
  booked: { label: "Booked", pct: 100 },
};

type EnrichmentStepMeta = { actionType: string; label: string; pct: number };
const ENRICHMENT_STEPS: EnrichmentStepMeta[] = [
  { actionType: "enrichment.resolve_record", label: "Resolve record", pct: 18 },
  { actionType: "enrichment.crunchbase", label: "Crunchbase", pct: 28 },
  { actionType: "enrichment.job_posts", label: "Job posts", pct: 40 },
  { actionType: "enrichment.layoffs", label: "Layoffs", pct: 48 },
  { actionType: "enrichment.leadership", label: "Leadership", pct: 56 },
  { actionType: "enrichment.merge", label: "Merge signals", pct: 66 },
  { actionType: "enrichment.ai_maturity", label: "AI maturity", pct: 76 },
  { actionType: "enrichment.icp_classification", label: "ICP", pct: 84 },
  { actionType: "enrichment.competitor_gap", label: "Gap brief", pct: 90 },
  { actionType: "enrichment.hiring_signal_brief", label: "Hiring brief", pct: 95 },
  { actionType: "enrichment.persist", label: "Persist", pct: 98 },
];

const ENRICHMENT_STEP_INDEX = new Map(ENRICHMENT_STEPS.map((step) => [step.actionType, step]));

type StepStatus = "pending" | "running" | "done" | "failed";

type ProgressStep = {
  actionType: string;
  label: string;
  status: StepStatus;
  startedAt?: string;
  completedAt?: string;
};

export type CompanyOption = { id: string; name: string; domain: string };

type ProgressState = {
  pct: number;
  label: string;
  state: string;
  leadId: string;
  objective?: string;
  steps?: ProgressStep[];
  elapsedSec: number;
};

function elapsedSeconds(startedAtMs: number): number {
  return Math.max(0, Math.round((Date.now() - startedAtMs) / 1000));
}

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function normalizeStepStatus(value: unknown): StepStatus {
  const status = String(value || "").toLowerCase();
  if (status === "done" || status === "running" || status === "failed") return status;
  return "pending";
}

function parseProgressSteps(session: MemorySessionPayload["session_state"]): ProgressStep[] {
  const source = Array.isArray(session.pending_actions) ? session.pending_actions : [];
  const byAction = new Map<
    string,
    { status: StepStatus; startedAt?: string; completedAt?: string }
  >();
  for (const item of source) {
    if (!item || typeof item !== "object") continue;
    const actionType = String((item as Record<string, unknown>).action_type || "").trim();
    if (!ENRICHMENT_STEP_INDEX.has(actionType)) continue;
    const startedAtRaw = (item as Record<string, unknown>).started_at;
    const completedAtRaw = (item as Record<string, unknown>).completed_at;
    byAction.set(actionType, {
      status: normalizeStepStatus((item as Record<string, unknown>).status),
      startedAt: typeof startedAtRaw === "string" ? startedAtRaw : undefined,
      completedAt: typeof completedAtRaw === "string" ? completedAtRaw : undefined,
    });
  }
  return ENRICHMENT_STEPS.map((step) => ({
    actionType: step.actionType,
    label: step.label,
    status: byAction.get(step.actionType)?.status || "pending",
    startedAt: byAction.get(step.actionType)?.startedAt,
    completedAt: byAction.get(step.actionType)?.completedAt,
  }));
}

const STEP_DURATION_HINTS_SEC = new Map<string, number>([
  ["enrichment.resolve_record", 2],
  ["enrichment.crunchbase", 4],
  ["enrichment.job_posts", 32],
  ["enrichment.layoffs", 3],
  ["enrichment.leadership", 3],
  ["enrichment.merge", 2],
  ["enrichment.ai_maturity", 8],
  ["enrichment.icp_classification", 8],
  ["enrichment.competitor_gap", 12],
  ["enrichment.hiring_signal_brief", 12],
  ["enrichment.persist", 3],
]);

function progressFromEnrichment(
  session: MemorySessionPayload["session_state"],
  options: { leadId: string; startedAtMs: number },
): ProgressState {
  const { leadId, startedAtMs } = options;
  const steps = parseProgressSteps(session);
  const running = steps.find((step) => step.status === "running");
  const failed = steps.find((step) => step.status === "failed");
  const doneCount = steps.filter((step) => step.status === "done").length;

  let pct = stageMeta.enriching.pct;
  if (failed) {
    const failedMeta = ENRICHMENT_STEP_INDEX.get(failed.actionType);
    pct = Math.max(stageMeta.enriching.pct, (failedMeta?.pct || stageMeta.enriching.pct) - 2);
  } else if (running) {
    const stepIndex = ENRICHMENT_STEPS.findIndex((step) => step.actionType === running.actionType);
    const base = ENRICHMENT_STEP_INDEX.get(running.actionType)?.pct || stageMeta.enriching.pct;
    const nextPct =
      stepIndex >= 0 && stepIndex < ENRICHMENT_STEPS.length - 1 ? ENRICHMENT_STEPS[stepIndex + 1]!.pct : 99;
    if (running.startedAt) {
      const startedAtMs = Date.parse(running.startedAt);
      if (Number.isFinite(startedAtMs)) {
        const elapsed = Math.max(0, (Date.now() - startedAtMs) / 1000);
        const expected = STEP_DURATION_HINTS_SEC.get(running.actionType) || 10;
        const ramp = Math.min(0.92, elapsed / expected);
        const span = Math.max(1, nextPct - base - 1);
        pct = Math.min(nextPct - 1, Math.round(base + span * ramp));
      } else {
        pct = base;
      }
    } else {
      pct = base;
    }
  } else if (doneCount > 0) {
    pct = ENRICHMENT_STEPS[Math.min(doneCount, ENRICHMENT_STEPS.length) - 1]?.pct || stageMeta.enriching.pct;
  }

  let label = stageMeta.enriching.label;
  if (failed) {
    label = `${failed.label} failed`;
  } else if (running) {
    if (running.startedAt) {
      const stepElapsedMs = Date.now() - Date.parse(running.startedAt);
      const elapsedSec = Number.isFinite(stepElapsedMs) ? Math.max(0, Math.round(stepElapsedMs / 1000)) : 0;
      label = `${running.label} in progress (${elapsedSec}s)`;
    } else {
      label = `${running.label} in progress`;
    }
  } else if (doneCount > 0 && doneCount < ENRICHMENT_STEPS.length) {
    label = `${ENRICHMENT_STEPS[doneCount]?.label || "Next step"} pending`;
  } else if (doneCount >= ENRICHMENT_STEPS.length) {
    label = "Finalizing enrichment";
  }

  return {
    pct,
    label,
    state: "enriching",
    leadId,
    objective: typeof session.current_objective === "string" ? session.current_objective : undefined,
    steps,
    elapsedSec: elapsedSeconds(startedAtMs),
  };
}

function stageProgressFromState(
  session: MemorySessionPayload["session_state"],
  options: { leadId: string; startedAtMs: number },
): ProgressState {
  const { leadId, startedAtMs } = options;
  const state = String(session.current_stage || "");
  if (state === "enriching") {
    return progressFromEnrichment(session, { leadId, startedAtMs });
  }
  const meta = stageMeta[state] || { label: `Stage: ${state}`, pct: 55 };
  return {
    pct: meta.pct,
    label: meta.label,
    state,
    leadId,
    objective: typeof session.current_objective === "string" ? session.current_objective : undefined,
    elapsedSec: elapsedSeconds(startedAtMs),
  };
}

function stepTone(status: StepStatus): string {
  if (status === "done") return "border-emerald-400/40 bg-emerald-500/10 text-emerald-300";
  if (status === "running") return "border-primary/50 bg-primary/15 text-primary";
  if (status === "failed") return "border-red-400/40 bg-red-500/10 text-red-300";
  return "border-border/70 bg-background text-muted";
}

export function ProcessLeadForm({ onPipelineChanged }: { onPipelineChanged?: () => void }) {
  const router = useRouter();
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressState | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/companies");
        const data = (await res.json()) as { companies?: CompanyOption[]; warning?: string };
        if (cancelled) return;
        setCompanies(Array.isArray(data.companies) ? data.companies : []);
        if (data.warning === "crunchbase_csv_not_found") {
          setLoadError("Crunchbase CSV not found. Set CRUNCHBASE_DATASET_PATH in web/.env.local if the file lives elsewhere.");
        } else if (data.warning) {
          setLoadError("Could not load company list.");
        }
      } catch {
        if (!cancelled) setLoadError("Failed to load companies.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return companies;
    return companies.filter(
      (c) => c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q) || c.domain.toLowerCase().includes(q),
    );
  }, [companies, filter]);

  const selected = useMemo(() => companies.find((c) => c.id === selectedId) ?? null, [companies, selectedId]);

  async function pollLeadProgress(
    leadId: string,
    stopAtMs: number,
    runStartedAtMs: number,
  ): Promise<{ reached: boolean; state?: string }> {
    let lastState = "";
    let sawCurrentRun = false;
    while (Date.now() < stopAtMs) {
      try {
        const mem = await orchestrationFetch<MemorySessionPayload>(
          `/memory/session/${encodeURIComponent(leadId)}`,
          undefined,
          { timeoutMs: 15_000 },
        );
        if (mem.status === "success") {
          const session = mem.data.session_state;
          const state = String(session.current_stage || "");
          const updatedAtMs = Date.parse(String(session.updated_at || ""));
          if (!sawCurrentRun) {
            if (Number.isFinite(updatedAtMs) && updatedAtMs < runStartedAtMs && state === "brief_ready") {
              await new Promise((r) => setTimeout(r, 1200));
              continue;
            }
            sawCurrentRun = true;
          }
          setProgress(stageProgressFromState(session, { leadId, startedAtMs: runStartedAtMs }));
          lastState = state;
          if (state === "brief_ready" || state === "awaiting_reply" || state === "booked") return { reached: true, state };
        }
      } catch {
        // keep polling while processing is in-flight
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
    return { reached: false, state: lastState || undefined };
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    if (!selected) {
      setMessage("Select a company from the list.");
      return;
    }

    setBusy(true);
    const fallbackLeadId = await leadIdForCompany(selected.id);
    const runStartedAtMs = Date.now();
    setProgress({
      pct: 5,
      label: "Starting intake",
      state: "starting",
      leadId: fallbackLeadId,
      elapsedSec: 0,
    });

    const stopAt = Date.now() + 6 * 60_000;
    const watcher = pollLeadProgress(fallbackLeadId, stopAt, runStartedAtMs);

    try {
      const env = await orchestrationFetch<{ lead_id: string; state?: string }>(
        "/lead/process",
        {
          method: "POST",
          body: JSON.stringify({
            idempotency_key: randomId("idem"),
            company_id: selected.id,
            source: "crunchbase",
            priority: "normal",
            metadata: {
              company_name: selected.name,
              company_domain: selected.domain,
            },
          }),
        },
        { timeoutMs: 5 * 60_000 },
      );

      const leadId = env.data.lead_id || fallbackLeadId;
      const observed = await watcher;
      if (env.status === "accepted" || env.status === "success") {
        setProgress({
          pct: 100,
          label: "Intake complete",
          state: observed.state || "brief_ready",
          leadId,
          elapsedSec: elapsedSeconds(runStartedAtMs),
        });
        onPipelineChanged?.();
        router.push(`/leads/${encodeURIComponent(leadId)}`);
        return;
      }
      setMessage(env.error?.error_message || `Status: ${env.status}`);
    } catch (err) {
      const text = err instanceof OrchestrationApiError ? err.message : "Request failed";
      if (err instanceof OrchestrationApiError && /non-json|timed out|gateway|502|503|504/i.test(text)) {
        setMessage("Process request channel timed out, but backend may still be running. Watching lead state...");
        const observed = await watcher;
        if (observed.reached) {
          onPipelineChanged?.();
          router.push(`/leads/${encodeURIComponent(fallbackLeadId)}`);
          return;
        }
        setMessage(`Processing did not reach brief_ready in time. Last observed state: ${observed.state || "unknown"}.`);
      } else {
        setMessage(text);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Process New Lead</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={(e) => void onSubmit(e)} className="space-y-4">
          <p className="text-sm text-muted">
            Select a company from the bundled Crunchbase dataset, then run intake (<code className="rounded bg-background px-1">POST /lead/process</code>).
          </p>
          {loadError && <p className="text-sm text-amber-700 dark:text-amber-400">{loadError}</p>}
          <label className="block text-sm">
            <span className="font-medium text-foreground">Search companies</span>
            <input
              type="search"
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground outline-none ring-primary focus:ring-2"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by name, id, or domain..."
              disabled={companies.length === 0}
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium text-foreground">Company</span>
            <select
              required
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground outline-none ring-primary focus:ring-2"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              disabled={companies.length === 0}
            >
              <option value="">- Select -</option>
              {filtered.slice(0, 500).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.id}){c.domain ? ` | ${c.domain}` : ""}
                </option>
              ))}
            </select>
            {filtered.length > 500 && <p className="mt-1 text-xs text-muted">Showing first 500 matches - narrow your search.</p>}
          </label>
          {selected && (
            <p className="rounded-md bg-background px-3 py-2 text-xs text-muted">
              <span className="font-medium text-foreground">id</span> {selected.id} | <span className="font-medium text-foreground">domain</span>{" "}
              {selected.domain || "-"}
            </p>
          )}
          {progress && (
            <div className="rounded-md border border-border bg-background p-3">
              <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                <span className="font-medium text-foreground">{progress.label}</span>
                <span className="text-muted">{progress.pct}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-700/30">
                <div className="h-full rounded-full bg-primary transition-all duration-700" style={{ width: `${progress.pct}%` }} />
              </div>
              <p className="mt-1 text-xs text-muted">
                lead {progress.leadId} | state {progress.state} | elapsed {formatElapsed(progress.elapsedSec)}
              </p>
              {progress.objective && <p className="mt-1 text-[11px] text-muted">objective: {progress.objective}</p>}
              {progress.steps && progress.steps.length > 0 && (
                <div className="mt-2 grid grid-cols-2 gap-1">
                  {progress.steps.map((step) => (
                    <div
                      key={step.actionType}
                      className={`rounded-md border px-2 py-1 text-[11px] transition ${stepTone(step.status)} ${step.status === "running" ? "animate-pulse" : ""}`}
                    >
                      <span className="font-medium">{step.label}</span>
                      <span className="ml-1 uppercase tracking-wide">{step.status}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {message && <p className="text-sm text-red-600 dark:text-red-400">{message}</p>}
          <Button type="submit" variant="primary" disabled={busy || companies.length === 0}>
            {busy ? "Processing..." : "Run intake"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

