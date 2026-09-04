import { apiRequest } from "./api";

export interface ImageAssetData {
  id: string;
  original_filename: string;
  file_format: string;
  sensor: string;
  modality: string;
  width: number;
  height: number;
  band_count: number;
  crs: string | null;
  resolution_m: number | null;
  preview_url: string | null;
  bounds_wgs84: { west: number; south: number; east: number; north: number } | null;
  is_georeferenced?: boolean;
  processing_status: "UPLOADED" | "VALIDATING" | "VALIDATED" | "FAILED";
  validation_report: any;
}

export interface ImagePairData {
  id: string;
  image_a: string;
  image_b: string;
  pair_type: "CROSS_MODAL" | "BI_TEMPORAL";
  compatibility_status: "PENDING" | "COMPATIBLE" | "INCOMPATIBLE";
  compatibility_report: any;
}

export async function uploadImage(sessionId: string, file: File): Promise<{ image_id: string; asset: ImageAssetData }> {
  const formData = new FormData();
  formData.append("file", file);

  return apiRequest(`/sessions/${sessionId}/images/`, {
    method: "POST",
    body: formData,
  });
}

export async function listImages(sessionId: string): Promise<ImageAssetData[]> {
  return apiRequest(`/sessions/${sessionId}/images/`);
}

export async function createPair(
  sessionId: string,
  imageAId: string,
  imageBId: string,
  pairType: "CROSS_MODAL" | "BI_TEMPORAL"
): Promise<{ pair_id: string; compatibility_status: string }> {
  return apiRequest(`/sessions/${sessionId}/pairs/`, {
    method: "POST",
    body: JSON.stringify({
      image_a_id: imageAId,
      image_b_id: imageBId,
      pair_type: pairType,
    }),
  });
}
