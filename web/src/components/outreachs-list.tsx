"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { orchestrationFetch, OrchestrationApiError } from "@/lib/api";
import type { OutreachListItem } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, DataTableElement } from "@/components/ui/data-table";

type OutreachsPayload = { outreachs: OutreachListItem[] };

function humanDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function reviewLabel(item: OutreachListItem): string {
  if (!item.review_status) return "Drafted";
  if (item.final_send_ok) return `${item.review_status} (send-ready)`;
  return item.review_status;
}

export function OutreachsList() {
  const [rows, setRows] = useState<OutreachListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const env = await orchestrationFetch<OutreachsPayload>("/outreachs?limit=200", undefined, { timeoutMs: 20_000 });
      if (env.status === "success" && Array.isArray(env.data.outreachs)) {
        setRows(env.data.outreachs);
      } else {
        setRows([]);
      }
    } catch (err) {
      setError(err instanceof OrchestrationApiError ? err.message : "Failed to load outreach records.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>Outreach Records</CardTitle>
        <Button size="sm" onClick={() => void load()}>
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {loading && <p className="text-sm text-muted">Loading outreach records...</p>}
        {error && <p className="text-sm text-danger">{error}</p>}
        {!loading && !error && rows.length === 0 && (
          <p className="text-sm text-muted">No outreach records yet. Draft an outreach from a lead detail page first.</p>
        )}
        {!loading && !error && rows.length > 0 && (
          <DataTable>
            <DataTableElement>
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-2 py-2">Company</th>
                  <th className="px-2 py-2">Subject</th>
                  <th className="px-2 py-2">Review</th>
                  <th className="px-2 py-2">Updated</th>
                  <th className="px-2 py-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.lead_id} className="border-t border-border/70">
                    <td className="px-2 py-3">
                      <div className="font-medium text-foreground">{row.company_name || row.company_id || row.lead_id}</div>
                      <div className="text-xs text-muted">{row.company_domain || row.company_id || row.lead_id}</div>
                    </td>
                    <td className="px-2 py-3 text-foreground">{row.subject || "—"}</td>
                    <td className="px-2 py-3">
                      <Badge tone={row.final_send_ok ? "success" : row.review_status ? "warning" : "neutral"}>
                        {reviewLabel(row)}
                      </Badge>
                    </td>
                    <td className="px-2 py-3 text-muted">{humanDate(row.updated_at)}</td>
                    <td className="px-2 py-3">
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

