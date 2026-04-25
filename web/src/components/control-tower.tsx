"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { OrchestrationApiError, orchestrationFetch } from "@/lib/api";
import { clearApiTraces, readApiTraces, type ApiTraceEntry } from "@/lib/api-trace";
import type { HandoffQueueItem, OutreachListItem, PipelineRun } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, DataTableElement } from "@/components/ui/data-table";

type PipelinesPayload = { pipelines: PipelineRun[] };
type OutreachsPayload = { outreachs: OutreachListItem[] };
type HandoffsPayload = { handoffs: HandoffQueueItem[] };

function formatDate(raw?: string | null): string {
  if (!raw) return "—";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}

export function ControlTower() {
  const [pipelines, setPipelines] = useState<PipelineRun[]>([]);
  const [outreachs, setOutreachs] = useState<OutreachListItem[]>([]);
  const [handoffs, setHandoffs] = useState<HandoffQueueItem[]>([]);
  const [traceEntries, setTraceEntries] = useState<ApiTraceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, o, h] = await Promise.all([
        orchestrationFetch<PipelinesPayload>("/pipelines?limit=200"),
        orchestrationFetch<OutreachsPayload>("/outreachs?limit=200"),
        orchestrationFetch<HandoffsPayload>("/handoffs?limit=200"),
      ]);
      if (p.status !== "success") throw new Error(p.error?.error_message || "Pipeline read failed.");
      if (o.status !== "success") throw new Error(o.error?.error_message || "Outreach read failed.");
      if (h.status !== "success") throw new Error(h.error?.error_message || "Handoff read failed.");
      setPipelines(p.data.pipelines || []);
      setOutreachs(o.data.outreachs || []);
      setHandoffs(h.data.handoffs || []);
      setTraceEntries(readApiTraces());
    } catch (err) {
      setError(err instanceof OrchestrationApiError ? err.message : "Failed to load control tower.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const recentFailures = useMemo(
    () => traceEntries.filter((entry) => entry.status === "failure").slice(0, 25),
    [traceEntries],
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Control Tower</CardTitle>
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => void load()}>
              Refresh
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                clearApiTraces();
                setTraceEntries([]);
              }}
            >
              Clear browser traces
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading && <p className="text-sm text-muted">Loading control data...</p>}
          {error && <p className="text-sm text-danger">{error}</p>}
          {!loading && !error && (
            <div className="grid gap-3 md:grid-cols-4">
              <SummaryCard title="Pipeline Runs" value={String(pipelines.length)} tone="info" />
              <SummaryCard title="Outreach Records" value={String(outreachs.length)} tone="neutral" />
              <SummaryCard title="Handoff Queue" value={String(handoffs.length)} tone={handoffs.length > 0 ? "warning" : "success"} />
              <SummaryCard title="Captured Trace Rows" value={String(traceEntries.length)} tone="neutral" />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Failure Diagnostics</CardTitle>
        </CardHeader>
        <CardContent>
          {recentFailures.length === 0 ? (
            <p className="text-sm text-muted">No failures captured in browser trace history.</p>
          ) : (
            <DataTable>
              <DataTableElement>
                <thead className="text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-2 py-2">At</th>
                    <th className="px-2 py-2">Path</th>
                    <th className="px-2 py-2">Status</th>
                    <th className="px-2 py-2">Trace</th>
                    <th className="px-2 py-2">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {recentFailures.map((row) => (
                    <tr key={row.id} className="border-t border-border/70">
                      <td className="px-2 py-2 text-xs text-muted">{formatDate(row.at)}</td>
                      <td className="px-2 py-2 font-mono text-xs text-foreground">{row.method} {row.path}</td>
                      <td className="px-2 py-2">
                        <Badge tone="danger">{row.httpStatus ? `${row.status}/${row.httpStatus}` : row.status}</Badge>
                      </td>
                      <td className="px-2 py-2 font-mono text-xs text-foreground">{row.traceId || "—"}</td>
                      <td className="px-2 py-2 text-xs text-foreground">{row.errorMessage || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTableElement>
            </DataTable>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent Trace Events</CardTitle>
        </CardHeader>
        <CardContent>
          {traceEntries.length === 0 ? (
            <p className="text-sm text-muted">No API call trace entries captured yet.</p>
          ) : (
            <DataTable>
              <DataTableElement>
                <thead className="text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-2 py-2">At</th>
                    <th className="px-2 py-2">Method</th>
                    <th className="px-2 py-2">Path</th>
                    <th className="px-2 py-2">Result</th>
                    <th className="px-2 py-2">Trace ID</th>
                  </tr>
                </thead>
                <tbody>
                  {traceEntries.slice(0, 80).map((row) => (
                    <tr key={row.id} className="border-t border-border/70">
                      <td className="px-2 py-2 text-xs text-muted">{formatDate(row.at)}</td>
                      <td className="px-2 py-2 text-xs text-foreground">{row.method}</td>
                      <td className="px-2 py-2 font-mono text-xs text-foreground">{row.path}</td>
                      <td className="px-2 py-2">
                        <Badge tone={row.status === "failure" ? "danger" : "success"}>
                          {row.status}
                        </Badge>
                      </td>
                      <td className="px-2 py-2 font-mono text-xs text-foreground">{row.traceId || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTableElement>
            </DataTable>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SummaryCard({
  title,
  value,
  tone,
}: {
  title: string;
  value: string;
  tone: "neutral" | "info" | "success" | "warning";
}) {
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <p className="text-xs uppercase tracking-wide text-muted">{title}</p>
      <div className="mt-2 flex items-center gap-2">
        <span className="text-xl font-semibold text-foreground">{value}</span>
        <Badge tone={tone}>{tone}</Badge>
      </div>
    </div>
  );
}

