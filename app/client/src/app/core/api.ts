import {
  API_BASE_URL,
  API_CHAT_MODELS_PATH,
  API_CHAT_SETTINGS_PATH,
  API_CHAT_STREAM_PATH,
  API_CHAT_TURN_PATH,
  API_GEOSPATIAL_AUDIT_PATH,
  API_GEOSPATIAL_CAMERAS_PATH,
  API_GEOSPATIAL_CAPABILITIES_PATH,
  API_GEOSPATIAL_LAYERS_PATH,
  API_MAPS_CATALOG_PATH,
  API_MAPS_SEARCH_PATH,
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
  parseModelSettingsResponse,
  parseSearchResponse,
} from './api-parsers';
import {
  CatalogResponse,
  ChatStreamEvent,
  ChatTurnRequest,
  ChatTurnResponse,
  GenericObjectResponse,
  GeospatialCredentialStatus,
  GeospatialProviderAccountSetupListResponse,
  GeospatialProviderPayload,
  LocationSearchRequest,
  ModelCardDescriptor,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
  OllamaHealthResponse,
  SearchResponse,
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

export const CHAT_STREAM_TIMEOUT_MS = 120_000;

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
  const query = new URLSearchParams();
  if (params.bbox) {
    query.set('bbox', params.bbox);
  }
  if (typeof params.zoom === 'number') {
    query.set('zoom', String(params.zoom));
  }
  if (params.time) {
    query.set('time', params.time);
  }
  if (params.live) {
    query.set('live', 'true');
  }
  if (params.incidents) {
    query.set('incidents', 'true');
  }
  const suffix = query.toString() ? `?${query}` : '';
  const data = await executeApiRequest(
    `${API_BASE_URL}${API_GEOSPATIAL_LAYERS_PATH}/${encodeURIComponent(layerId)}/features${suffix}`,
    { method: 'GET' },
  );
  return isRecord(data) ? data as unknown as GeospatialProviderPayload : { status: 'unavailable', provider: 'unknown' };
};

export const fetchGeospatialCameras = async (
  params: { bbox?: string; provider?: string; camera_type?: string } = {},
): Promise<GeospatialProviderPayload> => {
  const query = new URLSearchParams();
  if (params.bbox) {
    query.set('bbox', params.bbox);
  }
  if (params.provider) {
    query.set('provider', params.provider);
  }
  if (params.camera_type) {
    query.set('camera_type', params.camera_type);
  }
  const suffix = query.toString() ? `?${query}` : '';
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_CAMERAS_PATH}${suffix}`, {
    method: 'GET',
  });
  return isRecord(data) ? data as unknown as GeospatialProviderPayload : { status: 'unavailable', provider: 'unknown' };
};

export const fetchGeospatialCameraDetail = async (cameraId: string): Promise<GeospatialProviderPayload> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_CAMERAS_PATH}/${encodeURIComponent(cameraId)}`, {
    method: 'GET',
  });
  return isRecord(data)
    ? data as unknown as GeospatialProviderPayload
    : { status: 'unavailable', provider: 'unknown' };
};

export const fetchGeospatialCredentialStatus = async (providerId: string): Promise<GeospatialCredentialStatus> => {
  const data = await executeApiRequest(`${API_BASE_URL}/geospatial/sources/${encodeURIComponent(providerId)}/credential-status`, {
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
  const data = await executeApiRequest(`${API_BASE_URL}/geospatial/providers/account-setup`, { method: 'GET' });
  return parseGeospatialProviderAccountSetups(data);
};

export const runGeospatialAudit = async (): Promise<GenericObjectResponse> => {
  const data = await executeApiRequest(`${API_BASE_URL}${API_GEOSPATIAL_AUDIT_PATH}`, { method: 'POST' });
  return isRecord(data) ? data : {};
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
  const data = await executeApiRequest(`${API_BASE_URL}${API_CHAT_MODELS_PATH}`, {
    method: 'GET',
    cache: 'no-store',
  });
  const value = isRecord(data) ? data : {};

  return {
    cloud: normalizeModelCards(value.cloud),
    local: normalizeModelCards(value.local),
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
