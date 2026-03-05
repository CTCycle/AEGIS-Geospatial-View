import { API_BASE_URL } from '../constants';
import { LocationSearchRequest, SearchResponse, TableInfo, TableData } from '../types';

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

        return response.json();
    } catch (error) {
        console.error('Search API Error:', error);
        throw error;
    }
};

export const fetchTables = async (): Promise<TableInfo[]> => {
    const response = await fetch(`${API_BASE_URL}/browser/tables`);
    if (!response.ok) {
        throw new Error('Failed to fetch tables');
    }
    const data = await response.json();
    return data.tables;
};

export const fetchTableData = async (tableName: string): Promise<TableData> => {
    const normalizedName = tableName.trim();
    const response = await fetch(`${API_BASE_URL}/browser/tables/${encodeURIComponent(normalizedName)}`);
    if (!response.ok) {
        throw new Error('Failed to fetch table data');
    }
    return response.json();
};

export type { TableInfo, TableData } from '../types';
