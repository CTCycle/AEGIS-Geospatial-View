export type JsonPrimitive = string | number | boolean | null;

export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];

export interface JsonObject {
  [key: string]: JsonValue;
}

export interface ResolvedLocation {
  label: string;
  latitude: number;
  longitude: number;
  country?: string | null;
  city?: string | null;
  address?: string | null;
  source?: string;
  confidence?: number;
}

export interface ViewportPolicy {
  center_latitude: number;
  center_longitude: number;
  radius_m: number;
  bbox?: number[] | null;
}

export interface PresentationPolicy {
  emphasize_overlays: boolean;
  high_contrast: boolean;
  show_legend: boolean;
}

export interface LocationSearchRequest {
  resolved_location: ResolvedLocation;
  intent_id: string;
  time_mode: 'current' | 'historical' | 'forecast';
  basemap_id: string;
  overlay_ids: string[];
  viewport: ViewportPolicy;
  presentation: PresentationPolicy;
}

export interface CapabilityDescriptor {
  id: string;
  name: string;
  kind: 'basemap' | 'overlay' | 'tool' | string;
  provider: string;
  requires_credentials: boolean;
  is_available: boolean;
  supports_map: boolean;
  supports_direct_text: boolean;
  coverage: string;
  intent_tags: string[];
  task_tags: string[];
  metadata?: Record<string, JsonValue>;
}

export interface CatalogResponse {
  capabilities: CapabilityDescriptor[];
  basemaps?: CapabilityDescriptor[];
  overlays?: CapabilityDescriptor[];
}

export interface MapSession {
  session_id: string;
  resolved_location: ResolvedLocation;
  basemap_id: string;
  overlay_ids: string[];
  viewport: ViewportPolicy;
  generated_at?: string;
  payload?: Record<string, JsonValue>;
  center?: { latitude?: number | null; longitude?: number | null };
  bounds?: [number, number, number, number] | number[];
  basemap?: {
    id: string;
    label?: string;
    provider?: string;
    tile_url?: string | null;
    attribution?: string;
  };
  overlays?: Array<{
    id: string;
    label: string;
    provider: string;
    type: string;
    default_opacity?: number;
    url?: string | null;
    layers?: string;
    layer_id?: string;
    tile_matrix_set?: string;
    wmts_format?: string;
    wmts_style?: string;
    wms_version?: string;
    wms_exceptions?: string;
    bounds?: [number, number, number, number];
    attribution?: string;
  }>;
  compliance_warnings?: string[];
}

export interface SearchResponse {
  status_message: string;
  map_session: MapSession;
}

export interface SearchResponsePayload {
  satellite_imagery?: Record<string, JsonValue>;
  map_session?: MapSession;
  compliance_warnings?: string[];
}

export type ChatRole = 'user' | 'assistant' | 'system' | 'tool';

export interface ChatMessage {
  role: ChatRole;
  content: string;
  created_at?: string;
}

export interface ChatTurnRequest {
  session_id?: number;
  title?: string;
  message: string;
  datetime?: string;
}

export interface NormalizedIntent {
  intent_id: string;
  intent_label: string;
  task_tags: string[];
  intent_tags: string[];
  requires_location: boolean;
}

export interface TemporalSignal {
  mode: 'current' | 'historical' | 'forecast' | 'none';
  raw_text?: string | null;
  reference_time_iso?: string | null;
}

export interface LocationSignal {
  signal_type: 'address' | 'city' | 'country' | 'coordinates' | 'deictic';
  raw_value: string;
  normalized_value?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  confidence: number;
  source: 'text' | 'memory' | 'model';
}

export interface TurnParseResult {
  user_text: string;
  task_class: 'map_search' | 'direct_query' | 'general_question' | 'unclear';
  location_signals: LocationSignal[];
  normalized_intent: NormalizedIntent;
  temporal_signal: TemporalSignal;
  ambiguities: string[];
  parser_confidence: number;
}

export interface ClarificationRequest {
  question: string;
  reason: string;
  missing_fields: string[];
}

export interface PolicyDecision {
  plan: {
    state: 'clarify' | 'direct_tool' | 'map_search' | 'reject';
    mode?: 'direct_text' | 'map' | null;
    intent_id: string;
    basemap_id?: string | null;
    overlay_ids: string[];
    tool_id?: string | null;
  };
  clarification?: ClarificationRequest | null;
  resolved_location?: ResolvedLocation | null;
  trace?: { steps: string[] };
}

export interface ToolPayload {
  tool_id?: string;
  plan_state?: string;
  location?: {
    label: string;
    latitude: number;
    longitude: number;
  };
  result?: Record<string, JsonValue>;
  error?: string;
}

export interface ChatTurnResponse {
  session_id: number;
  assistant_message: string;
  turn_contract?: TurnParseResult;
  decision?: PolicyDecision;
  tool_payload?: ToolPayload | null;
  map_session?: MapSession | null;
  memory_snapshot?: Record<string, JsonValue>;
  follow_up_required?: boolean;
  fallback_mode?: string | null;
}

export type ChatStreamEventType = 'status' | 'assistant_delta' | 'tool_status' | 'final' | 'error';

export interface ChatStreamEvent {
  event: ChatStreamEventType;
  data: Record<string, JsonValue>;
}

export type ModelProviderMode = 'local' | 'cloud';

export interface ModelCardDescriptor {
  id: string;
  name: string;
  description: string;
  provider: string;
  capabilities: string[];
  metadata: Record<string, JsonValue>;
}

export interface ModelSettingsResponse {
  active_provider_mode: ModelProviderMode;
  chat_model_provider: string;
  chat_model_name: string;
  parser_model_provider: string;
  parser_model_name: string;
  agent_model_provider: string;
  agent_model_name: string;
  ollama_url: string;
  openai_base_url?: string | null;
  google_base_url?: string | null;
  credentials: Record<string, Record<string, boolean>>;
}

export interface ModelSettingsUpdateRequest {
  active_provider_mode: ModelProviderMode;
  chat_model_provider: string;
  chat_model_name: string;
  parser_model_provider: string;
  parser_model_name: string;
  agent_model_provider: string;
  agent_model_name: string;
  ollama_url: string;
  openai_base_url?: string | null;
  google_base_url?: string | null;
  credentials: Record<string, { api_key?: string }>;
}

export interface OllamaHealthResponse {
  ok?: boolean;
  detail?: string;
  [key: string]: unknown;
}

export interface GenericObjectResponse {
  [key: string]: unknown;
}

export interface VectorizationResponse {
  status: string;
  indexed_documents: number;
  vector_path: string;
}
