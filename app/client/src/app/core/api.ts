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
} from './constants';
import {
  CatalogResponse,
  ChatStreamEvent,
  ChatTurnRequest,
  ChatTurnResponse,
  GenericObjectResponse,
  JsonValue,
  LocationSearchRequest,
  ModelCardDescriptor,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
  OllamaHealthResponse,
  SearchResponse,
  VectorizationResponse,
} from './types';

export class ApiRequestError extends Error {
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

export const CHAT_STREAM_TIMEOUT_MS = 120_000;

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

export const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string');

export const parseBooleanCredentialMap = (value: unknown): Record<string, Record<string, boolean>> => {
  if (!isRecord(value)) {
    return {};
  }
  const parsed: Record<string, Record<string, boolean>> = {};
  Object.entries(value).forEach(([provider, providerValue]) => {
    if (!isRecord(providerValue)) {
      return;
    }
    const nextProvider: Record<string, boolean> = {};
    Object.entries(providerValue).forEach(([key, flag]) => {
      nextProvider[key] = Boolean(flag);
    });
    parsed[provider] = nextProvider;
  });
  return parsed;
};

export const requireRecord = (value: unknown, fieldName: string): Record<string, unknown> => {
  if (!isRecord(value)) {
    throw new Error(`Chat response field ${fieldName} must be an object`);
  }
  return value;
};

export const requireString = (value: unknown, fieldName: string): string => {
  if (typeof value !== 'string') {
    throw new Error(`Chat response field ${fieldName} must be a string`);
  }
  return value;
};

export const requireNumber = (value: unknown, fieldName: string): number => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new Error(`Chat response field ${fieldName} must be a number`);
  }
  return value;
};

export const normalizeCapabilities = (input: unknown): CatalogResponse['capabilities'] => (
  Array.isArray(input) ? input : []
)
  .filter((item): item is Record<string, unknown> => isRecord(item) && typeof item.id === 'string')
  .map((item) => ({
    id: String(item.id),
    name: String(item.name ?? item.id),
    kind: String(item.kind ?? 'overlay'),
    type: typeof item.type === 'string' ? item.type : undefined,
    description: typeof item.description === 'string' ? item.description : undefined,
    provider: String(item.provider ?? 'unknown'),
    requires_credentials: Boolean(item.requires_credentials),
    is_available: Boolean(item.is_available),
    supports_map: Boolean(item.supports_map),
    supports_direct_text: Boolean(item.supports_direct_text),
    coverage: String(item.coverage ?? 'global'),
    source_protocol: typeof item.source_protocol === 'string' ? item.source_protocol : undefined,
    data_format: typeof item.data_format === 'string' ? item.data_format : undefined,
    geometry_type: typeof item.geometry_type === 'string' ? item.geometry_type : undefined,
    queryable: typeof item.queryable === 'boolean' ? item.queryable : undefined,
    vectorizable: typeof item.vectorizable === 'boolean' ? item.vectorizable : undefined,
    endpoint_health: typeof item.endpoint_health === 'string' ? item.endpoint_health : undefined,
    auth_mode: typeof item.auth_mode === 'string' ? item.auth_mode : undefined,
    official_docs_url: typeof item.official_docs_url === 'string' ? item.official_docs_url : undefined,
    intent_tags: Array.isArray(item.intent_tags)
      ? item.intent_tags.filter((v): v is string => typeof v === 'string')
      : [],
    task_tags: Array.isArray(item.task_tags)
      ? item.task_tags.filter((v): v is string => typeof v === 'string')
      : [],
    metadata: isRecord(item.metadata) ? item.metadata as Record<string, JsonValue> : {},
  }));

export const parseContextUsage = (input: unknown): ChatTurnResponse['context_usage'] => {
  if (!isRecord(input)) {
    return undefined;
  }
  return {
    estimated_input_tokens: Number(input.estimated_input_tokens ?? 0),
    selected_context_window: typeof input.selected_context_window === 'number' ? input.selected_context_window : null,
    model_context_limit: typeof input.model_context_limit === 'number' ? input.model_context_limit : null,
    usage_percent: Number(input.usage_percent ?? 0),
    provider: String(input.provider ?? ''),
    model: String(input.model ?? ''),
  };
};

