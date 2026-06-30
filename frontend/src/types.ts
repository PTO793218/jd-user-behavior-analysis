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
  type: "bar" | "line" | "metric_cards" | "references";
  title: string;
  data: Array<Record<string, unknown>>;
  x_key?: string;
  y_key?: string;
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
};

export type ReportResponse = {
  session_id: string;
  report_markdown: string;
};
