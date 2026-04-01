import { API_BASE_URL } from '../constants';
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
                attribution: typeof item.attribution === 'string' ? item.attribution : undefined,
            })),
    };
};

export const searchLocation = async (payload: LocationSearchRequest): Promise<SearchResponse> => {
    try {
        const response = await fetch(`${API_BASE_URL}/maps/search`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ...payload,
                geospatial_layers: payload.filters,
            }),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            const detail = typeof errorData === 'object' && errorData !== null && 'detail' in errorData
                ? errorData.detail
                : errorData;
            const message = typeof detail === 'string'
                ? detail
                : `Error ${response.status}: ${response.statusText}`;
            throw new ApiRequestError(message, {
                detail,
                raw: errorData,
                status: response.status,
            });
        }

        const data: unknown = await response.json();
        return parseSearchResponse(data);
    } catch (error) {
        console.error('Search API Error:', error);
        throw error;
    }
};

export const fetchCatalog = async (): Promise<CatalogResponse> => {
    const response = await fetch(`${API_BASE_URL}/maps/catalog`, {
        method: 'GET',
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        const detail = typeof errorData === 'object' && errorData !== null && 'detail' in errorData
            ? errorData.detail
            : errorData;
        const message = typeof detail === 'string'
            ? detail
            : `Error ${response.status}: ${response.statusText}`;
        throw new ApiRequestError(message, {
            detail,
            raw: errorData,
            status: response.status,
        });
    }
    const data: unknown = await response.json();
    return parseCatalogResponse(data);
};
