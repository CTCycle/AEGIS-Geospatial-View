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

export interface CapabilityDescriptor {
  id: string;
  name: string;
  kind: CapabilityKind | 'overlay' | 'tool' | string;
  type?: string;
  description?: string;
  provider: string;
  requires_credentials: boolean;
  is_available: boolean;
  availability_reason?: string | null;
  supports_map: boolean;
  supports_direct_text: boolean;
  coverage: string;
  action_tags: string[];
  task_tags: string[];
  source_protocol?: string;
  data_format?: string;
  geometry_type?: string;
  queryable?: boolean;
  endpoint_health?: string;
  auth_mode?: string;
  official_docs_url?: string;
  capability_kind?: CapabilityKind | string;
  rendering_mode?: RenderingMode | string;
  reliability?: LayerReliability;
  auth?: ProviderAuthPolicy;
  metadata?: Record<string, JsonValue>;
  render?: {
    status?: 'available' | 'unavailable' | 'checking' | string;
    tile_url?: string | null;
    style_url?: string | null;
    attribution?: string;
    reason?: string;
  };
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

export interface GeospatialLayerRenderDescriptor {
  provider: string;
  layer_id: string;
  rendering_mode: RenderingMode | string;
  source_protocol: string;
  url?: string | null;
  tile_url_template?: string | null;
  crs?: string | null;
  format?: string | null;
  style?: string | null;
  time?: string | null;
  default_time?: string | null;
  tile_matrix_set?: string | null;
  tile_size?: number | null;
  min_zoom?: number | null;
  max_zoom?: number | null;
  attribution?: string[];
  attribution_url?: string | null;
  warnings?: string[];
}

export interface GeospatialProviderLayerDescriptor {
  provider: string;
  layer_id: string;
  title: string;
  abstract?: string | null;
  rendering_mode: RenderingMode | string;
  source_protocol: string;
  data_format: string;
  geometry_type: string;
  queryable: boolean;
  crs: string[];
  formats: string[];
  styles: string[];
  time_extent?: string | null;
  default_time?: string | null;
  tile_matrix_sets: string[];
  render?: GeospatialLayerRenderDescriptor | null;
  attribution: string[];
  warnings: string[];
}

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

export interface InspectionField {
  key: string;
  label: string;
  value: string | number | boolean | null;
  unit?: string | null;
  category?: string;
  source_url?: string | null;
  order?: number;
}

export interface MapInspection {
  inspection_id: string;
  title: string;
  association: 'feature' | 'location' | 'overlay' | 'non_spatial' | string;
  provider?: string | null;
  feature_id?: string | null;
  fields: InspectionField[];
  source_url?: string | null;
  freshness?: string | null;
  stale?: boolean;
  warnings?: string[];
  geometry?: Record<string, JsonValue> | null;
}

export interface OverlayInstance {
  instance_id: string;
  capability_id: string;
  label: string;
  provider: string;
  overlay_type: string;
  rendering_mode: string;
  scope_key: string;
  scope: Record<string, JsonValue>;
  resolved_location?: ResolvedLocation | null;
  viewport?: ViewportPolicy | Record<string, JsonValue> | null;
  visible: boolean;
  opacity: number;
  render_variant: Record<string, string | null>;
  descriptor: Record<string, JsonValue>;
  inspections: MapInspection[];
}

export interface OverlayCollectionState {
  collection_id: string;
  revision: number;
  instances: OverlayInstance[];
}

export interface OverlayMutationResult {
  collection_id: string;
  revision: number;
  added_instance_ids: string[];
  removed_instance_ids: string[];
  updated_instance_ids: string[];
  unmatched_selectors: string[];
  ambiguous_selectors: string[];
  clarification?: string | null;
}


export type GeospatialProviderAutomationSupport =
  | 'manual_only'
  | 'guided_playwright'
  | 'agent_assisted'
  | 'unsupported';

export interface GeospatialProviderSignupField {
  key: string;
  label: string;
  fieldType: 'text' | 'email' | 'textarea' | 'select';
  required: boolean;
  sensitive: boolean;
  helpText?: string | null;
}

export interface GeospatialProviderSignupAutomation {
  support: GeospatialProviderAutomationSupport;
  signupUrl?: string | null;
  developerPortalUrl?: string | null;
  docsUrl?: string | null;
  requiredFields: GeospatialProviderSignupField[];
  userActionNotes: string[];
  safetyNotes: string[];
  experimental: boolean;
  experimentalLabel: string;
}

export interface GeospatialProviderAccountSetup {
  providerId: string;
  name: string;
  requiresCredentials: boolean;
  authMode: string;
  docsUrl?: string | null;
  configured: boolean;
  instructions: string[];
  automation: GeospatialProviderSignupAutomation;
  credentialStorageKey: string;
  credentialLabel: string;
  keyFormatHint?: string | null;
  validationSupported: boolean;
}

export interface GeospatialProviderAccountSetupListResponse {
  providers: GeospatialProviderAccountSetup[];
}

export interface GeospatialCredentialStatus {
  provider: string;
  required: boolean;
  configured: boolean;
}

export interface GeospatialProviderPayload {
  status: 'ok' | 'missing-credential' | 'unavailable' | string;
  provider: string;
  payload?: Record<string, JsonValue>;
  attribution?: string[];
  warnings?: string[];
  stale?: boolean;
  message?: string;
  result_status?: string | null;
  result_type?: string | null;
  fetched_at?: string | null;
  observation_time?: string | null;
  coverage?: Record<string, JsonValue> | null;
  spatial_resolution?: string | null;
  units?: Record<string, string>;
  source_url?: string | null;
  partial?: boolean;
}

export interface MapOverlayEntry {
  id: string;
  instance_id?: string;
  capability_id?: string;
  label: string;
  provider: string;
  type: string;
  rendering_mode?: RenderingMode | string;
  default_opacity?: number;
  visible?: boolean;
  url?: string | null;
  tile_url_template?: string;
  layers?: string;
  layer_id?: string;
  source_layer?: string;
  tile_matrix_set?: string;
  tile_size?: number;
  min_zoom?: number;
  max_zoom?: number;
  bounds?: [number, number, number, number];
  attribution?: string;
  attribution_url?: string | null;
  source_protocol?: string;
  data_format?: string;
  geometry_type?: string;
  crs?: string | null;
  format?: string | null;
  style?: string | null;
  time?: string | null;
  default_time?: string | null;
  result_status?: string | null;
  fetched_at?: string | null;
  observation_time?: string | null;
  coverage?: Record<string, JsonValue> | null;
  spatial_resolution?: string | null;
  units?: Record<string, string>;
  source_url?: string | null;
  partial?: boolean;
  stale?: boolean;
  requested_variables?: string[];
  request_parameters?: Record<string, JsonValue>;
  warnings?: string[];
  render?: GeospatialLayerRenderDescriptor | null;
  data?: GeoJsonFeatureCollection;
  inspections?: MapInspection[];
}

export interface MapSession {
  session_id: string;
  resolved_location: ResolvedLocation;
  basemap_id: string;
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
    style_url?: string | null;
    attribution?: string;
    render_status?: 'available' | 'unavailable' | 'checking' | string;
    unavailable_reason?: string | null;
  };
  compliance_warnings?: string[];
  overlay_collection: OverlayCollectionState;
  presentation?: PresentationStatus | null;
}

