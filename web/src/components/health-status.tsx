"use client";

import { useCallback, useEffect, useState } from "react";

export function HealthStatus() {
  const [status, setStatus] = useState<"idle" | "ok" | "err">("idle");
  const [detail, setDetail] = useState<string>("");

  const ping = useCallback(async () => {
    setStatus("idle");
    setDetail("");
    try {
      const base = (await import("@/lib/settings")).getApiBase();
      const key = (await import("@/lib/settings")).getApiKey();
      const headers = new Headers();
      if (key) headers.set("X-API-Key", key);
      const res = await fetch(`${base}/health`, { headers });
      const json = (await res.json()) as { status?: string };
      if (!res.ok) {
        setStatus("err");
        setDetail(`${res.status}`);
        return;
      }
      setStatus("ok");
      setDetail(json.status === "ok" ? "API reachable" : JSON.stringify(json));
    } catch (e) {
      setStatus("err");
      setDetail(e instanceof Error ? e.message : "Request failed");
    }
  }, []);

  useEffect(() => {
    void ping();
  }, [ping]);

  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-foreground">API health</h2>
        <button
          type="button"
          onClick={() => void ping()}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
        >
          Retry
        </button>
      </div>
      <p className="mt-2 text-sm text-muted">
        {status === "idle" && "Checking…"}
        {status === "ok" && <span className="text-emerald-600 dark:text-emerald-400">OK — {detail}</span>}
        {status === "err" && <span className="text-red-600 dark:text-red-400">Failed — {detail}</span>}
      </p>
    </div>
  );
}
