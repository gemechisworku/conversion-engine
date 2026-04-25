import type { ResponseEnvelope } from "@/lib/types";
import { getApiBase, getApiKey } from "@/lib/settings";

export class OrchestrationApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "OrchestrationApiError";
    this.status = status;
    this.body = body;
  }
}

type FetchOpts = { timeoutMs?: number };

export async function orchestrationFetch<T>(
  path: string,
  init?: RequestInit,
  opts?: FetchOpts,
): Promise<ResponseEnvelope<T>> {
  const base = getApiBase();
  const key = getApiKey();
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type") && init?.body) headers.set("Content-Type", "application/json");
  if (key) headers.set("X-API-Key", key);

  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const timeoutMs = opts?.timeoutMs ?? 90000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers, signal: controller.signal });
  } catch (err) {
    if (controller.signal.aborted) {
      throw new OrchestrationApiError(`Request timed out after ${timeoutMs}ms`, 408, null);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  const bodyText = await res.text();
  let json: unknown = null;
  if (bodyText.trim()) {
    try {
      json = JSON.parse(bodyText);
    } catch {
      const snippet = bodyText.slice(0, 180).replace(/\s+/g, " ");
      throw new OrchestrationApiError(
        `Non-JSON response from API (status ${res.status}). ${snippet || "No body."}`,
        res.status,
        bodyText,
      );
    }
  }

  if (res.status === 401) {
    throw new OrchestrationApiError("Unauthorized — check API key in Settings.", 401, json);
  }
  if (!res.ok) {
    const msg =
      typeof json === "object" && json !== null && "error" in json
        ? String((json as { error?: { error_message?: string } }).error?.error_message || res.statusText)
        : res.statusText;
    throw new OrchestrationApiError(msg, res.status, json);
  }
  if (!json || typeof json !== "object") {
    throw new OrchestrationApiError("API returned empty body; expected ResponseEnvelope JSON.", res.status, json);
  }
  return json as ResponseEnvelope<T>;
}
