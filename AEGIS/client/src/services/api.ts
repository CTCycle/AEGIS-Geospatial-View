import {
    API_BASE_URL,
    API_CHAT_MODELS_PATH,
    API_CHAT_SETTINGS_PATH,
    API_CHAT_STREAM_PATH,
    API_CHAT_TURN_PATH,
    API_MAPS_CATALOG_PATH,
    API_MAPS_SEARCH_PATH,
    API_OLLAMA_HEALTH_PATH,
    API_OLLAMA_PULL_PATH,
    API_OLLAMA_REFRESH_PATH,
    API_VECTOR_REBUILD_PATH,
} from '../constants';
import {
    CatalogResponse,
    ChatStreamEvent,
    ChatTurnRequest,
    ChatTurnResponse,
    LocationSearchRequest,
    ModelCardDescriptor,
    ModelSettingsUpdateRequest,
    ModelSettingsResponse,
    JsonValue,
    SearchResponse,
    SearchResponsePayload,
    VectorizationResponse,
} from '../types';
import { clearPersistedAppState } from '../state/appState';

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

const parseChatTurnResponse = (value: unknown): ChatTurnResponse => {
    if (!isRecord(value)) {
        throw new Error('Unexpected chat response format');
    }
    return {
        session_id: Number(value.session_id ?? 0),
        assistant_message: String(value.assistant_message ?? ''),
        structured_intent: isRecord(value.structured_intent) ? value.structured_intent : undefined,
        map_session: isRecord(value.map_session) ? value.map_session : undefined,
        tool_payload: isRecord(value.tool_payload) ? value.tool_payload as Record<string, JsonValue> : undefined,
        follow_up_required: Boolean(value.follow_up_required),
        fallback_mode: typeof value.fallback_mode === 'string' ? value.fallback_mode : undefined,
    };
};

export const sendChatTurn = async (payload: ChatTurnRequest): Promise<ChatTurnResponse> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_TURN_PATH}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    return parseChatTurnResponse(data);
};

export const streamChatTurn = async (
    payload: ChatTurnRequest,
    onEvent: (event: ChatStreamEvent) => void,
): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}${API_CHAT_STREAM_PATH}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw await buildApiError(response);
    }
    if (!response.body) {
        return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const chunk = await reader.read();
        if (chunk.done) {
            break;
        }
        buffer += decoder.decode(chunk.value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) {
                continue;
            }
            let parsed: ChatStreamEvent | null = null;
            try {
                parsed = JSON.parse(trimmed) as ChatStreamEvent;
            } catch {
                // ignore malformed event chunks
                continue;
            }
            onEvent(parsed);
            if (parsed.event === 'error') {
                const detail = String(parsed.data.message ?? 'Streaming request failed');
                const statusValue = parsed.data.status;
                const statusCode = typeof statusValue === 'number' ? statusValue : undefined;
                throw new ApiRequestError(detail, { detail: parsed.data, status: statusCode, raw: parsed.data });
            }
        }
    }
    const trailing = buffer.trim();
    if (trailing) {
        let parsed: ChatStreamEvent | null = null;
        try {
            parsed = JSON.parse(trailing) as ChatStreamEvent;
        } catch {
            // ignore malformed trailing chunks
        }
        if (parsed) {
            onEvent(parsed);
            if (parsed.event === 'error') {
                const detail = String(parsed.data.message ?? 'Streaming request failed');
                const statusValue = parsed.data.status;
                const statusCode = typeof statusValue === 'number' ? statusValue : undefined;
                throw new ApiRequestError(detail, { detail: parsed.data, status: statusCode, raw: parsed.data });
            }
        }
    }
};

