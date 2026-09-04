/**
 * Application State Stores per §14.3
 */

export interface SessionState {
  currentSessionId: string | null;
  currentSessionName: string;
  images: any[];
  pairs: any[];
}

export interface QueryState {
  activeQueryId: string | null;
  text: string;
  detectedMode: string | null;
  detectedTask: string | null;
  status: "IDLE" | "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  answer: string | null;
  confidence: number | null;
  executionSteps: any[];
  evidenceRegions: any[];
}

export interface MapState {
  activeBaseLayer: "satellite" | "streets" | "dark";
  layerOpacity: number;
  selectedRegionId: string | null;
}

export interface UIState {
  activeModal: "upload" | "satellite" | "report" | null;
  isLoading: boolean;
}
