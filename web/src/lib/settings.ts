const LS_BASE = "tenacious.orchestrationApiBase";
const LS_KEY = "tenacious.orchestrationApiKey";

export const DEFAULT_DIRECT_API_BASE = "http://127.0.0.1:8000";
export const DEFAULT_PROXY_API_BASE = "/api/orchestration";

export function defaultApiBase(): string {
  if (
    typeof process.env.NEXT_PUBLIC_ORCHESTRATION_API_URL === "string" &&
    process.env.NEXT_PUBLIC_ORCHESTRATION_API_URL.trim()
  ) {
    return process.env.NEXT_PUBLIC_ORCHESTRATION_API_URL.trim().replace(/\/$/, "");
  }
  return DEFAULT_DIRECT_API_BASE;
}

function normalizeStoredBase(raw: string): string {
  const t = raw.trim().replace(/\/$/, "");
  if (!t) return defaultApiBase();
  if (t === DEFAULT_PROXY_API_BASE) return DEFAULT_DIRECT_API_BASE;
  return t;
}

export function getApiBase(): string {
  if (typeof window === "undefined") {
    return defaultApiBase();
  }
  const stored = localStorage.getItem(LS_BASE);
  const resolved = normalizeStoredBase(stored || defaultApiBase());
  if (stored && resolved !== stored.trim().replace(/\/$/, "")) {
    localStorage.setItem(LS_BASE, resolved);
  }
  return resolved.replace(/\/$/, "");
}

export function getApiKey(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return localStorage.getItem(LS_KEY) || "";
}

export function setConnection(baseUrl: string, apiKey: string): void {
  localStorage.setItem(LS_BASE, baseUrl.trim().replace(/\/$/, ""));
  localStorage.setItem(LS_KEY, apiKey.trim());
}

export function clearConnection(): void {
  localStorage.removeItem(LS_BASE);
  localStorage.removeItem(LS_KEY);
}