export const fetchChatModels = async (): Promise<{ cloud: ModelCardDescriptor[]; local: ModelCardDescriptor[] }> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_MODELS_PATH}`, { method: 'GET' });
    const value = isRecord(data) ? data : {};
    const buildDescription = (item: Record<string, unknown>): string => {
        const rawDescription = String(item.description ?? '').trim();
        if (rawDescription && !rawDescription.toLowerCase().startsWith('local ollama model ')) {
            return rawDescription;
        }
        const metadata = isRecord(item.metadata) ? item.metadata : {};
        const family = typeof metadata.family === 'string' ? metadata.family : '';
        const parameterSize = typeof metadata.parameter_size === 'string' ? metadata.parameter_size : '';
        const quantization = typeof metadata.quantization_level === 'string' ? metadata.quantization_level : '';
        const details = [family, parameterSize, quantization].filter(Boolean).join(' ');
        return details ? `Optimized for ${details}.` : rawDescription || 'General purpose local model.';
    };

    const normalize = (input: unknown): ModelCardDescriptor[] => {
        if (!Array.isArray(input)) {
            return [];
        }
        return input
            .filter((item): item is Record<string, unknown> => isRecord(item))
            .map((item) => ({
                id: String(item.id ?? item.name ?? ''),
                name: String(item.name ?? item.id ?? ''),
                description: buildDescription(item),
                provider: String(item.provider ?? ''),
                capabilities: Array.isArray(item.capabilities)
                    ? item.capabilities.filter((entry): entry is string => typeof entry === 'string')
                    : [],
                metadata: isRecord(item.metadata) ? item.metadata as Record<string, JsonValue> : {},
            }));
    };
    return {
        cloud: normalize(value.cloud),
        local: normalize(value.local),
    };
};

export const fetchChatSettings = async (): Promise<ModelSettingsResponse> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_SETTINGS_PATH}`, { method: 'GET' });
    if (!isRecord(data)) {
        throw new Error('Unexpected settings response format');
    }
    return {
        active_provider_mode: (data.active_provider_mode === 'cloud' ? 'cloud' : 'local'),
        chat_model_provider: String(data.chat_model_provider ?? 'ollama'),
        chat_model_name: String(data.chat_model_name ?? ''),
        agent_model_provider: String(data.agent_model_provider ?? 'ollama'),
        agent_model_name: String(data.agent_model_name ?? ''),
        ollama_url: String(data.ollama_url ?? 'http://localhost:11434'),
        openai_base_url: typeof data.openai_base_url === 'string' ? data.openai_base_url : null,
        google_base_url: typeof data.google_base_url === 'string' ? data.google_base_url : null,
        credentials: isRecord(data.credentials) ? data.credentials as Record<string, Record<string, boolean>> : {},
    };
};

export const updateChatSettings = async (payload: ModelSettingsUpdateRequest): Promise<ModelSettingsResponse> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_SETTINGS_PATH}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!isRecord(data)) {
        throw new Error('Unexpected settings response format');
    }
    return {
        active_provider_mode: (data.active_provider_mode === 'cloud' ? 'cloud' : 'local'),
        chat_model_provider: String(data.chat_model_provider ?? 'ollama'),
        chat_model_name: String(data.chat_model_name ?? ''),
        agent_model_provider: String(data.agent_model_provider ?? 'ollama'),
        agent_model_name: String(data.agent_model_name ?? ''),
        ollama_url: String(data.ollama_url ?? 'http://localhost:11434'),
        openai_base_url: typeof data.openai_base_url === 'string' ? data.openai_base_url : null,
        google_base_url: typeof data.google_base_url === 'string' ? data.google_base_url : null,
        credentials: isRecord(data.credentials) ? data.credentials as Record<string, Record<string, boolean>> : {},
    };
};

export const refreshOllamaModels = async (): Promise<Record<string, unknown>> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_OLLAMA_REFRESH_PATH}`, { method: 'POST' });
    return isRecord(data) ? data : {};
};

export const pullOllamaModel = async (model: string): Promise<Record<string, unknown>> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_OLLAMA_PULL_PATH}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
    });
    return isRecord(data) ? data : {};
};

export const rebuildVectors = async (): Promise<VectorizationResponse> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_VECTOR_REBUILD_PATH}`, { method: 'POST' });
    if (!isRecord(data)) {
        throw new Error('Unexpected vectorization response format');
    }
    return {
        status: String(data.status ?? 'ok'),
        indexed_documents: Number(data.indexed_documents ?? 0),
        vector_path: String(data.vector_path ?? ''),
    };
};

export const checkOllamaHealth = async (): Promise<Record<string, unknown>> => {
    const data = await executeApiRequest(`${API_BASE_URL}${API_OLLAMA_HEALTH_PATH}`, { method: 'GET' });
    return isRecord(data) ? data : {};
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
    if (response.status === 401 || response.status === 403) {
        clearPersistedAppState();
    }
    return new ApiRequestError(message, {
        detail,
        raw: errorData,
        status: response.status,
    });
};
