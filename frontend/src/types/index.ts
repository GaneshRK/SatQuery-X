export type InputMode = 'single_image' | 'cross_modal_pair' | 'bi_temporal' | 'change_vqa';

export interface RasterMetadata {
  image_id: string;
  filename: string;
  content_type: string;
  width: number;
  height: number;
  band_count: number;
  geo_referenced: boolean;
  crs?: string | null;
  bounds_wgs84?: { west: number; south: number; east: number; north: number } | null;
  affine?: number[] | null;
  sensor_type?: string | null;
  preview_url?: string | null;
}

export interface PlanStep {
  step: number;
  tool: string;
  version: string;
  params: Record<string, any>;
}

export interface BoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label?: string;
  confidence?: number;
}

export interface EvidenceOutput {
  change_mask_url?: string | null;
  overlay_url?: string | null;
  bboxes: BoundingBox[];
  geojson: any[];
  quantified_area_km2?: number | null;
  quantified_area_hectares?: number | null;
  change_percentage?: number | null;
  before_after_thumbnails?: string[];
}

export interface AnswerContract {
  answer: string;
  confidence: number;
  findings: string[];
  measurements: Array<{ metric: string; value: number | string; unit?: string }>;
  regions: any[];
  evidence: any[];
  sources: any[];
  models: string[];
  methods: string[];
  limitations: string[];
}

export interface AOIGeometry {
  type: string;
  coordinates: any;
  bbox?: { west: number; south: number; east: number; north: number };
  area_ha?: number;
}

export interface ExternalEvidenceItem {
  id?: string;
  source_title: string;
  source_url: string;
  domain: string;
  publisher?: string;
  trust_tier: 'TIER_1_GOV_AGENCY' | 'TIER_2_ACADEMIC_PEER_REVIEW' | 'TIER_3_REPUTABLE_NEWS' | 'TIER_4_GENERAL_WEB' | string;
  published_date?: string | null;
  extracted_facts: string[];
  relevance_score?: number;
  content_sha256?: string;
  cached_at?: string;
  expires_at?: string;
}

export interface ExecutionTrace {
  query_id: string;
  session_id: string;
  query: string;
  detected_mode: InputMode;
  task_classification: string;
  status: string;
  plan: PlanStep[];
  outputs: Record<string, any>;
  answer: string;
  confidence: number;
  answer_contract?: AnswerContract;
  evidence: EvidenceOutput;
  structured_plan?: any;
  follow_up_questions?: string[];
  evidence_graph?: any;
  external_evidence?: ExternalEvidenceItem[];
  timings_ms: Record<string, number>;
  errors: string[];
  created_at: string;
  ui_actions?: UIAction[];
  clarification?: {
    clarification_prompt?: string | null;
    clarification_options?: ClarificationOption[];
  } | null;
  completed_at?: string | null;
}

export interface UIAction {
  action: 'ZOOM_TO_REGION' | 'SHOW_LAYER' | 'SET_TIMELINE' | 'HIGHLIGHT_FEATURE' | 'RESET_VIEW' | string;
  parameters: Record<string, any>;
  description?: string;
}

export interface ClarificationOption {
  label: string;
  query: string;
  description?: string;
}

export interface ConversationContext {
  active_region?: {
    name?: string;
    coordinates?: [number, number];
    bbox?: [number, number, number, number];
  } | null;
  active_focus?: string | null;
  active_observation_pair?: {
    t1_date?: string;
    t2_date?: string;
    scene_id_t1?: string;
    scene_id_t2?: string;
  } | null;
  active_layers?: string[];
  current_visual_state?: {
    center?: [number, number];
    zoom?: number;
    active_layer?: string;
    drawn_polygon?: any;
  } | null;
  active_entities?: Array<{
    class_name: string;
    area_ha?: number;
    confidence?: number;
  }>;
  conversation_history?: Array<{
    turn: number;
    user_query: string;
    assistant_summary: string;
    focus?: string;
    timestamp?: string;
  }>;
  confidence_threshold?: number;
}

export interface ModelEntry {
  id: string;
  version: string;
  task: string;
  input_modes: string[];
  status: string;
  base_arch: string;
  training_data: string[];
  hardware: string;
  healthy: boolean;
}
