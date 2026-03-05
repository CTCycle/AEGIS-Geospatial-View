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
    bbox?: number[];
    radius_m?: number;
    map_size_m?: number;
    map_tiles?: string;
    image_width?: number;
    image_height?: number;
    image_crs?: string;
    image_format?: string;
    agentic_enabled?: boolean;
    agent_prompt?: string;
    llm_provider?: string;
    cloud_model?: string;
    agent_model?: string;
    temperature?: number;
    reasoning?: boolean;
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
    [key: string]: unknown;
}

export interface SearchResponse {
    status_message: string;
    payload: SearchResponsePayload;
    json?: unknown;
}

export interface RuntimeSettings {
    useCloudServices: boolean;
    provider: string;
    cloudModel: string;
    agentModel: string;
}

export interface AgenticConfig {
    enabled: boolean;
    objective: string;
}

export interface TableInfo {
    name: string;
    displayName: string;
}

export interface TableData {
    tableName: string;
    displayName: string;
    columns: string[];
    rows: Record<string, unknown>[];
    rowCount: number;
    columnCount: number;
}
