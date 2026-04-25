"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { orchestrationFetch, OrchestrationApiError } from "@/lib/api";
import type { MemorySessionPayload } from "@/lib/types";

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
  enriching: { label: "Enrichment running", pct: 35 },
  brief_ready: { label: "Briefs ready", pct: 70 },
  drafting: { label: "Drafting outreach", pct: 80 },
  in_review: { label: "In review", pct: 88 },
  queued_to_send: { label: "Queued to send", pct: 94 },
  awaiting_reply: { label: "Awaiting reply", pct: 100 },
  booked: { label: "Booked", pct: 100 },
};

export type CompanyOption = { id: string; name: string; domain: string };

type ProgressState = { pct: number; label: string; state: string; leadId: string };

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
              await new Promise((r) => setTimeout(r, 1500));
              continue
            }
            sawCurrentRun = true;
          }
          const meta = stageMeta[state] || { label: `Stage: ${state}`, pct: 55 };
          setProgress({ pct: meta.pct, label: meta.label, state, leadId });
          lastState = state;
          if (state === "brief_ready" || state === "awaiting_reply" || state === "booked") return { reached: true, state };
        }
      } catch {
        // keep polling while processing is in-flight
      }
      await new Promise((r) => setTimeout(r, 2500));
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
    setProgress({ pct: 5, label: "Starting intake", state: "starting", leadId: fallbackLeadId });

    const stopAt = Date.now() + 6 * 60_000;
    const runStartedAtMs = Date.now();
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
        setProgress({ pct: 100, label: "Intake complete", state: observed.state || "brief_ready", leadId });
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
    <form onSubmit={(e) => void onSubmit(e)} className="max-w-xl space-y-4 rounded-lg border border-border bg-surface p-4 shadow-sm">
      <h2 className="text-base font-semibold text-foreground">Process new lead</h2>
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
          <option value="">— Select —</option>
          {filtered.slice(0, 500).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.id}){c.domain ? ` · ${c.domain}` : ""}
            </option>
          ))}
        </select>
        {filtered.length > 500 && <p className="mt-1 text-xs text-muted">Showing first 500 matches — narrow your search.</p>}
      </label>
      {selected && (
        <p className="rounded-md bg-background px-3 py-2 text-xs text-muted">
          <span className="font-medium text-foreground">id</span> {selected.id} · <span className="font-medium text-foreground">domain</span>{" "}
          {selected.domain || "—"}
        </p>
      )}
      {progress && (
        <div className="rounded-md border border-border bg-background p-3">
          <div className="mb-1 flex items-center justify-between gap-3 text-xs">
            <span className="font-medium text-foreground">{progress.label}</span>
            <span className="text-muted">{progress.pct}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-700/30">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress.pct}%` }} />
          </div>
          <p className="mt-1 text-xs text-muted">lead {progress.leadId} · state {progress.state}</p>
        </div>
      )}
      {message && <p className="text-sm text-red-600 dark:text-red-400">{message}</p>}
      <button
        type="submit"
        disabled={busy || companies.length === 0}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "Processing..." : "Run intake"}
      </button>
    </form>
  );
}
