import { describe, expect, it, vi, beforeEach } from "vitest";
import { clearApiTraces, readApiTraces } from "@/lib/api-trace";
import { OrchestrationApiError, orchestrationFetch } from "@/lib/api";

describe("orchestrationFetch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("tenacious.orchestrationApiBase", "http://127.0.0.1:8000");
    localStorage.setItem("tenacious.orchestrationApiKey", "test_key");
    clearApiTraces();
  });

  it("returns response envelope on success and captures trace entry", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          request_id: "req_1",
          trace_id: "trace_1",
          status: "success",
          data: { ok: true },
          error: null,
          timestamp: new Date().toISOString(),
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const env = await orchestrationFetch<{ ok: boolean }>("/health");
    expect(env.status).toBe("success");
    expect(env.data.ok).toBe(true);
    const traces = readApiTraces();
    expect(traces.length).toBeGreaterThan(0);
    expect(traces[0].traceId).toBe("trace_1");
    expect(traces[0].status).toBe("success");
  });

  it("throws on unauthorized responses and logs failure trace", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          request_id: "req_2",
          trace_id: "trace_2",
          status: "failure",
          data: {},
          error: { error_code: "UNAUTHORIZED", error_message: "invalid key", retryable: false },
          timestamp: new Date().toISOString(),
        }),
        { status: 401, headers: { "content-type": "application/json" } },
      ),
    );

    await expect(orchestrationFetch("/lead/abc/state")).rejects.toBeInstanceOf(OrchestrationApiError);
    const traces = readApiTraces();
    expect(traces[0].status).toBe("failure");
    expect(traces[0].httpStatus).toBe(401);
  });
});