export type PresentationStatus =
  | 'not_required'
  | 'not_requested'
  | 'pending'
  | 'prepared'
  | 'prepared_unverified'
  | 'ready'
  | 'failed'
  | 'render_timeout';

export interface RenderRequirement {
  name: string;
  required: boolean;
  status: 'pending' | 'satisfied' | 'failed' | 'not_applicable';
  target_id?: string | null;
  evidence_ref?: string | null;
  failure_code?: string | null;
}

export interface MapRenderAcknowledgement {
  run_id: string;
  run_version: number;
  map_session_id: string;
  collection_revision: number;
  status: 'ready' | 'failed';
  viewport_bounds?: number[] | null;
  checks: Record<string, boolean>;
  overlay_results: Array<Record<string, JsonValue>>;
  failure_code?: string | null;
  failure_stage?: string | null;
  failure_summary?: string | null;
}

/** Bounded browser evidence fed back into the native agent run. */
export interface RenderObservation {
  map_session_id: string;
  collection_revision: number;
  attempt: number;
  status: 'ready' | 'failed';
  viewport_bounds?: [number, number, number, number] | null;
  checks: Record<string, boolean>;
  overlay_results: Array<Record<string, JsonValue>>;
  failure_code?: string | null;
  failure_stage?: string | null;
  failure_summary?: string | null;
  fingerprint?: string | null;
  action_fingerprint?: string | null;
  recovery: 'continue' | 'revise_map' | 'alternate_source' | 'terminal';
  observed_at?: string | null;
}

