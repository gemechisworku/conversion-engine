"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { orchestrationFetch, OrchestrationApiError } from "@/lib/api";
import type { PipelineRun } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, DataTableElement } from "@/components/ui/data-table";

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
  handoff_required: "Handoff required",
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

  const handoffCount = useMemo(() => rows.filter((row) => row.last_stage === "handoff_required").length, [rows]);

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
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <div>
          <CardTitle>Pipeline Runs</CardTitle>
          <p className="mt-1 text-xs text-muted">
            Handoff-required runs: <span className="font-semibold text-foreground">{handoffCount}</span> ·{" "}
            <Link href="/handoffs" className="text-primary hover:underline">
              open handoff queue
            </Link>
          </p>
        </div>
        <Button size="sm" onClick={() => void load()}>
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {loading && <p className="text-sm text-muted">Loading runs...</p>}
        {error && <p className="text-sm text-danger">{error}</p>}
        {!loading && !error && rows.length === 0 && (
          <p className="text-sm text-muted">No pipeline runs yet. Run intake for a company to populate this list.</p>
        )}
        {!loading && !error && rows.length > 0 && (
          <DataTable>
            <DataTableElement>
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-2 py-2">Company</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Runs</th>
                  <th className="px-2 py-2">Trace</th>
                  <th className="px-2 py-2">Updated</th>
                  <th className="px-2 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.lead_id} className="border-t border-border/70">
                    <td className="px-2 py-3">
                      <div className="font-medium text-foreground">{row.company_name}</div>
                      <div className="text-xs text-muted">{row.company_domain || row.company_id}</div>
                    </td>
                    <td className="px-2 py-3">
                      <Badge tone={row.last_stage === "handoff_required" ? "warning" : row.last_stage.includes("failed") ? "danger" : "info"}>
                        {stageLabel[row.last_stage] || row.last_stage}
                      </Badge>
                    </td>
                    <td className="px-2 py-3 text-foreground">{row.run_count}</td>
                    <td className="px-2 py-3 font-mono text-xs text-foreground">{row.last_trace_id || "—"}</td>
                    <td className="px-2 py-3 text-muted">{humanDate(row.updated_at)}</td>
                    <td className="px-2 py-3">
                      <div className="flex items-center gap-2">
                        <Link href={`/leads/${encodeURIComponent(row.lead_id)}`} className="text-sm text-primary hover:underline">
                          Open
                        </Link>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => void onDelete(row.lead_id)}
                          disabled={deletingLead === row.lead_id}
                          className="text-danger"
                        >
                          {deletingLead === row.lead_id ? "Deleting..." : "Delete"}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTableElement>
          </DataTable>
        )}
      </CardContent>
    </Card>
  );
}

