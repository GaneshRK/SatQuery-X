import { apiRequest } from "./api";
import { ConversationContext } from "@/types";

export interface SessionContextResponse {
  session_id: string;
  conversation_context: ConversationContext;
}

export async function getSessionContext(sessionId: string): Promise<SessionContextResponse> {
  return apiRequest(`/sessions/${sessionId}/context/`);
}

export async function resetSessionContext(sessionId: string): Promise<{ session_id: string; status: string; conversation_context: ConversationContext }> {
  return apiRequest(`/sessions/${sessionId}/context/reset/`, {
    method: "POST",
  });
}
