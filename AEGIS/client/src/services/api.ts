import { API_BASE_URL } from '../constants';
import { LocationSearchRequest, SearchResponse, SearchResponsePayload } from '../types';

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
        json: value.json,
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
