import {
  API_BASE_URL,
  API_CHAT_MODELS_PATH,
  API_CHAT_STRUCTURED_PROBE_PATH,
  API_CHAT_SETTINGS_PATH,
  API_CHAT_TURN_PATH,
  API_CONVERSATION_PATH,
  API_CONVERSATIONS_PATH,
  API_GEOSPATIAL_CAMERAS_PATH,
  API_GEOSPATIAL_CAPABILITIES_PATH,
  API_GEOSPATIAL_LAYERS_PATH,
  API_GEOSPATIAL_PROVIDER_ACCOUNT_SETUP_PATH,
  API_GEOSPATIAL_SOURCE_CREDENTIAL_STATUS_PATH,
  API_OLLAMA_HEALTH_PATH,
  API_OLLAMA_PULL_PATH,
  API_OLLAMA_REFRESH_PATH,
} from './constants';
import {
  parseCatalogResponse,
  parseChatTurnResponse,
  parseConversationCreateResponse,
  parseConversationListResponse,
  parseConversationSnapshotResponse,
  parseGenericObjectResponse,
  parseGeospatialCredentialStatus,
  parseGeospatialLayersResponse,
  parseGeospatialProviderPayload,
  parseGeospatialProviderAccountSetups,
  parseModelLibraryResponse,
  parseModelSettingsResponse,
  parseOllamaHealthResponse,
  parseOllamaRefreshResponse,
  parseStructuredProbeResponse,
  parseRunTraceResponse,
} from './api-parsers';
import {
  CatalogResponse,
  ChatTurnRequest,
  ChatTurnResponse,
  ConversationCreateRequest,
  ConversationCreateResponse,
  ConversationListResponse,
  ConversationSnapshotResponse,
  GenericObjectResponse,
  GeospatialCredentialStatus,
  GeospatialProviderAccountSetupListResponse,
  GeospatialProviderPayload,
  ModelLibraryResponse,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
  StructuredProbeResponse,
  RunTraceResponse,
  OllamaHealthResponse,
} from './types';
import { ApiRequestError } from './api-errors';

export { ApiContractError, ApiRequestError } from './api-errors';

const API_REQUEST_TIMEOUTS = {
  metadata: 30_000,
  ordinary: 60_000,
  long_operation: 180_000,
} as const;

const requestTimeoutMs = (url: string, init: RequestInit): number => {
  const normalizedUrl = url.toLowerCase();
  if (
    normalizedUrl.includes('/chat/turn')
    || normalizedUrl.includes('/chat/structured-probe')
    || normalizedUrl.includes('/ollama/pull')
    || normalizedUrl.includes('/geospatial/layers/') && normalizedUrl.includes('/features')
  ) {
    return API_REQUEST_TIMEOUTS.long_operation;
  }
  if (init.method?.toUpperCase() === 'GET') {
    return API_REQUEST_TIMEOUTS.metadata;
  }
  return API_REQUEST_TIMEOUTS.ordinary;
};

const buildQuerySuffix = (params: Record<string, string | number | boolean | undefined>): string => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === false || value === '') {
      return;
    }
    query.set(key, value === true ? 'true' : String(value));
  });
  const serialized = query.toString();
  return serialized ? `?${serialized}` : '';
};

export const executeApiRequest = async (
  url: string,
  init: RequestInit,
  timeoutMs = requestTimeoutMs(url, init),
): Promise<unknown> => {
  const controller = new AbortController();
  const callerSignal = init.signal;
  let timedOut = false;
  const forwardAbort = (): void => controller.abort();
  if (callerSignal?.aborted) {
    controller.abort();
  } else {
    callerSignal?.addEventListener('abort', forwardAbort, { once: true });
  }
  const timeoutHandle = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, Math.max(1, timeoutMs));

  let response: Response;
  try {
    response = await fetch(url, { ...init, signal: controller.signal });
  } catch (error: unknown) {
    const message = (error as { name?: string })?.name === 'AbortError'
      ? timedOut
        ? 'Request timed out before completion.'
        : 'Request interrupted before completion.'
      : 'Network request failed.';
    throw new ApiRequestError(message, { detail: error, raw: error });
  } finally {
    clearTimeout(timeoutHandle);
    callerSignal?.removeEventListener('abort', forwardAbort);
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

export const fetchCatalog = async (): Promise<CatalogResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_CAPABILITIES_PATH}`, {
    method: 'GET',
  });
  return parseCatalogResponse(data);
};

export const fetchGeospatialLayers = async (): Promise<Pick<CatalogResponse, 'basemaps' | 'overlays' | 'cameras' | 'transit'>> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_LAYERS_PATH}`, {
    method: 'GET',
  });
  return parseGeospatialLayersResponse(data);
};

