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
    attribution?: string;
}

export interface CatalogResponse {
    providers: CatalogProvider[];
    basemaps: CatalogBasemap[];
    overlays: CatalogOverlay[];
}

export interface MapSession {
    center?: { latitude?: number | null; longitude?: number | null };
    bounds?: number[];
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
    [key: string]: unknown;
}

export interface SearchResponse {
    status_message: string;
    payload: SearchResponsePayload;
    map_session?: MapSession;
    compliance_warnings?: string[];
    json?: unknown;
}
