"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { OrchestrationApiError, orchestrationFetch } from "@/lib/api";
import type { HandoffQueueItem } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, DataTableElement } from "@/components/ui/data-table";

type HandoffsPayload = { handoffs: HandoffQueueItem[] };

function formatDate(raw: string): string {
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}

export function HandoffQueue() {
  const [rows, setRows] = useState<HandoffQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const env = await orchestrationFetch<HandoffsPayload>("/handoffs?limit=200");
      if (env.status !== "success") {
        throw new Error(env.error?.error_message || "Failed to load handoff queue.");
      }
      setRows(env.data.handoffs || []);
    } catch (err) {
      setError(err instanceof OrchestrationApiError ? err.message : "Failed to load handoff queue.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Handoff Queue</CardTitle>
        <Button size="sm" onClick={() => void load()}>
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {loading && <p className="text-sm text-muted">Loading queue...</p>}
        {error && <p className="text-sm text-danger">{error}</p>}
        {!loading && !error && rows.length === 0 && <p className="text-sm text-muted">No handoff-required leads right now.</p>}
        {!loading && !error && rows.length > 0 && (
          <DataTable>
            <DataTableElement>
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-2 py-2">Company</th>
                  <th className="px-2 py-2">Lead</th>
                  <th className="px-2 py-2">Flags</th>
                  <th className="px-2 py-2">Trace</th>
                  <th className="px-2 py-2">Updated</th>
                  <th className="px-2 py-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.lead_id} className="border-t border-border/70">
                    <td className="px-2 py-2">
                      <div className="font-medium text-foreground">{row.company_name || row.company_id || row.lead_id}</div>
                      <div className="text-xs text-muted">{row.company_domain || row.company_id || "—"}</div>
                    </td>
                    <td className="px-2 py-2">
                      <Badge tone="warning">{row.current_stage}</Badge>
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(row.policy_flags || []).slice(0, 3).map((flag) => (
                          <Badge key={flag} tone="danger">
                            {flag}
                          </Badge>
                        ))}
                        {(!row.policy_flags || row.policy_flags.length === 0) && <span className="text-xs text-muted">none</span>}
                      </div>
                    </td>
                    <td className="px-2 py-2 font-mono text-xs text-foreground">{row.last_trace_id || "—"}</td>
                    <td className="px-2 py-2 text-xs text-muted">{formatDate(row.updated_at)}</td>
                    <td className="px-2 py-2">
                      <Link href={`/leads/${encodeURIComponent(row.lead_id)}`} className="text-sm text-primary hover:underline">
                        Open lead
                      </Link>
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