export interface GeoJsonFeatureCollection {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    id?: string | number;
    geometry: JsonObject | null;
    properties?: JsonObject | null;
  }>;
}

export interface SearchResponsePayload {
  map_session?: MapSession;
  compliance_warnings?: string[];
}

export interface OverlayStateChange {
  overlayVisibility: Record<string, boolean>;
  overlayOpacity: Record<string, number>;
}

export interface OverlayRenderStatus {
  overlayId: string;
  status: 'pending' | 'loaded' | 'failed' | 'metadata-only' | 'no-results';
  message?: string;
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
  kind?: 'normal' | 'steering' | 'system_progress';
  runVersion?: number;
}

export type AgentRunState =
  | 'pending'
  | 'running'
  | 'updating'
  | 'waiting_for_clarification'
  | 'awaiting_render'
  | 'completed'
  | 'failed'
  | 'cancelled';

/**
 * A small, run-scoped task projection.  Task state is operational UI data;
 * it is deliberately separate from provider messages and never contains
 * hidden model reasoning.
 */
export type AgentTaskStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'failed'
  | 'blocked'
  | 'cancelled'
  | 'superseded';

export interface CompletionRequirement {
  name: string;
  required: boolean;
  status: 'pending' | 'satisfied' | 'failed' | 'not_applicable';
  target_id?: string | null;
  evidence_ref?: string | null;
  failure_code?: string | null;
}

export interface AgentTask {
  id: string;
  task_id?: string;
  description: string;
  status: AgentTaskStatus;
  parent_task_id?: string | null;
  dependencies?: string[];
  result?: Record<string, JsonValue> | null;
  failure_code?: string | null;
  requirement_name?: string | null;
  target_id?: string | null;
}

export interface AgentTaskState {
  run_id?: string | null;
  root_task_id?: string;
  current_iteration?: number;
  max_iterations?: number;
  active_task_id?: string | null;
  status?: AgentTaskStatus;
  tasks: AgentTask[];
  completion_requirements?: CompletionRequirement[];
  unresolved_requirements?: string[];
}

export type RunEventType =
  | 'progress'
  | 'context_usage'
  | 'assistant_text_delta'
  | 'assistant_text_completed'
  | 'tool_started'
  | 'tool_completed'
  | 'request_updated'
  | 'error'
  | 'completed'
  | 'cancelled'
  | 'clarification_needed'
  | 'trace'
  | 'checkpoint'
  | 'map_prepared'
  | 'render_observed';

export type RunEventVisibility = 'user' | 'internal';

export interface RunEvent {
  event_id: string;
  sequence: number;
  conversation_id: string;
  run_id: string;
  run_version: number;
  type: RunEventType;
  timestamp: string;
  visibility: RunEventVisibility;
  payload: Record<string, JsonValue>;
}

export interface ConversationCreateRequest {
  title?: string | null;
}

export interface ConversationCreateResponse {
  conversation_id: string;
  title?: string | null;
}

export interface ActiveConversationRunSnapshot {
  run_id: string;
  run_version: number;
  state: AgentRunState;
  presentation_status?: PresentationStatus;
  presentation?: Record<string, JsonValue> | null;
  task_state?: AgentTaskState | null;
  current_iteration?: number | null;
  max_iterations?: number | null;
}