export const fetchGeospatialLayerFeatures = async (
  layerId: string,
  params: { bbox?: string; zoom?: number; time?: string; live?: boolean; incidents?: boolean } = {},
): Promise<GeospatialProviderPayload> => {
  const suffix = buildQuerySuffix(params);
  const data = await executeApiRequest(
    `${API_BASE_URL}${API_GEOSPATIAL_LAYERS_PATH}/${encodeURIComponent(layerId)}/features${suffix}`,
    { method: 'GET' },
  );
  return parseGeospatialProviderPayload(data, 'geospatial layer features');
};

export const fetchGeospatialCameras = async (
  params: { bbox?: string; provider?: string; camera_type?: string } = {},
): Promise<GeospatialProviderPayload> => {
  const suffix = buildQuerySuffix(params);
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_CAMERAS_PATH}${suffix}`, {
    method: 'GET',
  });
  return parseGeospatialProviderPayload(data, 'geospatial cameras');
};

export const fetchGeospatialCredentialStatus = async (providerId: string): Promise<GeospatialCredentialStatus> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_SOURCE_CREDENTIAL_STATUS_PATH(providerId)}`, {
    method: 'GET',
  });
  return parseGeospatialCredentialStatus(data);
};

export const fetchGeospatialProviderAccountSetups = async (): Promise<GeospatialProviderAccountSetupListResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_PROVIDER_ACCOUNT_SETUP_PATH}`, { method: 'GET' });
  return parseGeospatialProviderAccountSetups(data);
};

export const sendChatTurn = async (payload: ChatTurnRequest): Promise<ChatTurnResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_TURN_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseChatTurnResponse(data);
};

export const createConversation = async (
  payload: ConversationCreateRequest,
): Promise<ConversationCreateResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CONVERSATIONS_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseConversationCreateResponse(data);
};

export const fetchConversationSnapshot = async (
  conversationId: string,
): Promise<ConversationSnapshotResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CONVERSATION_PATH(conversationId)}`, {
    method: 'GET',
    cache: 'no-store',
  });
  return parseConversationSnapshotResponse(data);
};

export const fetchConversations = async (
  params: { query?: string; limit?: number; cursor?: string } = {},
): Promise<ConversationListResponse> => {
  const suffix = buildQuerySuffix({
    query: params.query,
    limit: params.limit,
    cursor: params.cursor,
  });
  const data = await executeApiRequest(`${API_BASE_URL}${API_CONVERSATIONS_PATH}${suffix}`, {
    method: 'GET',
    cache: 'no-store',
  });
  return parseConversationListResponse(data);
};

export const fetchConversationRunTrace = async (
  conversationId: string,
  runId: string,
  params: { limit?: number; cursor?: string } = {},
): Promise<RunTraceResponse> => {
  const suffix = buildQuerySuffix({ limit: params.limit, cursor: params.cursor });
  const path = `${API_CONVERSATION_PATH(conversationId)}/runs/${encodeURIComponent(runId)}/trace`;
  const data = await executeApiRequest(`${API_BASE_URL}${path}${suffix}`, {
    method: 'GET',
    cache: 'no-store',
  });
  return parseRunTraceResponse(data);
};

export const fetchChatModels = async (
  provider?: 'deepseek' | 'opencode' | 'opencode-go',
): Promise<ModelLibraryResponse> => {
  const suffix = provider ? `?provider=${encodeURIComponent(provider)}` : '';
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_MODELS_PATH}${suffix}`, {
    method: 'GET',
    cache: 'no-store',
  });
  return parseModelLibraryResponse(data);
};

export const fetchChatSettings = async (): Promise<ModelSettingsResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_SETTINGS_PATH}`, {
    method: 'GET',
    cache: 'no-store',
  });
  return parseModelSettingsResponse(data);
};

export const updateChatSettings = async (payload: ModelSettingsUpdateRequest): Promise<ModelSettingsResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_SETTINGS_PATH}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseModelSettingsResponse(data);
};

export const refreshOllamaModels = async (): Promise<GenericObjectResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_OLLAMA_REFRESH_PATH}`, { method: 'POST' });
  return parseOllamaRefreshResponse(data);
};

export const pullOllamaModel = async (model: string): Promise<GenericObjectResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_OLLAMA_PULL_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  return parseGenericObjectResponse(data, 'Ollama model pull');
};

export const checkOllamaHealth = async (): Promise<OllamaHealthResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_OLLAMA_HEALTH_PATH}`, { method: 'GET' });
  return parseOllamaHealthResponse(data);
};

export const fetchStructuredProbe = async (): Promise<StructuredProbeResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_STRUCTURED_PROBE_PATH}`, {
    method: 'GET',
    cache: 'no-store',
  });
  return parseStructuredProbeResponse(data);
};

export const runStructuredProbe = async (): Promise<StructuredProbeResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_STRUCTURED_PROBE_PATH}`, {
    method: 'POST',
    cache: 'no-store',
  });
  return parseStructuredProbeResponse(data);
};
