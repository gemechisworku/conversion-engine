export type ApiTraceStatus = "success" | "failure";

export type ApiTraceEntry = {
  id: string;
  at: string;
  path: string;
  method: string;
  status: ApiTraceStatus;
  httpStatus?: number;
  traceId?: string;
  requestBody?: unknown;
  responseBody?: unknown;
  errorMessage?: string;
};

const TRACE_KEY = "tenacious.apiTrace.entries";
const MAX_ENTRIES = 120;
let inMemoryEntries: ApiTraceEntry[] = [];

function loadStoredEntries(): ApiTraceEntry[] {
  if (typeof window === "undefined") return inMemoryEntries;
  try {
    const raw = sessionStorage.getItem(TRACE_KEY);
    if (!raw) return inMemoryEntries;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return inMemoryEntries;
    return parsed.filter((v) => typeof v === "object" && v !== null) as ApiTraceEntry[];
  } catch {
    return inMemoryEntries;
  }
}

function saveStoredEntries(entries: ApiTraceEntry[]) {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(TRACE_KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    // ignore storage failures
  }
}

export function recordApiTrace(entry: Omit<ApiTraceEntry, "id" | "at">) {
  const next: ApiTraceEntry = {
    id: crypto.randomUUID(),
    at: new Date().toISOString(),
    ...entry,
  };
  const loaded = loadStoredEntries();
  inMemoryEntries = [next, ...loaded].slice(0, MAX_ENTRIES);
  saveStoredEntries(inMemoryEntries);
}

export function readApiTraces(): ApiTraceEntry[] {
  const loaded = loadStoredEntries();
  inMemoryEntries = loaded.slice(0, MAX_ENTRIES);
  return inMemoryEntries;
}

export function clearApiTraces() {
  inMemoryEntries = [];
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(TRACE_KEY);
  }
}

