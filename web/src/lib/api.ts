import { recordApiTrace } from "@/lib/api-trace";
import { getApiBase, getApiKey } from "@/lib/settings";
import type { ResponseEnvelope } from "@/lib/types";

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
  const method = (init?.method || "GET").toUpperCase();
  const requestBody = parseJsonBody(init?.body);

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
    recordApiTrace({
      path,
      method,
      status: "failure",
      requestBody,
      errorMessage:
        controller.signal.aborted
          ? `Request timed out after ${timeoutMs}ms`
          : err instanceof Error
            ? err.message
            : "Network request failed",
    });
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
      recordApiTrace({
        path,
        method,
        status: "failure",
        httpStatus: res.status,
        requestBody,
        responseBody: bodyText,
        errorMessage: `Non-JSON response from API (status ${res.status}). ${snippet || "No body."}`,
      });
      throw new OrchestrationApiError(
        `Non-JSON response from API (status ${res.status}). ${snippet || "No body."}`,
        res.status,
        bodyText,
      );
    }
  }

  if (res.status === 401) {
    recordApiTrace({
      path,
      method,
      status: "failure",
      httpStatus: res.status,
      requestBody,
      responseBody: json,
      errorMessage: "Unauthorized — check API key in Settings.",
    });
    throw new OrchestrationApiError("Unauthorized — check API key in Settings.", 401, json);
  }
  if (!res.ok) {
    const msg =
      typeof json === "object" && json !== null && "error" in json
        ? String((json as { error?: { error_message?: string } }).error?.error_message || res.statusText)
        : res.statusText;
    recordApiTrace({
      path,
      method,
      status: "failure",
      httpStatus: res.status,
      requestBody,
      responseBody: json,
      errorMessage: msg,
    });
    throw new OrchestrationApiError(msg, res.status, json);
  }
  if (!json || typeof json !== "object") {
    recordApiTrace({
      path,
      method,
      status: "failure",
      httpStatus: res.status,
      requestBody,
      responseBody: json,
      errorMessage: "API returned empty body; expected ResponseEnvelope JSON.",
    });
    throw new OrchestrationApiError("API returned empty body; expected ResponseEnvelope JSON.", res.status, json);
  }

  const envelope = json as ResponseEnvelope<T>;
  recordApiTrace({
    path,
    method,
    status: envelope.status === "failure" ? "failure" : "success",
    httpStatus: res.status,
    traceId: envelope.trace_id,
    requestBody,
    responseBody: envelope,
    errorMessage: envelope.error?.error_message,
  });
  return envelope;
}

function parseJsonBody(body: BodyInit | null | undefined): unknown {
  if (!body) return undefined;
  if (typeof body !== "string") return body;
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}