export const buildModelDescription = (item: Record<string, unknown>): string => {
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

export const normalizeModelCards = (input: unknown): ModelCardDescriptor[] => {
  if (!Array.isArray(input)) {
    return [];
  }
  return input
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((item) => ({
      id: String(item.id ?? item.name ?? ''),
      name: String(item.name ?? item.id ?? ''),
      description: buildModelDescription(item),
      provider: String(item.provider ?? ''),
      capabilities: isStringArray(item.capabilities) ? item.capabilities : [],
      metadata: isRecord(item.metadata) ? item.metadata as Record<string, JsonValue> : {},
    }));
};

export const parseSearchResponse = (value: unknown): SearchResponse => {
  if (!isRecord(value)) {
    throw new Error('Unexpected search response format');
  }

  const statusMessage = value.status_message;
  if (typeof statusMessage !== 'string') {
    throw new Error('Search response is missing status_message');
  }
  if (!isRecord(value.map_session)) {
    throw new Error('Search response is missing map_session');
  }

  return {
    status_message: statusMessage,
    map_session: value.map_session as unknown as SearchResponse['map_session'],
  };
};

export const parseCatalogResponse = (value: unknown): CatalogResponse => {
  if (!isRecord(value)) {
    throw new Error('Unexpected catalog response format');
  }
  const normalized = normalizeCapabilities(value.capabilities);
  const providers = normalizeCapabilities(value.providers);
  const basemaps = normalizeCapabilities(value.basemaps);
  const overlays = normalizeCapabilities(value.overlays);
  const tools = normalizeCapabilities(value.tools);
  return {
    capabilities: normalized,
    providers: providers.length ? providers : normalized.filter((item) => item.kind === 'provider'),
    basemaps: basemaps.length ? basemaps : normalized.filter((item) => item.kind === 'basemap'),
    overlays: overlays.length ? overlays : normalized.filter((item) => item.kind === 'overlay'),
    tools: tools.length ? tools : normalized.filter((item) => item.kind === 'tool'),
  };
};

export const parseModelSettingsResponse = (value: unknown): ModelSettingsResponse => {
  if (!isRecord(value)) {
    throw new Error('Unexpected settings response format');
  }
  return {
    active_provider_mode: (value.active_provider_mode === 'cloud' ? 'cloud' : 'local'),
    chat_model_provider: String(value.chat_model_provider ?? 'ollama'),
    chat_model_name: String(value.chat_model_name ?? ''),
    parser_model_provider: String(value.parser_model_provider ?? 'ollama'),
    parser_model_name: String(value.parser_model_name ?? ''),
    agent_model_provider: String(value.agent_model_provider ?? 'ollama'),
    agent_model_name: String(value.agent_model_name ?? ''),
    ollama_url: String(value.ollama_url ?? 'http://localhost:11434'),
    openai_base_url: typeof value.openai_base_url === 'string' ? value.openai_base_url : null,
    google_base_url: typeof value.google_base_url === 'string' ? value.google_base_url : null,
    credentials: parseBooleanCredentialMap(value.credentials),
    credential_health: isRecord(value.credential_health)
      ? value.credential_health as ModelSettingsResponse['credential_health']
      : {},
  };
};

export const parseChatTurnResponse = (value: unknown): ChatTurnResponse => {
  if (!isRecord(value)) {
    throw new Error('Unexpected chat response format');
  }

  return {
    request_id: requireString(value.request_id, 'request_id'),
    session_id: requireNumber(value.session_id, 'session_id'),
    assistant_message: requireString(value.assistant_message, 'assistant_message'),
    turn_contract: requireRecord(value.turn_contract, 'turn_contract') as unknown as ChatTurnResponse['turn_contract'],
    decision: requireRecord(value.decision, 'decision') as unknown as ChatTurnResponse['decision'],
    tool_payload: isRecord(value.tool_payload) ? value.tool_payload as ChatTurnResponse['tool_payload'] : undefined,
    map_session: isRecord(value.map_session) ? value.map_session as unknown as ChatTurnResponse['map_session'] : undefined,
    memory_snapshot: isRecord(value.memory_snapshot) ? value.memory_snapshot as Record<string, JsonValue> : {},
    context_usage: parseContextUsage(value.context_usage),
  };
};

export const executeApiRequest = async (url: string, init: RequestInit): Promise<unknown> => {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error: unknown) {
    const message = (error as { name?: string })?.name === 'AbortError'
      ? 'Request interrupted before completion.'
      : 'Network request failed.';
    throw new ApiRequestError(message, { detail: error, raw: error });
  }
  if (!response.ok) {
    throw await buildApiError(response);
  }
  return response.json();
};

export const buildApiError = async (response: Response): Promise<ApiRequestError> => {
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

export const searchLocation = async (payload: LocationSearchRequest): Promise<SearchResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_MAPS_SEARCH_PATH}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return parseSearchResponse(data);
};

export const fetchCatalog = async (): Promise<CatalogResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_MAPS_CATALOG_PATH}`, {
    method: 'GET',
  });
  return parseCatalogResponse(data);
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
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), CHAT_STREAM_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_CHAT_STREAM_PATH}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (error: unknown) {
    if ((error as { name?: string })?.name === 'AbortError') {
      throw new ApiRequestError('Streaming request timed out. Please retry.', { status: 408 });
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }

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
    try {
      const parsed = JSON.parse(trailing) as ChatStreamEvent;
      onEvent(parsed);
    } catch {
      // ignore malformed trailing chunk
    }
  }
};

export const fetchChatModels = async (): Promise<{ cloud: ModelCardDescriptor[]; local: ModelCardDescriptor[] }> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_MODELS_PATH}`, { method: 'GET' });
  const value = isRecord(data) ? data : {};

  return {
    cloud: normalizeModelCards(value.cloud),
    local: normalizeModelCards(value.local),
  };
};

export const fetchChatSettings = async (): Promise<ModelSettingsResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_SETTINGS_PATH}`, { method: 'GET' });
  return parseModelSettingsResponse(data);
};

export const updateChatSettings = async (payload: ModelSettingsUpdateRequest): Promise<ModelSettingsResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_SETTINGS_PATH}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseModelSettingsResponse(data);
};

export const refreshOllamaModels = async (): Promise<GenericObjectResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_OLLAMA_REFRESH_PATH}`, { method: 'POST' });
  return isRecord(data) ? data : {};
};

export const pullOllamaModel = async (model: string): Promise<GenericObjectResponse> => {
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

export const checkOllamaHealth = async (): Promise<OllamaHealthResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_OLLAMA_HEALTH_PATH}`, { method: 'GET' });
  return isRecord(data) ? data : {};
};