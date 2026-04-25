import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LeadDetail } from "@/components/lead-detail";

const orchestrationFetchMock = vi.fn();
const pushToastMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: { children: unknown; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api-trace", () => ({
  readApiTraces: () => [],
}));

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ pushToast: pushToastMock }),
}));

vi.mock("@/lib/api", () => {
  class MockApiError extends Error {
    status: number;
    body: unknown;
    constructor(message: string, status = 500, body: unknown = null) {
      super(message);
      this.status = status;
      this.body = body;
    }
  }
  return {
    orchestrationFetch: (...args: unknown[]) => orchestrationFetchMock(...args),
    OrchestrationApiError: MockApiError,
  };
});

function env(status: string, data: Record<string, unknown>, traceId = "trace_test_1") {
  return {
    request_id: "req_test_1",
    trace_id: traceId,
    status,
    data,
    error: null,
    timestamp: new Date().toISOString(),
  };
}

function wireDefaultApiMocks(leadId: string) {
  orchestrationFetchMock.mockImplementation(async (path: string) => {
    if (path.includes(`/lead/${leadId}/state`)) {
      return env("success", {
        lead_id: leadId,
        state: "awaiting_reply",
        company_name: "Acme Test",
        company_domain: "acme.test",
        segment: "segment_a",
        segment_confidence: 0.7,
        ai_maturity_score: 2,
        pending_actions: [],
        policy_flags: [],
      });
    }
    if (path.includes(`/memory/evidence/${leadId}`)) return env("success", { lead_id: leadId, edges: [] });
    if (path.includes(`/lead/${leadId}/briefs`)) return env("success", { lead_id: leadId, briefs: {} });
    if (path.includes(`/outreachs/${leadId}`)) {
      return env("success", {
        lead_id: leadId,
        outbound: { draft_id: "draft_1", subject: "Subject", to_email: "prospect@example.com" },
        review: { review_id: "review_1", status: "approved", final_send_ok: true },
      });
    }
    if (path.includes(`/lead/${leadId}/conversation`)) {
      return env("success", {
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
        messages: [
          {
            lead_id: leadId,
            channel: "email",
            message_id: "msg_in_1",
            direction: "inbound",
            content: "Can you tell me more about your services?",
            recorded_at: new Date().toISOString(),
            metadata: { from_email: "prospect@example.com", subject: "Re: Intro" },
          },
          {
            lead_id: leadId,
            channel: "email",
            message_id: "msg_suggested_1",
            direction: "outbound",
            content: "Thanks for the question. We support...",
            recorded_at: new Date().toISOString(),
            metadata: { kind: "suggested_reply_email", subject: "Re: Intro" },
          },
        ],
        pipeline: { last_stage: "awaiting_reply", last_trace_id: "trace_test_1" },
      });
    }
    if (path.includes(`/memory/session/${leadId}`)) {
      return env("success", { lead_id: leadId, session_state: { current_stage: "awaiting_reply" } });
    }
    if (path === "/outreach/draft") return env("success", { draft_id: "draft_new_1" }, "trace_draft_1");
    if (path === "/lead/respond")
      return env("success", { lead_id: leadId, message_id: "reply_msg_1", delivery_status: "queued" }, "trace_reply_1");
    return env("success", {});
  });
}

describe("LeadDetail", () => {
  beforeEach(() => {
    orchestrationFetchMock.mockReset();
    pushToastMock.mockReset();
  });

  it("runs outreach draft action", async () => {
    const leadId = "lead_test_1";
    wireDefaultApiMocks(leadId);
    render(<LeadDetail leadId={leadId} />);

    await screen.findByText("Acme Test");
    await userEvent.click(screen.getByRole("tab", { name: "Outreach" }));
    await userEvent.click(screen.getByRole("button", { name: /^Draft$/ }));

    await waitFor(() => {
      expect(screen.getByText(/Draft created:/)).toBeInTheDocument();
    });
    expect(orchestrationFetchMock).toHaveBeenCalledWith(
      "/outreach/draft",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("sends outbound reply from conversation panel", async () => {
    const leadId = "lead_test_2";
    wireDefaultApiMocks(leadId);
    render(<LeadDetail leadId={leadId} />);

    await screen.findByText("Acme Test");
    await userEvent.click(screen.getByRole("tab", { name: "Conversation" }));
    await userEvent.clear(screen.getByLabelText(/Outbound reply content/i));
    await userEvent.type(screen.getByLabelText(/Outbound reply content/i), "Thanks. We can help with...");
    await userEvent.click(screen.getByRole("button", { name: /send outbound reply/i }));

    await waitFor(() => {
      expect(screen.getByText(/Outbound reply queued/)).toBeInTheDocument();
    });
    expect(orchestrationFetchMock).toHaveBeenCalledWith(
      "/lead/respond",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
