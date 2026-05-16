const DEFAULT_API_BASE_PATH = '/api';

const trimTrailingSlashes = (value: string): string => {
  let normalized = value;
  while (normalized.length > 1 && normalized.endsWith('/')) {
    normalized = normalized.slice(0, -1);
  }
  return normalized;
};

const normalizeApiBaseUrl = (value: string): string => {
  const candidate = value.trim();
  if (!candidate) {
    return DEFAULT_API_BASE_PATH;
  }
  if (candidate.startsWith('/') && !candidate.startsWith('//')) {
    return trimTrailingSlashes(candidate);
  }
  if (candidate.startsWith('http://') || candidate.startsWith('https://')) {
    return trimTrailingSlashes(candidate);
  }
  return DEFAULT_API_BASE_PATH;
};

const computeDefaultApiBaseUrl = (): string => {
  if (typeof window === 'undefined') {
    return DEFAULT_API_BASE_PATH;
  }
  const { protocol, hostname, port } = window.location;
  const isLocalHost = hostname === '127.0.0.1' || hostname === 'localhost';
  if (isLocalHost && port === '4980') {
    return `${protocol}//${hostname}:6010/api`;
  }
  return DEFAULT_API_BASE_PATH;
};

const globalApiBase = typeof window !== 'undefined'
  ? String((window as Window & { __AEGIS_API_BASE_URL__?: string }).__AEGIS_API_BASE_URL__ || '')
  : '';

export const API_BASE_URL = normalizeApiBaseUrl(globalApiBase || computeDefaultApiBaseUrl());
export const API_MAPS_SEARCH_PATH = '/maps/search';
export const API_MAPS_CATALOG_PATH = '/maps/catalog';
export const API_GEOSPATIAL_CAPABILITIES_PATH = '/geospatial/capabilities';
export const API_GEOSPATIAL_LAYERS_PATH = '/geospatial/layers';
export const API_GEOSPATIAL_CAMERAS_PATH = '/geospatial/cameras';
export const API_GEOSPATIAL_AUDIT_PATH = '/geospatial/audit';
export const API_GEOSPATIAL_PROVIDER_ACCOUNT_SETUPS_PATH = '/geospatial/providers/account-setup';
export const API_CHAT_TURN_PATH = '/chat/turn';
export const API_CHAT_STREAM_PATH = '/chat/stream';
export const API_CHAT_MODELS_PATH = '/chat/models';
export const API_CHAT_SETTINGS_PATH = '/chat/settings';
export const API_OLLAMA_REFRESH_PATH = '/chat/models/ollama/refresh';
export const API_OLLAMA_PULL_PATH = '/chat/models/ollama/pull';
export const API_OLLAMA_HEALTH_PATH = '/chat/models/ollama/health';
export const API_VECTOR_REBUILD_PATH = '/chat/vectors/rebuild';

export const DEFAULT_OVERLAY_OPACITY = 0.65;
export const DEFAULT_WMS_LAYER_ID = '0';
export const DEFAULT_WMS_VERSION = '1.1.1';
export const DEFAULT_WMS_EXCEPTIONS = 'application/vnd.ogc.se_inimage';
export const DEFAULT_WMTS_MATRIX_SET = 'EPSG:3857';
export const DEFAULT_WMTS_FORMAT = 'image/png';
export const DEFAULT_BASE_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
export const DEFAULT_BASE_TILE_PROXY_URL = `${API_BASE_URL}/maps/basemaps/osm/{z}/{x}/{y}.png`;
export const DEFAULT_BASE_ATTRIBUTION = '© OpenStreetMap contributors';
export const DEFAULT_BASE_TILE_MAX_ZOOM = 19;
export const DEFAULT_MAP_FIT_MAX_ZOOM = 18;
