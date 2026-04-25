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
