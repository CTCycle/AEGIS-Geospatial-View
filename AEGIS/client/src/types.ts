export type JsonPrimitive = string | number | boolean | null;

export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];

export interface JsonObject {
    [key: string]: JsonValue;
}

export interface ApiErrorShape {
    message: string;
    detail?: unknown;
    status?: number;
    raw?: unknown;
}

export interface LocationSearchRequest {
    datetime?: string;
    time_of_day?: string;
    timeline_year?: number;
    country?: string;
    city?: string;
    address?: string;
    use_coordinates: boolean;
    latitude?: number;
    longitude?: number;
    filters?: string[];
    basemap_id?: string;
    overlay_ids?: string[];
    aoi?: {
        mode: 'radius' | 'bbox';
        radius_m?: number;
        bbox?: [number, number, number, number];
    };
    commute?: Record<string, JsonValue>;
    bbox?: number[];
    radius_m?: number;
    map_size_m?: number;
    map_tiles?: string;
    image_width?: number;
    image_height?: number;
    image_crs?: string;
    image_format?: string;
}

export interface CatalogProvider {
    id: string;
    name?: string;
    docs_url: string;
    commercial_notes: string;
    warning_level: 'low' | 'medium' | 'high' | string;
}

export interface CatalogBasemap {
    id: string;
    label: string;
    provider: string;
    type: 'tile' | string;
    tile_url?: string | null;
    attribution?: string;
    requires_key: boolean;
}

export interface CatalogOverlay {
    id: string;
    label: string;
    provider: string;
    type: 'tile' | 'wms' | 'wmts' | 'geojson' | 'point-insight' | string;
    default_opacity?: number;
    coverage?: string;
    requires_key: boolean;
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
}

export interface CatalogResponse {
    providers: CatalogProvider[];
    basemaps: CatalogBasemap[];
    overlays: CatalogOverlay[];
}

export interface MapSession {
    center?: { latitude?: number | null; longitude?: number | null };
    bounds?: [number, number, number, number] | number[];
    basemap?: CatalogBasemap;
    overlays?: CatalogOverlay[];
    insights?: Record<string, JsonValue>;
    compliance_warnings?: string[];
}

export interface SatelliteImageryPayload {
    image_base64?: string;
    mime?: string;
    map_html?: string;
    image_url?: string;
    wms_url?: string;
    format?: string;
    [key: string]: unknown;
}

export interface SearchResponsePayload {
    satellite_imagery?: SatelliteImageryPayload;
    map_session?: MapSession;
    compliance_warnings?: string[];
    latitude?: number;
    longitude?: number;
    coordinates?: {
        latitude?: number;
        longitude?: number;
    };
    [key: string]: unknown;
}

export interface SearchResponse {
    status_message: string;
    payload: SearchResponsePayload;
    map_session?: MapSession;
    compliance_warnings?: string[];
    json?: unknown;
}

export type ChatRole = 'user' | 'assistant' | 'system' | 'tool';

export interface ChatMessage {
    role: ChatRole;
    content: string;
    created_at?: string;
}

export interface ChatSession {
    id: number;
    title?: string;
    status?: string;
    messages?: ChatMessage[];
}

export interface StructuredSearchIntent {
    request_text?: string;
    location?: {
        name?: string | null;
        coordinates?: { latitude?: number; longitude?: number } | null;
        bbox?: [number, number, number, number] | null;
        granularity?: string | null;
        is_partial?: boolean;
        ambiguity_reason?: string | null;
    };
    map_preferences?: {
        map_type?: 'street' | 'satellite' | 'terrain' | 'light' | 'dark' | 'thematic' | 'auto' | string;
        map_type_confidence?: number;
        basemap_preference?: string | null;
        overlay_candidates?: string[];
    };
    task?: {
        user_intent?: string;
        scope?: 'concrete_area' | 'broad_but_usable_area' | 'missing_area' | 'requires_area_discovery' | string;
        requires_external_fact_finding?: boolean;
        is_geographically_actionable?: boolean;
    };
    temporal_context?: {
        raw_text?: string | null;
        normalized_datetime?: string | null;
        date_range?: [string, string] | null;
    };
    planning?: {
        confidence?: number;
        missing_information?: string[];
        should_execute_search?: boolean;
        follow_up_question?: string | null;
        fallback_mode?: string;
    };
}

export interface ChatTurnRequest {
    session_id?: number;
    title?: string;
    message: string;
    datetime?: string;
}

export interface ChatTurnResponse {
    session_id: number;
    assistant_message: string;
    structured_intent?: StructuredSearchIntent | null;
    extracted_state?: Record<string, JsonValue> | null;
    map_session?: MapSession | null;
    tool_payload?: Record<string, JsonValue> | null;
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
