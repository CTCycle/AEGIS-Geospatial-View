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
  kind: CapabilityKind | 'overlay' | 'tool' | string;
  type?: string;
  description?: string;
  provider: string;
  requires_credentials: boolean;
  is_available: boolean;
  supports_map: boolean;
  supports_direct_text: boolean;
  coverage: string;
  intent_tags: string[];
  task_tags: string[];
  source_protocol?: string;
  data_format?: string;
  geometry_type?: string;
  queryable?: boolean;
  vectorizable?: boolean;
  endpoint_health?: string;
  auth_mode?: string;
  official_docs_url?: string;
  capability_kind?: CapabilityKind | string;
  rendering_mode?: RenderingMode | string;
  reliability?: LayerReliability;
  auth?: ProviderAuthPolicy;
  metadata?: Record<string, JsonValue>;
}

export interface CatalogResponse {
  capabilities: CapabilityDescriptor[];
  providers?: CapabilityDescriptor[];
  basemaps?: CapabilityDescriptor[];
  overlays?: CapabilityDescriptor[];
  cameras?: CapabilityDescriptor[];
  transit?: CapabilityDescriptor[];
  tools?: CapabilityDescriptor[];
}

export type CapabilityKind =
  | 'basemap'
  | 'raster-overlay'
  | 'vector-overlay'
  | 'search-index'
  | 'camera-network'
  | 'dataset-ingestion'
  | 'analysis-tool'
  | 'metadata-only';

export type ProviderAuthType = 'none' | 'api-key' | 'oauth' | 'token-header' | 'paid-or-gated';

export type LayerHealthStatus = 'functional' | 'partial' | 'broken' | 'disabled' | 'unknown';

export type RenderingMode =
  | 'xyz'
  | 'wmts'
  | 'wms'
  | 'geojson'
  | 'vector-tile'
  | 'raster-tile'
  | 'clustered-points'
  | 'choropleth'
  | 'camera-points'
  | 'metadata-only';

export interface ProviderAuthPolicy {
  type: ProviderAuthType | string;
  required: boolean;
  providerKey?: string | null;
  accessPageProviderId?: string | null;
}

export interface LayerReliability {
  status: LayerHealthStatus | string;
  lastAudited?: string;
  knownLimitations?: string[];
}

export interface CameraFeature {
  id: string;
  name: string;
  provider: string;
  camera_type: string;
  latitude: number;
  longitude: number;
  last_update_time?: string | null;
  preview_image_url?: string | null;
  official_url: string;
  embed_url?: string | null;
  embedding_allowed: boolean;
  stale: boolean;
  metadata: Record<string, JsonValue>;
}

export interface GeospatialCredentialStatus {
  provider: string;
  required: boolean;
  configured: boolean;
  environmentVariable?: string | null;
}

export interface ProviderAccountSetupStep {
  id: string;
  title: string;
  description: string;
  url?: string | null;
}

export interface ProviderCredentialField {
  name: string;
  label: string;
  secret: boolean;
  required: boolean;
  placeholder?: string | null;
}

export interface ProviderAccountSetup {
  provider_id: string;
  mode: 'manual' | 'not_required';
  automation_supported: boolean;
  automation_reason?: string | null;
  account_url?: string | null;
  dashboard_url?: string | null;
  documentation_url?: string | null;
  credential_fields: ProviderCredentialField[];
  steps: ProviderAccountSetupStep[];
}

export interface ProviderCredentialValidationRequest {
  credentials: Record<string, string>;
}

export interface ProviderCredentialValidationResult {
  provider_id: string;
  valid: boolean;
  status: 'valid' | 'invalid' | 'unsupported' | 'error';
  message: string;
}

export interface GeospatialProviderPayload {
  status: 'ok' | 'missing-credential' | 'unavailable' | string;
  provider: string;
  payload?: Record<string, JsonValue>;
  attribution?: string[];
  warnings?: string[];
  stale?: boolean;
  message?: string;
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
    rendering_mode?: RenderingMode | string;
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
      maxzoom?: number;
      source_protocol?: string;
      data_format?: string;
      geometry_type?: string;
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

export interface OverlayStateChange {
  overlayVisibility: Record<string, boolean>;
  overlayOpacity: Record<string, number>;
}

export interface OverlayVisibilityChange {
  overlayId: string;
  checked: boolean;
}

export interface OverlayOpacityChange {
  overlayId: string;
  percentValue: string;
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
  request_id?: string;
}

export interface ContextUsage {
  estimated_input_tokens: number;
  selected_context_window?: number | null;
  model_context_limit?: number | null;
  usage_percent: number;
  provider: string;
  model: string;
}

export interface NormalizedIntent {
  intent_id: string;
  intent_label: string;
  task_tags: string[];
  intent_tags: string[];
  requested_visualizations?: string[];
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
  request_id: string;
  session_id: number;
  assistant_message: string;
  turn_contract: TurnParseResult;
  decision: PolicyDecision;
  tool_payload?: ToolPayload | null;
  map_session?: MapSession | null;
  memory_snapshot: Record<string, JsonValue>;
  context_usage?: ContextUsage | null;
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
  credential_health?: Record<string, Record<string, 'healthy' | 'unreadable' | string>>;
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
