import { apiRequest } from "./api";

export interface CandidateData {
  id: string;
  stac_item_id: string;
  collection: string;
  acquisition_date: string;
  cloud_cover_pct: number;
  selected: boolean;
}

export async function searchSatelliteCandidates(params: {
  sessionId?: string;
  aoi_geometry: any;
  sensor: string;
  date_start: string;
  date_end: string;
  max_cloud_cover?: number;
}): Promise<{ request_id: string; candidate_count: number }> {
  return apiRequest("/satellite/search/", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function getCandidates(requestId: string): Promise<CandidateData[]> {
  return apiRequest(`/satellite/search/${requestId}/candidates/`);
}

export async function selectCandidate(requestId: string, stacItemId: string): Promise<any> {
  return apiRequest(`/satellite/search/${requestId}/select/`, {
    method: "POST",
    body: JSON.stringify({ stac_item_id: stacItemId }),
  });
}