export interface ConversationRunSummary {
  conversation_id?: string;
  run_id: string;
  original_request?: string;
  aggregated_request?: string;
  run_version?: number;
  active_run_version?: number;
  state: AgentRunState;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  request_timezone?: string | null;
  cancel_requested_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  presentation_status?: PresentationStatus;
  presentation?: Record<string, JsonValue> | null;
  task_state?: AgentTaskState | null;
  current_iteration?: number | null;
  max_iterations?: number | null;
}

export interface ConversationSummary {
  conversation_id: string;
  title?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  message_count?: number;
  last_message_preview?: string | null;
  active_run?: ActiveConversationRunSnapshot | null;
  latest_run?: ConversationRunSummary | null;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
  next_cursor?: string | null;
}

/** Safe, operational fields returned by the run-trace inspection endpoint. */
export interface RunTraceEntry {
  event_id: string;
  sequence: number;
  run_id: string;
  run_version: number;
  kind: string;
  timestamp: string;
  task_id?: string | null;
  tool_name?: string | null;
  call_id?: string | null;
  iteration?: number | null;
  label?: string | null;
  status?: string | null;
  summary?: string | null;
  duration_ms?: number | null;
  evidence_refs: string[];
  retryable?: boolean | null;
  error?: string | null;
}

export interface RunTraceResponse {
  conversation_id: string;
  run_id: string;
  entries: RunTraceEntry[];
  next_cursor?: string | null;
}

export type ToolProgressStatus = 'running' | 'success' | 'valid_empty' | 'partial' | 'failed';

export interface ToolProgressItem {
  call_id: string;
  tool_name: string;
  status: ToolProgressStatus;
  label?: string;
  task_id?: string | null;
  iteration?: number | null;
  summary?: string | null;
  duration_ms?: number | null;
  evidence_refs?: string[];
  error?: string | null;
  started_at?: string;
  completed_at?: string;
}

export interface ConversationSnapshotResponse {
  conversation_id: string;
  title?: string | null;
  context_revision: number;
  messages: ChatMessage[];
  conversation_state: ConversationState;
  memory_snapshot: Record<string, JsonValue>;
  map_session?: MapSession | null;
  active_run?: ActiveConversationRunSnapshot | null;
  recent_runs?: ConversationRunSummary[];
}

/** Response returned when the direct chat request is accepted asynchronously. */
export interface AgentRunAcceptedResponse {
  conversation_id: string;
  run_id: string;
  run_version: number;
  state: AgentRunState;
  presentation_status: PresentationStatus;
  status_url: string;
  realtime_url?: string | null;
  terminal: boolean;
}

export interface AgentRunSnapshot {
  conversation_id: string;
  run_id: string;
  original_request: string;
  aggregated_request: string;
  active_run_version: number;
  state: AgentRunState;
  created_at: string;
  request_timezone?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  cancel_requested_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  presentation_status: PresentationStatus;
  presentation?: Record<string, JsonValue> | null;
  response?: ChatTurnResponse | null;
  current_iteration?: number | null;
  task_state?: AgentTaskState | null;
}

export interface ChatTurnRequest {
  conversation_id: string;
  title?: string;
  message: string;
  datetime?: string;
  timezone?: string;
  request_id?: string;
}

export interface ContextUsage {
  estimated_input_tokens: number;
  reported_input_tokens?: number | null;
  reported_output_tokens?: number | null;
  selected_context_window?: number | null;
  model_context_limit?: number | null;
  usage_percent: number | null;
  provider: string;
  model: string;
  reserved_output_tokens?: number;
  tool_schema_tokens?: number;
  response_schema_tokens?: number;
  safety_margin_tokens?: number;
  usage_source?: 'not_measured' | 'estimated' | 'provider_reported' | 'hybrid' | string;
  phases?: Record<string, unknown>;
  peak_request_tokens?: number | null;
  total_input_tokens?: number | null;
  total_output_tokens?: number | null;
  usable_prompt_budget_tokens?: number | null;
  current_conversation_tokens?: number | null;
  expected_output_tokens?: number | null;
  context_profile_source?: string;
  compaction_applied?: boolean;
}

