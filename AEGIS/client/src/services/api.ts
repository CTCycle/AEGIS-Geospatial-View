import { API_BASE_URL } from '../constants';
import { LocationSearchRequest, SearchResponse, TableInfo, TableData } from '../types';

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

// Re-export types for convenience
export type { TableInfo, TableData } from '../types';
