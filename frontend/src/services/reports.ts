import { apiRequest } from "./api";

export async function generateReport(
  sessionId: string,
  queryId?: string,
  format: "PDF" | "HTML" = "PDF"
): Promise<{ report_id: string; format: string; status: string }> {
  return apiRequest(`/sessions/${sessionId}/reports/`, {
    method: "POST",
    body: JSON.stringify({ query_id: queryId, format }),
  });
}

export function getReportDownloadUrl(sessionId: string, reportId: string): string {
  const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  return `${BASE_URL}/sessions/${sessionId}/reports/${reportId}/download/`;
}