export interface AgentTemporalScope {
  mode: 'current' | 'historical' | 'forecast' | 'none';
  reference_time_iso?: string | null;
  start_time_iso?: string | null;
  end_time_iso?: string | null;
  granularity: string;
  aggregation: string;
}

export interface AgentSpatialScope {
  kind: 'point' | 'bbox' | 'radius' | 'administrative_geometry' | 'feature_geometry' | 'viewport';
  relationship: 'at' | 'in' | 'near' | 'around' | 'within_distance' | 'along' | 'visible_area' | 'here';
  target_refs: string[];
  distance_m?: number | null;
}

export interface AgentGoal {
  goal: string;
  task_mode: 'answer' | 'execute' | 'clarify';
  presentation: 'text' | 'map' | 'both';
  operation: string;
  requires_location: boolean;
  target_ids: string[];
  temporal_scope: Record<string, JsonValue>;
  spatial_scope: Array<Record<string, JsonValue>>;
  filters: Record<string, JsonValue>;
}

export interface CompletionContract {
  operation: string;
  requirements: string[];
  data_requirement?: 'none' | 'provider_data';
  location_required: boolean;
  evidence_required: boolean;
  map_preparation_required: boolean;
  temporal_scope_required: boolean;
  spatial_scope_required: boolean;
  render_verification_required?: boolean;
  render_verified?: boolean;
}

export interface ConversationDirective {
  directive: string;
  value?: JsonValue;
  source?: string;
  active?: boolean;
  created_at_turn?: number;
}

export interface PendingClarification {
  question: string;
  source_turn_index: number;
  source_request_id?: string | null;
  scope: 'current_request';
  scope_terms: string[];
  kind?: 'generic' | 'infrastructure_subtype';
  options?: string[];
  selected_option?: string | null;
  status: 'active' | 'deferred' | 'answered';
}

export interface ConversationState {
  schema_version: 2;
  conversation_id: string;
  revision: number;
  active_directives: Array<Record<string, JsonValue>>;
  summary?: Record<string, JsonValue> | null;
  goal?: AgentGoal | null;
  route?: NativeCapabilityRoute | null;
  constraints: Record<string, JsonValue>;
  resolved_locations: Record<string, ResolvedLocation>;
  evidence_refs: string[];
  committed_map_session?: MapSession | null;
  pending_clarification?: PendingClarification | null;
}

export interface ChatOperationResult {
  kind: 'map_session' | 'direct_answer' | 'capability_catalog' | 'clarification' | 'rejection' | 'error';
  status: 'success' | 'partial' | 'pending' | 'failed';
  message: string;
  warnings?: string[];
  direct_result?: Record<string, JsonValue> | null;
  provider_error?: Record<string, JsonValue> | null;
  failure_category?: 'model_capability' | 'provider_api' | 'provider_failure' | 'schema_definition' | 'response_parsing' | 'context_limit' | 'insufficient_evidence' | 'model_budget_exhausted' | 'tool_budget_exhausted' | 'transition_budget_exhausted' | 'iteration_budget_exhausted' | 'run_deadline_exhausted' | 'no_progress' | 'cancelled' | 'superseded' | null;
}

export type RealtimeConnectionState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'
  | 'failed';

export interface RealtimeServerMessage {
  protocol_version: number;
  type: string;
  message_id?: string | null;
  correlation_id?: string | null;
  conversation_id: string;
  payload: JsonObject;
}

export interface NativeToolResultSummary {
  call_id: string;
  tool_name: string;
  status: 'success' | 'valid_empty' | 'partial' | 'failed';
  summary: string;
  evidence_refs: string[];
  map_candidate_id?: string | null;
  error?: Record<string, JsonValue> | null;
}

