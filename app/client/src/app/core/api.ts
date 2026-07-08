import {
  API_BASE_URL,
  API_CHAT_MODELS_PATH,
  API_CHAT_SETTINGS_PATH,
  API_CHAT_TURN_PATH,
  API_CONVERSATION_RUN_CANCEL_PATH,
  API_CONVERSATION_RUN_EVENTS_PATH,
  API_CONVERSATION_RUN_STEERING_PATH,
  API_CONVERSATION_RUNS_PATH,
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
  normalizeCapabilities,
  normalizeModelCards,
  parseCatalogResponse,
  parseChatTurnResponse,
  parseGeospatialProviderAccountSetups,
  parseModelLibrarySources,
  parseModelSettingsResponse,
} from './api-parsers';
import {
  CatalogResponse,
  AgentRunCancelResponse,
  AgentRunCreateRequest,
  AgentRunCreateResponse,
  ChatTurnRequest,
  ChatTurnResponse,
  ConversationCreateRequest,
  ConversationCreateResponse,
  GenericObjectResponse,
  GeospatialCredentialStatus,
  GeospatialProviderAccountSetupListResponse,
  GeospatialProviderPayload,
  ModelLibraryResponse,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
  OllamaHealthResponse,
  SteeringMessageRequest,
  SteeringMessageResponse,
} from './types';
import { isRecord } from './type-guards';

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

const asProviderPayload = (data: unknown): GeospatialProviderPayload =>
  isRecord(data) ? data as unknown as GeospatialProviderPayload : { status: 'unavailable', provider: 'unknown' };

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

export const fetchCatalog = async (): Promise<CatalogResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_CAPABILITIES_PATH}`, {
    method: 'GET',
  });
  return parseCatalogResponse(data);
};

export const fetchGeospatialCapabilities = async (): Promise<CatalogResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_CAPABILITIES_PATH}`, {
    method: 'GET',
  });
  return parseCatalogResponse(data);
};

export const fetchGeospatialLayers = async (): Promise<Pick<CatalogResponse, 'basemaps' | 'overlays' | 'cameras' | 'transit'>> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_LAYERS_PATH}`, {
    method: 'GET',
  });
  const value = isRecord(data) ? data : {};
  return {
    basemaps: normalizeCapabilities(value.basemaps),
    overlays: normalizeCapabilities(value.overlays),
    cameras: normalizeCapabilities(value.cameras),
    transit: normalizeCapabilities(value.transit),
  };
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
  return asProviderPayload(data);
};

export const fetchGeospatialCameras = async (
  params: { bbox?: string; provider?: string; camera_type?: string } = {},
): Promise<GeospatialProviderPayload> => {
  const suffix = buildQuerySuffix(params);
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_CAMERAS_PATH}${suffix}`, {
    method: 'GET',
  });
  return asProviderPayload(data);
};

export const fetchGeospatialCredentialStatus = async (providerId: string): Promise<GeospatialCredentialStatus> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_SOURCE_CREDENTIAL_STATUS_PATH(providerId)}`, {
    method: 'GET',
  });
  if (!isRecord(data)) {
    return { provider: providerId, required: false, configured: false };
  }
  return {
    provider: String(data.provider ?? providerId),
    required: Boolean(data.required),
    configured: Boolean(data.configured),
    environmentVariable: typeof data.environmentVariable === 'string' ? data.environmentVariable : null,
  };
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
  return data as ConversationCreateResponse;
};

export const createAgentRun = async (
  conversationId: string,
  payload: AgentRunCreateRequest,
): Promise<AgentRunCreateResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CONVERSATION_RUNS_PATH(conversationId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return data as AgentRunCreateResponse;
};

export const sendRunSteering = async (
  conversationId: string,
  runId: string,
  payload: SteeringMessageRequest,
): Promise<SteeringMessageResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CONVERSATION_RUN_STEERING_PATH(conversationId, runId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return data as SteeringMessageResponse;
};

export const cancelAgentRun = async (
  conversationId: string,
  runId: string,
): Promise<AgentRunCancelResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_CONVERSATION_RUN_CANCEL_PATH(conversationId, runId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: 'user_cancelled' }),
  });
  return data as AgentRunCancelResponse;
};

export const openRunEventSource = (
  conversationId: string,
  runId: string,
  afterEventId?: string,
): EventSource => {
  const path = API_CONVERSATION_RUN_EVENTS_PATH(conversationId, runId);
  const suffix = afterEventId ? `?after_event_id=${encodeURIComponent(afterEventId)}` : '';
  return new EventSource(`${API_BASE_URL}${path}${suffix}`);
};

export const fetchChatModels = async (
  provider?: 'deepseek',
): Promise<ModelLibraryResponse> => {
  const suffix = provider ? `?provider=${encodeURIComponent(provider)}` : '';
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_MODELS_PATH}${suffix}`, {
    method: 'GET',
    cache: 'no-store',
  });
  const value = isRecord(data) ? data : {};

  return {
    cloud: normalizeModelCards(value.cloud),
    local: normalizeModelCards(value.local),
    sources: parseModelLibrarySources(value.sources),
  };
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

export const checkOllamaHealth = async (): Promise<OllamaHealthResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_OLLAMA_HEALTH_PATH}`, { method: 'GET' });
  return isRecord(data) ? data : {};
};
