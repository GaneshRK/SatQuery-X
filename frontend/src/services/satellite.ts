import { apiRequest } from "./api";

export interface CandidateData {
  id: string;
  stac_item_id: string;
  collection: string;
  acquisition_date: string;
  cloud_cover_pct: number;
  selected: boolean;
}

export interface SatelliteSceneData {
  id: string;
  provider: string;
  collection: string;
  external_id: string;
  platform: string;
  mission: string;
  instrument: string;
  acquisition_datetime: string;
  processing_level: string;
  cloud_cover: number | null;
  geometry: any;
  bbox: number[];
  crs: string;
  resolution: number;
  sensor: string;
  modality: string;
  thumbnail_url?: string;
  availability_status: string;
  assets?: Array<{
    id: string;
    asset_key: string;
    asset_type: string;
    href: string;
    is_downloaded: boolean;
  }>;
}

export interface AOIData {
  id: string;
  name: string;
  description: string;
  geometry: any;
  bbox: number[];
  centroid: [number, number];
  area_sqkm: number;
  crs: string;
  created_at: string;
}

export interface TemporalObservationData {
  id: string;
  aoi: string;
  scene_id: string;
  external_id: string;
  platform: string;
  sensor: string;
  observation_date: string;
  year: number;
  month: number;
  cloud_cover: number | null;
  quality_score: number;
  thumbnail_url: string;
  is_preferred: boolean;
}

export interface AOITimelineResponse {
  aoi_id: string;
  aoi_name: string;
  area_sqkm: number;
  centroid: [number, number];
  bbox: number[];
  observation_count: number;
  years_covered: number[];
  data_gaps: number[];
  earliest_observation: TemporalObservationData | null;
  latest_observation: TemporalObservationData | null;
  observations: TemporalObservationData[];
}

export interface ChangeEventData {
  id: string;
  aoi: string;
  aoi_name: string;
  before_scene_id: string;
  before_date: string;
  after_scene_id: string;
  after_date: string;
  change_type: string;
  change_polygon: any;
  area_hectares: number;
  change_percentage: number;
  confidence: number;
  algorithm: string;
  evidence_data: any;
  created_at: string;
}

export interface SyncStatusData {
  status: string;
  last_sync: string;
  scenes_indexed_total: number;
  last_job_ingested: number;
  provider: string;
  mode: string;
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

export async function listSatelliteScenes(params?: {
  sensor?: string;
  platform?: string;
  year?: number;
  limit?: number;
}): Promise<{ count: number; scenes: SatelliteSceneData[] }> {
  const query = new URLSearchParams();
  if (params?.sensor) query.append("sensor", params.sensor);
  if (params?.platform) query.append("platform", params.platform);
  if (params?.year) query.append("year", String(params.year));
  if (params?.limit) query.append("limit", String(params.limit));
  const qs = query.toString();
  return apiRequest(`/satellite/scenes/${qs ? `?${qs}` : ""}`);
}

export async function listAOIs(): Promise<AOIData[]> {
  return apiRequest("/satellite/aoi/");
}

export async function createAOI(data: {
  name: string;
  description?: string;
  bbox?: number[];
  geometry?: any;
  sensor?: string;
}): Promise<{ aoi: AOIData; indexing: any }> {
  return apiRequest("/satellite/aoi/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getAOITimeline(aoiId: string): Promise<AOITimelineResponse> {
  return apiRequest(`/satellite/aoi/${aoiId}/timeline/`);
}

export async function runChangeAnalysis(data: {
  aoi_id?: string;
  before_scene_id?: string;
  after_scene_id?: string;
  change_type?: string;
}): Promise<ChangeEventData> {
  return apiRequest("/satellite/change-analysis/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function listChangeEvents(): Promise<{ count: number; events: ChangeEventData[] }> {
  return apiRequest("/satellite/change-events/");
}

export async function getSyncStatus(): Promise<SyncStatusData> {
  return apiRequest("/satellite/sync-status/");
}

export async function triggerSync(): Promise<any> {
  return apiRequest("/satellite/sync-status/", {
    method: "POST",
  });
}
