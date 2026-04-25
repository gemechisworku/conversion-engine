"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ThemeToggle } from "@/components/theme-toggle";
import { defaultApiBase, setConnection } from "@/lib/settings";

export default function LoginPage() {
  const router = useRouter();
  const [baseUrl, setBaseUrl] = useState(defaultApiBase());
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  function onSave(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    try {
      setConnection(baseUrl, apiKey);
      router.push("/pipeline");
    } catch {
      setMessage("Could not save settings.");
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="flex justify-end border-b border-border bg-surface px-4 py-3">
        <ThemeToggle />
      </header>
      <div className="flex flex-1 flex-col items-center justify-center px-4 py-12">
        <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-lg">
          <h1 className="text-xl font-semibold text-foreground">
            Connect to <span className="text-primary">orchestration API</span>
          </h1>
          <p className="mt-2 text-sm text-muted">
            Saved in this browser only (localStorage). Keep the default base URL — Next forwards requests to FastAPI. Add an API
            key here only if your server is configured to require one.
          </p>
          <form className="mt-6 space-y-4" onSubmit={onSave}>
            <label className="block text-sm">
              <span className="font-medium text-foreground">API base URL</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground outline-none ring-primary focus:ring-2"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="/api/orchestration (default proxy)"
                required
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-foreground">API key (optional)</span>
              <input
                type="password"
                autoComplete="off"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground outline-none ring-primary focus:ring-2"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Leave empty if server has no ORCHESTRATION_API_KEY"
              />
            </label>
            {message && <p className="text-sm text-red-600 dark:text-red-400">{message}</p>}
            <button
              type="submit"
              className="w-full rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Save & go to pipeline
            </button>
          </form>
          <p className="mt-4 text-center text-sm">
            <Link href="/pipeline" className="text-primary hover:underline">
              Skip to pipeline (use env default URL only)
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
