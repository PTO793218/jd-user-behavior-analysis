import type { ChatResponse, Overview, ReportResponse, Session, SessionDetail } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {})
    },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  overview: () => request<Overview>("/api/overview"),
  listSessions: () => request<Session[]>("/api/sessions"),
  createSession: (title?: string) =>
    request<Session>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title })
    }),
  getSession: (id: string) => request<SessionDetail>(`/api/sessions/${id}`),
  deleteSession: (id: string) =>
    request<{ deleted: boolean }>(`/api/sessions/${id}`, { method: "DELETE" }),
  chat: (question: string, sessionId?: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ question, session_id: sessionId })
    }),
  generateReport: (sessionId: string) =>
    request<ReportResponse>(`/api/sessions/${sessionId}/report`, {
      method: "POST"
    })
};
