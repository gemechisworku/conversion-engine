"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { orchestrationFetch, OrchestrationApiError } from "@/lib/api";
import type { PipelineRun } from "@/lib/types";

type PipelinesPayload = { pipelines: PipelineRun[] };

const stageLabel: Record<string, string> = {
  enriching: "Enrichment in progress",
  brief_ready: "Briefs ready",
  drafting: "Drafting outreach",
  in_review: "Under review",
  queued_to_send: "Queued to send",
  awaiting_reply: "Awaiting reply",
  reply_received: "Reply received",
  scheduling: "Scheduling",
  booked: "Booked",
  failed: "Failed",
  failed_invalid_transition: "Failed",
};

function humanDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

export function PipelineRunsList({ refreshToken }: { refreshToken: number }) {
  const [rows, setRows] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingLead, setDeletingLead] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const env = await orchestrationFetch<PipelinesPayload>("/pipelines?limit=200", undefined, { timeoutMs: 20_000 });
      if (env.status === "success" && Array.isArray(env.data.pipelines)) {
        setRows(env.data.pipelines);
      } else {
        setRows([]);
      }
    } catch (err) {
      setError(err instanceof OrchestrationApiError ? err.message : "Failed to load pipeline runs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  const grouped = useMemo(() => rows, [rows]);

  async function onDelete(leadId: string) {
    if (!confirm("Delete this pipeline run and its stored state?")) return;
    setDeletingLead(leadId);
    try {
      const env = await orchestrationFetch<{ deleted: boolean }>(`/pipelines/${encodeURIComponent(leadId)}`, {
        method: "DELETE",
      });
      if (env.status === "success") {
        setRows((prev) => prev.filter((r) => r.lead_id !== leadId));
      }
    } catch (err) {
      setError(err instanceof OrchestrationApiError ? err.message : "Delete failed.");
    } finally {
      setDeletingLead(null);
    }
  }

  return (
    <section className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-foreground">Pipeline runs</h2>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-background"
        >
          Refresh
        </button>
      </div>
      {loading && <p className="text-sm text-muted">Loading runs...</p>}
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {!loading && !error && grouped.length === 0 && (
        <p className="text-sm text-muted">No pipeline runs yet. Run intake for a company to populate this list.</p>
      )}
      {!loading && !error && grouped.length > 0 && (
        <div className="overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-2 py-2">Company</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Runs</th>
                <th className="px-2 py-2">Updated</th>
                <th className="px-2 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {grouped.map((row) => (
                <tr key={row.lead_id} className="border-t border-border/70">
                  <td className="px-2 py-3">
                    <div className="font-medium text-foreground">{row.company_name}</div>
                    <div className="text-xs text-muted">
                      {row.company_domain || row.company_id} · lead {row.lead_id}
                    </div>
                  </td>
                  <td className="px-2 py-3 text-foreground">{stageLabel[row.last_stage] || row.last_stage}</td>
                  <td className="px-2 py-3 text-foreground">{row.run_count}</td>
                  <td className="px-2 py-3 text-muted">{humanDate(row.updated_at)}</td>
                  <td className="px-2 py-3">
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/leads/${encodeURIComponent(row.lead_id)}`}
                        className="rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-background"
                      >
                        Open
                      </Link>
                      <button
                        type="button"
                        onClick={() => void onDelete(row.lead_id)}
                        disabled={deletingLead === row.lead_id}
                        className="rounded-md border border-red-500/40 px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50 dark:text-red-300 dark:hover:bg-red-950/30"
                      >
                        {deletingLead === row.lead_id ? "Deleting..." : "Delete"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

