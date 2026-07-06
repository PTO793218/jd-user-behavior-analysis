export type Session = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type ToolCall = {
  id: string;
  session_id: string;
  message_id: string;
  tool_name: string;
  result_json: string;
  created_at: string;
};

export type RagSource = {
  source: string;
  heading: string;
  content: string;
  score: number;
};

export type ToolPayload = {
  name: string;
  result: unknown;
};

export type Confidence = {
  level: "高" | "中" | "低";
  reason: string;
};

export type VisualPayload = {
  tool_name: string;
  type: "bar" | "line" | "metric_cards" | "references" | "table" | "matrix" | "plan";
  title: string;
  data: Array<Record<string, unknown>>;
  x_key?: string;
  y_key?: string;
  columns?: Array<{ key: string; label: string }>;
};

export type EvidenceFact = {
  label: string;
  value: unknown;
  source: string;
  note?: string;
};

export type AgentTrace = {
  intent: string;
  planned_tools: string[];
  planning_reason: string;
  planning_used_llm: boolean;
  model_status: string;
  evidence_summary: EvidenceFact[];
};

export type ModelStatus = {
  configured: boolean;
  status: string;
  model: string;
  base_url: string;
  provider: string;
};

export type SessionDetail = {
  session: Session;
  messages: Message[];
  tool_calls: ToolCall[];
};

export type Overview = {
  records: number;
  users: number;
  goods: number;
  rfm_users: number;
  semantic_sample_count: number;
  semantic_scope_note: string;
  model_status?: ModelStatus;
  date_range?: string;
  charts?: {
    behavior_counts?: Array<Record<string, unknown>>;
    behavior_funnel?: Array<Record<string, unknown>>;
    daily_trend?: Array<Record<string, unknown>>;
    rfm_summary?: Array<Record<string, unknown>>;
  };
};

export type ChatResponse = {
  session_id: string;
  message: Message;
  answer: string;
  tools: ToolPayload[];
  rag_sources: RagSource[];
  used_llm: boolean;
  error: string;
  routing_explanation: string;
  confidence: Confidence;
  context_summary: string;
  visual_payloads: VisualPayload[];
  evidence_summary: EvidenceFact[];
  agent_trace: AgentTrace;
};

export type ReportResponse = {
  session_id: string;
  report_markdown: string;
};
