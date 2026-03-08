import { API_BASE_URL } from '../constants';
import { LocationSearchRequest, SearchResponse, SearchResponsePayload, TableInfo, TableData } from '../types';

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

const parseTableInfo = (value: unknown): TableInfo | null => {
    if (!isRecord(value)) {
        return null;
    }
    const name = value.name;
    const displayName = value.displayName;
    if (typeof name !== 'string' || typeof displayName !== 'string') {
        return null;
    }
    return { name, displayName };
};

const parseTablesResponse = (value: unknown): TableInfo[] => {
    if (!isRecord(value) || !Array.isArray(value.tables)) {
        throw new Error('Failed to fetch tables');
    }

    const tables = value.tables.map(parseTableInfo);
    const invalidEntry = tables.find((table) => table === null);
    if (invalidEntry !== undefined) {
        throw new Error('Failed to parse tables payload');
    }

    return tables.filter((table): table is TableInfo => table !== null);
};

const isRowRecord = (value: unknown): value is Record<string, unknown> => isRecord(value);

const parseTableData = (value: unknown): TableData => {
    if (!isRecord(value)) {
        throw new Error('Failed to parse table data payload');
    }

    const tableName = value.tableName;
    const displayName = value.displayName;
    const columns = value.columns;
    const rows = value.rows;
    const rowCount = value.rowCount;
    const columnCount = value.columnCount;

    if (typeof tableName !== 'string' || typeof displayName !== 'string') {
        throw new Error('Failed to parse table metadata');
    }
    if (!Array.isArray(columns) || columns.some((column) => typeof column !== 'string')) {
        throw new Error('Failed to parse table columns');
    }
    if (!Array.isArray(rows) || rows.some((row) => !isRowRecord(row))) {
        throw new Error('Failed to parse table rows');
    }
    if (typeof rowCount !== 'number' || typeof columnCount !== 'number') {
        throw new Error('Failed to parse table stats');
    }

    return {
        tableName,
        displayName,
        columns,
        rows,
        rowCount,
        columnCount,
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

export const fetchTables = async (): Promise<TableInfo[]> => {
    const response = await fetch(`${API_BASE_URL}/browser/tables`);
    if (!response.ok) {
        throw new Error('Failed to fetch tables');
    }
    const data: unknown = await response.json();
    return parseTablesResponse(data);
};

export const fetchTableData = async (tableName: string): Promise<TableData> => {
    const normalizedName = tableName.trim();
    const response = await fetch(`${API_BASE_URL}/browser/tables/${encodeURIComponent(normalizedName)}`);
    if (!response.ok) {
        throw new Error('Failed to fetch table data');
    }
    const data: unknown = await response.json();
    return parseTableData(data);
};

export type { TableInfo, TableData } from '../types';
