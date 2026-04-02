import {
    API_BASE_URL,
    API_MAPS_CATALOG_PATH,
    API_MAPS_SEARCH_PATH,
} from '../constants';
import {
    CatalogResponse,
    LocationSearchRequest,
    SearchResponse,
    SearchResponsePayload,
} from '../types';

class ApiRequestError extends Error {
    detail?: unknown;
    status?: number;
    raw?: unknown;

    constructor(message: string, options?: { detail?: unknown; status?: number; raw?: unknown }) {
        super(message);
        this.name = 'ApiRequestError';
        this.detail = options?.detail;
        this.status = options?.status;
        this.raw = options?.raw;
    }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null;

const parseSearchResponse = (value: unknown): SearchResponse => {
    if (!isRecord(value)) {
        throw new Error('Unexpected search response format');
    }

    const statusMessage = value.status_message;
    if (typeof statusMessage !== 'string') {
        throw new Error('Search response is missing status_message');
    }

    const payloadCandidate = value.payload;
    const payload: SearchResponsePayload = isRecord(payloadCandidate) ? payloadCandidate : {};

    return {
        status_message: statusMessage,
        payload,
        map_session: isRecord(value.map_session) ? value.map_session : undefined,
        compliance_warnings: Array.isArray(value.compliance_warnings)
            ? value.compliance_warnings.filter((item): item is string => typeof item === 'string')
            : undefined,
        json: value.json,
    };
};

const parseCatalogResponse = (value: unknown): CatalogResponse => {
    if (!isRecord(value)) {
        throw new Error('Unexpected catalog response format');
    }
    const providers = Array.isArray(value.providers) ? value.providers : [];
    const basemaps = Array.isArray(value.basemaps) ? value.basemaps : [];
    const overlays = Array.isArray(value.overlays) ? value.overlays : [];
    return {
        providers: providers
            .filter((item): item is Record<string, unknown> => isRecord(item) && typeof item.id === 'string')
            .map((item) => ({
                id: String(item.id),
                name: typeof item.name === 'string' ? item.name : undefined,
                docs_url: typeof item.docs_url === 'string' ? item.docs_url : '',
                commercial_notes: typeof item.commercial_notes === 'string' ? item.commercial_notes : '',
                warning_level: typeof item.warning_level === 'string' ? item.warning_level : 'low',
            })),
        basemaps: basemaps
            .filter((item): item is Record<string, unknown> => isRecord(item) && typeof item.id === 'string')
            .map((item) => ({
                id: String(item.id),
                label: typeof item.label === 'string' ? item.label : String(item.id),
                provider: typeof item.provider === 'string' ? item.provider : 'unknown',
                type: typeof item.type === 'string' ? item.type : 'tile',
                tile_url: typeof item.tile_url === 'string' ? item.tile_url : null,
                attribution: typeof item.attribution === 'string' ? item.attribution : undefined,
                requires_key: Boolean(item.requires_key),
            })),
        overlays: overlays
            .filter((item): item is Record<string, unknown> => isRecord(item) && typeof item.id === 'string')
            .map((item) => ({
                id: String(item.id),
                label: typeof item.label === 'string' ? item.label : String(item.id),
                provider: typeof item.provider === 'string' ? item.provider : 'unknown',
                type: typeof item.type === 'string' ? item.type : 'tile',
                default_opacity: typeof item.default_opacity === 'number' ? item.default_opacity : undefined,
                coverage: typeof item.coverage === 'string' ? item.coverage : undefined,
                requires_key: Boolean(item.requires_key),
                url: typeof item.url === 'string' ? item.url : null,
                layers: typeof item.layers === 'string' ? item.layers : undefined,
                layer_id: typeof item.layer_id === 'string' ? item.layer_id : undefined,
                tile_matrix_set: typeof item.tile_matrix_set === 'string' ? item.tile_matrix_set : undefined,
                wmts_format: typeof item.wmts_format === 'string' ? item.wmts_format : undefined,
                wmts_style: typeof item.wmts_style === 'string' ? item.wmts_style : undefined,
                wms_version: typeof item.wms_version === 'string' ? item.wms_version : undefined,
                wms_exceptions: typeof item.wms_exceptions === 'string' ? item.wms_exceptions : undefined,
                bounds: Array.isArray(item.bounds) && item.bounds.length === 4
                    && item.bounds.every((value) => typeof value === 'number')
                    ? item.bounds as [number, number, number, number]
                    : undefined,
                attribution: typeof item.attribution === 'string' ? item.attribution : undefined,
            })),
    };
};

export const searchLocation = async (payload: LocationSearchRequest): Promise<SearchResponse> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_MAPS_SEARCH_PATH}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            ...payload,
            geospatial_layers: payload.filters,
        }),
    });
    return parseSearchResponse(data);
};

export const fetchCatalog = async (): Promise<CatalogResponse> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_MAPS_CATALOG_PATH}`, {
        method: 'GET',
    });
    return parseCatalogResponse(data);
};

const executeApiRequest = async (url: string, init: RequestInit): Promise<unknown> => {
    const response = await fetch(url, init);
    if (!response.ok) {
        throw await buildApiError(response);
    }
    return response.json();
};

const buildApiError = async (response: Response): Promise<ApiRequestError> => {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = typeof errorData === 'object' && errorData !== null && 'detail' in errorData
        ? errorData.detail
        : errorData;
    const message = typeof detail === 'string'
        ? detail
        : `Error ${response.status}: ${response.statusText}`;
    return new ApiRequestError(message, {
        detail,
        raw: errorData,
        status: response.status,
    });
};