export interface NativeCapabilityRoute {
  primary_domain: string;
  secondary_domains: string[];
  task_mode: 'answer' | 'execute' | 'clarify';
  presentation: 'text' | 'map' | 'both';
  requires_location: boolean;
  capability_queries: string[];
  explicit_capability_ids: string[];
  clarification_question?: string | null;
  operation?: string | null;
  target_refs: string[];
  temporal_scope: AgentTemporalScope;
  spatial_scope?: AgentSpatialScope | null;
  filters: Record<string, JsonValue>;
}

export interface ChatTurnResponse {
  conversation_id: string;
  request_id: string;
  assistant_message: string;
  operation: ChatOperationResult;
  tool_payload?: Record<string, unknown> | null;
  map_session?: MapSession | null;
  memory_snapshot: Record<string, JsonValue>;
  context_usage?: ContextUsage | null;
  context_revision: number;
  execution_trace?: Record<string, JsonValue> | null;
  route?: NativeCapabilityRoute | null;
  goal?: AgentGoal | null;
  completion_contract?: CompletionContract | null;
  presentation_status: PresentationStatus;
  tool_results: NativeToolResultSummary[];
  conversation_state?: ConversationState | null;
  task_state?: AgentTaskState | null;
}

export type ChatTurnApiResponse = ChatTurnResponse | AgentRunAcceptedResponse;

export type ChatStreamEventType =
  | 'status'
  | 'context_usage'
  | 'tool_call_started'
  | 'tool_call_completed'
  | 'map_session_created'
  | 'stage'
  | 'final'
  | 'error';

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
  supports_tools?: boolean | null;
  supports_structured_output?: boolean | null;
  supports_vision?: boolean | null;
  supports_embeddings?: boolean | null;
  tool_support_source?: string;
  protocol?: string | null;
  agent_selection_disabled_reason?: string | null;
  context_window_tokens?: number | null;
  maximum_output_tokens?: number | null;
  context_profile_source?: string;
  metadata: Record<string, JsonValue>;
}

export interface ModelLibrarySourceStatus {
  ok: boolean;
  reachable?: boolean | null;
  stale?: boolean;
  message?: string | null;
  model_count?: number | null;
  structured_probe_status?: StructuredProbeStatus;
  structured_probe_checked_at?: string | null;
  structured_probe_expires_at?: string | null;
}

export type StructuredProbeStatus = 'not_tested' | 'passed' | 'failed' | 'timeout' | 'unsupported';

export interface StructuredProbeResponse {
  provider: string;
  model: string;
  protocol: string;
  status: StructuredProbeStatus;
  parse_status: string;
  duration_ms: number | null;
  checked_at: string | null;
  expires_at: string | null;
  message: string | null;
}

export interface ModelLibraryResponse {
  cloud: ModelCardDescriptor[];
  local: ModelCardDescriptor[];
  sources: Record<string, ModelLibrarySourceStatus>;
}

export interface ModelSettingsResponse {
  active_provider_mode: ModelProviderMode;
  agent_model_provider: string;
  agent_model_name: string;
  ollama_url: string;
  openai_base_url?: string | null;
  google_base_url?: string | null;
  deepseek_base_url?: string | null;
  credentials: Record<string, Record<string, boolean>>;
  credential_health?: Record<string, Record<string, 'healthy' | 'unreadable' | string>>;
  selected_model_context: SelectedModelContext;
}

export interface SelectedModelContext {
  provider: string;
  model: string;
  context_window_tokens: number | null;
  maximum_output_tokens: number | null;
  context_profile_source: string;
}

export interface ModelSettingsUpdateRequest {
  active_provider_mode?: ModelProviderMode;
  agent_model_provider?: string;
  agent_model_name?: string;
  ollama_url?: string;
  openai_base_url?: string | null;
  google_base_url?: string | null;
  deepseek_base_url?: string | null;
  credentials: Record<string, { api_key?: string }>;
}

export interface OllamaHealthResponse {
  ok: boolean | null;
  detail: string | null;
  [key: string]: unknown;
}

export interface GenericObjectResponse {
  [key: string]: unknown;
}
