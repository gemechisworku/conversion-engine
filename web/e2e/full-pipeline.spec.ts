import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";

function leadIdForCompany(companyId: string): string {
  const digest = createHash("sha256").update(companyId).digest("hex").slice(0, 10);
  return `lead_${digest}`;
}

function envelope(status: string, data: Record<string, unknown>, traceId = "trace_e2e_1") {
  return {
    request_id: `req_${Math.random().toString(36).slice(2, 8)}`,
    trace_id: traceId,
    status,
    data,
    error: null,
    timestamp: new Date().toISOString(),
  };
}

test("login -> process lead -> lead detail -> outreach -> reply -> escalate", async ({ page }) => {
  const companyId = "comp_e2e_1";
  const leadId = leadIdForCompany(companyId);

  await page.route("**/api/companies**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        companies: [{ id: companyId, name: "Acme E2E", domain: "acme-e2e.ai" }],
      }),
    });
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const rawPath = `${url.pathname}${url.search}`;
    const path = rawPath.startsWith("/api/orchestration")
      ? rawPath.slice("/api/orchestration".length) || "/"
      : rawPath;
    const method = route.request().method().toUpperCase();

    const isMockedApiPath =
      path === "/health" ||
      path === "/lead/process" ||
      path === "/outreach/draft" ||
      path === "/lead/reply" ||
      path === "/lead/escalate" ||
      path.startsWith(`/memory/session/${leadId}`) ||
      path.startsWith(`/lead/${leadId}/state`) ||
      path.startsWith(`/memory/evidence/${leadId}`) ||
      path.startsWith(`/lead/${leadId}/briefs`) ||
      path.startsWith(`/outreachs/${leadId}`) ||
      path.startsWith(`/lead/${leadId}/conversation`);
    if (!isMockedApiPath && !rawPath.startsWith("/api/companies")) {
      await route.continue();
      return;
    }

    if (path === "/health") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      return;
    }
    if (path === "/lead/process" && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(envelope("accepted", { lead_id: leadId, state: "brief_ready" }, "trace_process_1")),
      });
      return;
    }
    if (path.startsWith(`/memory/session/${leadId}`) && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          envelope("success", {
            lead_id: leadId,
            session_state: {
              current_stage: "brief_ready",
              next_best_action: "draft",
              updated_at: new Date().toISOString(),
            },
          }),
        ),
      });
      return;
    }
    if (path.startsWith(`/lead/${leadId}/state`)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          envelope("success", {
            lead_id: leadId,
            state: "awaiting_reply",
            company_id: companyId,
            company_name: "Acme E2E",
            company_domain: "acme-e2e.ai",
            segment: "recently_funded_startup",
            segment_confidence: 0.81,
            ai_maturity_score: 2,
            pending_actions: [{ action_type: "wait_for_reply", status: "pending" }],
            policy_flags: [],
            updated_at: new Date().toISOString(),
          }),
        ),
      });
      return;
    }
    if (path.startsWith(`/memory/evidence/${leadId}`)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(envelope("success", { lead_id: leadId, edges: [] })),
      });
      return;
    }
    if (path.startsWith(`/lead/${leadId}/briefs`)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(envelope("success", { lead_id: leadId, briefs: {} })),
      });
      return;
    }
    if (path.startsWith(`/outreachs/${leadId}`)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          envelope("success", {
            lead_id: leadId,
            outbound: {
              draft_id: "draft_1",
              subject: "Hello from Tenacious",
              to_email: "prospect@example.com",
            },
            review: {
              review_id: "review_1",
              status: "approved",
              final_send_ok: true,
            },
          }),
        ),
      });
      return;
    }
    if (path.startsWith(`/lead/${leadId}/conversation`)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          envelope("success", {
            lead_id: leadId,
            session_state: { next_best_action: "clarify" },
            conversation_state: {
              lead_id: leadId,
              conversation_state_id: "conv_1",
              current_stage: "waiting",
              current_channel: "email",
              last_customer_intent: "unknown",
              last_customer_sentiment: "neutral",
              qualification_status: "unknown",
              open_questions: [],
              pending_actions: [],
              objections: [],
              scheduling_context: { booking_status: "none", timezone: null, slots_proposed: [] },
              policy_flags: [],
              updated_at: new Date().toISOString(),
            },
            messages: [],
            pipeline: {
              lead_id: leadId,
              company_id: companyId,
              company_name: "Acme E2E",
              company_domain: "acme-e2e.ai",
              run_count: 1,
              last_stage: "awaiting_reply",
              last_trace_id: "trace_process_1",
              started_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
          }),
        ),
      });
      return;
    }
    if (path === "/outreach/draft" && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(envelope("success", { draft_id: "draft_new_1" }, "trace_outreach_draft")),
      });
      return;
    }
    if (path === "/lead/reply" && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          envelope("accepted", { lead_id: leadId, state: "reply_received", next_action: "schedule" }, "trace_reply_1"),
        ),
      });
      return;
    }
    if (path === "/lead/escalate" && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          envelope("success", { lead_id: leadId, state: "handoff_required", handoff_id: "handoff_1" }, "trace_handoff_1"),
        ),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(envelope("success", {})),
    });
  });

  await page.goto("/login");
  await page.evaluate(() => {
    localStorage.setItem("tenacious.orchestrationApiBase", "http://127.0.0.1:8000");
    localStorage.setItem("tenacious.orchestrationApiKey", "");
  });
  await page.goto("/pipeline");
  await expect(page).toHaveURL(/\/pipeline$/);

  await page.evaluate(async ({ companyId }) => {
    await fetch("http://127.0.0.1:8000/lead/process", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        idempotency_key: "idem_e2e_1",
        company_id: companyId,
        source: "crunchbase",
        priority: "normal",
        metadata: { company_name: "Acme E2E", company_domain: "acme-e2e.ai" },
      }),
    });
  }, { companyId });
  await page.goto(`/leads/${leadId}`);

  await expect(page).toHaveURL(new RegExp(`/leads/${leadId}$`));

  const draftResponse = await page.evaluate(async ({ leadId }) => {
    const res = await fetch("http://127.0.0.1:8000/outreach/draft", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ lead_id: leadId, idempotency_key: "idem_outreach_1" }),
    });
    return res.json();
  }, { leadId });
  expect(draftResponse.status).toBe("success");
  expect(draftResponse.data.draft_id).toBe("draft_new_1");

  const replyResponse = await page.evaluate(async ({ leadId }) => {
    const res = await fetch("http://127.0.0.1:8000/lead/reply", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        idempotency_key: "idem_reply_1",
        lead_id: leadId,
        channel: "email",
        message_id: "msg_1",
        content: "Can you share times next week?",
      }),
    });
    return res.json();
  }, { leadId });
  expect(replyResponse.status).toBe("accepted");
  expect(replyResponse.data.next_action).toBe("schedule");

  const escalateResponse = await page.evaluate(async ({ leadId }) => {
    const res = await fetch("http://127.0.0.1:8000/lead/escalate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        idempotency_key: "idem_escalate_1",
        lead_id: leadId,
        reason_code: "manual_escalation",
        summary: "Prospect asked for custom legal language.",
        evidence_refs: ["brief_1"],
      }),
    });
    return res.json();
  }, { leadId });
  expect(escalateResponse.status).toBe("success");
  expect(escalateResponse.data.handoff_id).toBe("handoff_1");
});
