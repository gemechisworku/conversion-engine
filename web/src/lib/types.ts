/** Mirrors `agent/services/orchestration/schemas.py` ResponseEnvelope (JSON). */

export type ResponseEnvelope<T = Record<string, unknown>> = {
  request_id: string;
  trace_id: string;
  status: string;
  data: T;
  error: {
    error_code: string;
    error_message: string;
    retryable?: boolean;
    details?: Record<string, unknown>;
  } | null;
  timestamp: string;
};

export type LeadStatePayload = {
  lead_id: string;
  state: string;
  company_id?: string | null;
  company_name?: string | null;
  company_domain?: string | null;
  segment?: string | null;
  segment_confidence?: number;
  ai_maturity_score?: number | null;
  pending_actions?: unknown[];
  kb_refs?: unknown[];
  policy_flags?: unknown[];
  updated_at?: string;
};

export type EvidenceEdge = {
  id: number;
  lead_id: string;
  trace_id: string;
  edge_type: string;
  claim_ref: string | null;
  brief_id: string | null;
  source_ref: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type PipelineRun = {
  lead_id: string;
  company_id: string;
  company_name: string;
  company_domain?: string | null;
  run_count: number;
  last_stage: string;
  last_trace_id?: string | null;
  started_at: string;
  updated_at: string;
};

export type MemorySessionPayload = {
  lead_id: string;
  session_state: {
    current_stage: string;
    updated_at?: string;
  };
};

export type LeadBriefsPayload = {
  lead_id: string;
  briefs: {
    hiring_signal_brief?: Record<string, unknown>;
    competitor_gap_brief?: Record<string, unknown>;
    ai_maturity_score?: Record<string, unknown>;
    updated_at?: string;
  };
};

export type OutreachListItem = {
  lead_id: string;
  company_id?: string | null;
  company_name?: string | null;
  company_domain?: string | null;
  updated_at: string;
  last_send_idempotency?: string | null;
  draft_id?: string | null;
  subject?: string | null;
  to_email?: string | null;
  review_status?: string | null;
  review_id?: string | null;
  final_send_ok?: boolean | null;
};

export type OutreachDetailPayload = {
  lead_id: string;
  company_id?: string | null;
  company_name?: string | null;
  company_domain?: string | null;
  updated_at?: string | null;
  last_send_idempotency?: string | null;
  outbound?: Record<string, unknown>;
  review?: Record<string, unknown> | null;
};
