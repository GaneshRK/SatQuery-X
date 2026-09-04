import { apiRequest } from "./api";

export interface ExecutionStepData {
  id: string;
  step_number: number;
  tool_name: string;
  model_version: string;
  parameters: any;
  status: "PENDING" | "RUNNING" | "DONE" | "FAILED" | "SKIPPED";
  latency_ms: number | null;
  output_ref: any;
}

export interface EvidenceRegionData {
  id: string;
  class_name: string;
  confidence: number;
  area_km2: number;
  area_m2: number;
  geojson_geometry: any;
}

export interface QueryDetailData {
  id: string;
  text: string;
  detected_mode: string;
  detected_task: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  answer: string | null;
  confidence: number | null;
  execution_steps: ExecutionStepData[];
  evidence_regions: EvidenceRegionData[];
}

export async function submitQuery(
  sessionId: string,
  text: string,
  imageId?: string,
  pairId?: string
): Promise<{ query_id: string; status: string; plan: any }> {
  return apiRequest(`/sessions/${sessionId}/queries/`, {
    method: "POST",
    body: JSON.stringify({ text, image_id: imageId, pair_id: pairId }),
  });
}

export async function getQuery(sessionId: string, queryId: string): Promise<QueryDetailData> {
  return apiRequest(`/sessions/${sessionId}/queries/${queryId}/`);
}

export function subscribeToQueryStream(
  sessionId: string,
  queryId: string,
  onEvent: (event: any) => void
): () => void {
  const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  const url = `${BASE_URL}/sessions/${sessionId}/queries/${queryId}/stream/`;
  const eventSource = new EventSource(url);

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
      if (data.event === "QUERY_COMPLETED" || data.event === "QUERY_FAILED") {
        eventSource.close();
      }
    } catch (err) {
      console.error("SSE parse error", err);
    }
  };

  eventSource.onerror = (err) => {
    console.warn("SSE connection closed/error", err);
    eventSource.close();
  };

  return () => {
    eventSource.close();
  };
}
