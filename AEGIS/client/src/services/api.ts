import { LocationSearchRequest, SearchResponse } from '../types';

const API_BASE_URL = '/api/maps';

export const searchLocation = async (payload: LocationSearchRequest): Promise<SearchResponse> => {
    try {
        const response = await fetch(`${API_BASE_URL}/search`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ...payload,
                geospatial_layers: payload.filters, // Map filters to geospatial_layers expected by backend
            }),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            const message = typeof errorData.detail === 'string'
                ? errorData.detail
                : `Error ${response.status}: ${response.statusText}`;
            const error: Error & { detail?: unknown; status?: number; raw?: unknown } = new Error(message);
            error.detail = errorData.detail ?? errorData;
            error.raw = errorData;
            error.status = response.status;
            throw error;
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Search API Error:', error);
        throw error;
    }
};
