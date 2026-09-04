import { apiRequest } from "./api";

export interface ConversationItem {
  query_id?: string;
  role: "user" | "assistant";
  content: string;
  task?: string;
  confidence?: number;
  tools_executed?: string[];
  timestamp?: string;
}

export interface SessionData {
  id: string;
  name: string;
  status: "active" | "archived";
  project?: string | null;
  conversation_history?: ConversationItem[];
  created_at: string;
  updated_at: string;
  image_count: number;
  query_count: number;
}

export async function listSessions(): Promise<{ results: SessionData[] }> {
  return apiRequest("/sessions/");
}

export async function createSession(name: string): Promise<SessionData> {
  return apiRequest("/sessions/", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function getSession(id: string): Promise<SessionData> {
  return apiRequest(`/sessions/${id}/`);
}

export async function deleteSession(id: string): Promise<void> {
  return apiRequest(`/sessions/${id}/`, {
    method: "DELETE",
  });
}
