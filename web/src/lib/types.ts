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

export type MessageLogItem = {
  lead_id: string;
  channel: string;
  message_id: string;
  direction: string;
  content: string;
  recorded_at: string;
  metadata: Record<string, unknown>;
};

export type ConversationStatePayload = {
  lead_id: string;
  conversation_state_id: string;
  current_stage: string;
  current_channel: string;
  last_inbound_message_id?: string | null;
  last_outbound_message_id?: string | null;
  last_customer_intent: string;
  last_customer_sentiment: string;
  qualification_status: string;
  open_questions: Array<Record<string, unknown>>;
  pending_actions: Array<Record<string, unknown>>;
  objections: Array<Record<string, unknown>>;
  scheduling_context: Record<string, unknown>;
  policy_flags: string[];
  updated_at: string;
};

export type LeadConversationPayload = {
  lead_id: string;
  session_state: Record<string, unknown>;
  conversation_state: ConversationStatePayload | null;
  messages: MessageLogItem[];
  pipeline?: PipelineRun | null;
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

export type HandoffQueueItem = {
  lead_id: string;
  current_stage: string;
  handoff_required: boolean;
  pending_actions: Array<Record<string, unknown>>;
  policy_flags: string[];
  updated_at: string;
  company_id?: string | null;
  company_name?: string | null;
  company_domain?: string | null;
  last_trace_id?: string | null;
};

export type LeadRespondPayload = {
  lead_id: string;
  message_id: string;
  delivery_status: string;
  state?: string;
  next_action?: string;
};

export type LeadSchedulePreparePayload = {
  lead_id: string;
  next_action?: string;
  meeting_time_text?: string | null;
  meeting_time_source?: string | null;
  meeting_time_start_at?: string | null;
  meeting_timezone?: string | null;
  booking_status?: string;
  scheduling_portal_url?: string | null;
};

export type LeadScheduleBookPayload = {
  lead_id: string;
  state: string;
  booking_id?: string | null;
  slot_id?: string | null;
  calendar_ref?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  timezone?: string | null;
  crm_sync_status?: string;
};
