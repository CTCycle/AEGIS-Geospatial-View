import {
  ActiveConversationRunSnapshot,
  AgentRunState,
  CatalogResponse,
  ChatMessage,
  ChatRole,
  ChatTurnResponse,
  ConversationCreateResponse,
  ConversationSnapshotResponse,
  ConversationTaskSnapshot,
  GenericObjectResponse,
  GeospatialCredentialStatus,
  GeospatialLayerRenderDescriptor,
  GeospatialProviderPayload,
  GeospatialProviderAccountSetup,
  GeospatialProviderAccountSetupListResponse,
  GeospatialProviderLayerDescriptor,
  GeoJsonFeatureCollection,
  JsonObject,
  JsonValue,
  MapOverlayEntry,
  MapSession,
  ModelCardDescriptor,
  ModelLibraryResponse,
  ModelSettingsResponse,
  SelectedModelContext,
  OllamaHealthResponse,
  MapInspection,
  OverlayCollectionState,
  OverlayInstance,
} from './types';
import { isFiniteNumber, isJsonObject, isRecord, isStringArray } from './type-guards';
import { ApiContractError } from './api-errors';

const apiContract = (endpoint: string, detail: string, raw?: unknown): never => {
  throw new ApiContractError(endpoint, detail, raw);
};

const requireApiRecord = (value: unknown, endpoint: string, field = 'response'): Record<string, unknown> => {
  if (!isRecord(value) || Array.isArray(value)) {
    return apiContract(endpoint, `${field} must be an object`, value);
  }
  return value;
};

const requireApiJsonObject = (
  value: unknown,
  endpoint: string,
  field: string,
): Record<string, JsonValue> => {
  if (!isJsonObject(value)) {
    return apiContract(endpoint, `${field} must be a JSON object`, value);
  }
  return value;
};

const requireApiArray = (value: unknown, endpoint: string, field: string): unknown[] => {
  if (!Array.isArray(value)) {
    return apiContract(endpoint, `${field} must be an array`, value);
  }
  return value;
};

const requireApiString = (
  record: Record<string, unknown>,
  field: string,
  endpoint: string,
): string => {
  if (typeof record[field] !== 'string') {
    return apiContract(endpoint, `${field} must be a string`, record[field]);
  }
  return record[field] as string;
};

const requireApiStringOrNull = (
  record: Record<string, unknown>,
  field: string,
  endpoint: string,
): string | null => {
  if (!(field in record) || (record[field] !== null && typeof record[field] !== 'string')) {
    return apiContract(endpoint, `${field} must be a string or null`, record[field]);
  }
  return record[field] as string | null;
};

const requireApiBoolean = (
  record: Record<string, unknown>,
  field: string,
  endpoint: string,
): boolean => {
  if (typeof record[field] !== 'boolean') {
    return apiContract(endpoint, `${field} must be a boolean`, record[field]);
  }
  return record[field] as boolean;
};

const requireApiStringArray = (
  record: Record<string, unknown>,
  field: string,
  endpoint: string,
): string[] => {
  if (!isStringArray(record[field])) {
    return apiContract(endpoint, `${field} must be an array of strings`, record[field]);
  }
  return record[field] as string[];
};

const optionalApiString = (
  record: Record<string, unknown>,
  field: string,
  endpoint: string,
): string | null | undefined => {
  if (!(field in record)) {
    return undefined;
  }
  if (record[field] !== null && typeof record[field] !== 'string') {
    return apiContract(endpoint, `${field} must be a string or null`, record[field]);
  }
  return record[field] as string | null;
};

const optionalApiNullableBoolean = (
  record: Record<string, unknown>,
  field: string,
  endpoint: string,
): boolean | null | undefined => {
  if (!(field in record)) {
    return undefined;
  }
  if (record[field] !== null && typeof record[field] !== 'boolean') {
    return apiContract(endpoint, `${field} must be a boolean or null`, record[field]);
  }
  return record[field] as boolean | null;
};

const optionalApiNumber = (
  record: Record<string, unknown>,
  field: string,
  endpoint: string,
): number | null | undefined => {
  if (!(field in record)) {
    return undefined;
  }
  if (record[field] !== null && !isFiniteNumber(record[field])) {
    return apiContract(endpoint, `${field} must be a finite number or null`, record[field]);
  }
  return record[field] as number | null;
};

const optionalApiRecord = (
  record: Record<string, unknown>,
  field: string,
  endpoint: string,
): Record<string, unknown> | null | undefined => {
  if (!(field in record)) {
    return undefined;
  }
  if (record[field] === null) {
    return null;
  }
  return requireApiRecord(record[field], endpoint, field);
};

const safeStringRecord = (value: unknown): Record<string, string> | undefined => {
  if (!isRecord(value) || Array.isArray(value)) {
    return undefined;
  }
  const entries = Object.entries(value).filter(([, entry]) => typeof entry === 'string');
  return entries.length === Object.keys(value).length
    ? Object.fromEntries(entries) as Record<string, string>
    : undefined;
};

const safeJsonRecord = (value: unknown): Record<string, JsonValue> | null | undefined => {
  if (value === null) {
    return null;
  }
  return isJsonObject(value) ? value : undefined;
};

export const parseBooleanCredentialMap = (
  value: unknown,
  endpoint = 'model settings',
): Record<string, Record<string, boolean>> => {
  const record = requireApiRecord(value, endpoint, 'credentials');
  const parsed: Record<string, Record<string, boolean>> = {};
  Object.entries(record).forEach(([provider, providerValue]) => {
    const providerRecord = requireApiRecord(providerValue, endpoint, `credentials.${provider}`);
    const nextProvider: Record<string, boolean> = {};
    Object.entries(providerRecord).forEach(([key, flag]) => {
      if (typeof flag !== 'boolean') {
        return apiContract(endpoint, `credentials.${provider}.${key} must be a boolean`, flag);
      }
      nextProvider[key] = flag as boolean;
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

export const normalizeCapabilities = (
  input: unknown,
  endpoint = 'geospatial catalog',
  field = 'capabilities',
): CatalogResponse['capabilities'] => requireApiArray(input, endpoint, field).map((raw, index) => {
  const item = requireApiRecord(raw, endpoint, `capabilities[${index}]`);
  const reliability = requireApiRecord(item.reliability, endpoint, `capabilities[${index}].reliability`);
  const auth = requireApiRecord(item.auth, endpoint, `capabilities[${index}].auth`);
  const render = item.render === undefined ? undefined : requireApiRecord(
    item.render,
    endpoint,
    `capabilities[${index}].render`,
  );
  return {
    id: requireApiString(item, 'id', endpoint),
    name: requireApiString(item, 'name', endpoint),
    kind: requireApiString(item, 'kind', endpoint),
    type: requireApiString(item, 'type', endpoint),
    description: requireApiString(item, 'description', endpoint),
    provider: requireApiString(item, 'provider', endpoint),
    requires_credentials: requireApiBoolean(item, 'requires_credentials', endpoint),
    is_available: requireApiBoolean(item, 'is_available', endpoint),
    supports_map: requireApiBoolean(item, 'supports_map', endpoint),
    supports_direct_text: requireApiBoolean(item, 'supports_direct_text', endpoint),
    coverage: requireApiString(item, 'coverage', endpoint),
    source_protocol: requireApiString(item, 'source_protocol', endpoint),
    data_format: requireApiString(item, 'data_format', endpoint),
    geometry_type: requireApiString(item, 'geometry_type', endpoint),
    queryable: requireApiBoolean(item, 'queryable', endpoint),
    endpoint_health: requireApiString(item, 'endpoint_health', endpoint),
    auth_mode: requireApiString(item, 'auth_mode', endpoint),
    official_docs_url: requireApiString(item, 'official_docs_url', endpoint),
    capability_kind: requireApiString(item, 'capability_kind', endpoint),
    rendering_mode: requireApiString(item, 'rendering_mode', endpoint),
    reliability: {
      status: requireApiString(reliability, 'status', endpoint),
      lastAudited: optionalApiString(reliability, 'last_audited', endpoint) ?? undefined,
      knownLimitations: requireApiStringArray(reliability, 'known_limitations', endpoint),
    },
    auth: {
      type: requireApiString(auth, 'type', endpoint),
      required: requireApiBoolean(auth, 'required', endpoint),
      providerKey: optionalApiString(auth, 'provider_key', endpoint) ?? null,
      accessPageProviderId: optionalApiString(auth, 'access_page_provider_id', endpoint) ?? null,
    },
    action_tags: requireApiStringArray(item, 'action_tags', endpoint),
    task_tags: requireApiStringArray(item, 'task_tags', endpoint),
    metadata: requireApiRecord(item.metadata, endpoint, `capabilities[${index}].metadata`) as Record<string, JsonValue>,
    render: render
      ? {
        status: optionalApiString(render, 'status', endpoint) ?? undefined,
        tile_url: optionalApiString(render, 'tile_url', endpoint) ?? null,
        style_url: optionalApiString(render, 'style_url', endpoint) ?? null,
        attribution: optionalApiString(render, 'attribution', endpoint) ?? undefined,
        reason: optionalApiString(render, 'reason', endpoint) ?? undefined,
      }
      : undefined,
  };
});

export const mapGeospatialProviderSignupField = (
  dto: Record<string, unknown>,
  endpoint = 'geospatial provider account setup',
  field = 'field',
): GeospatialProviderAccountSetup['automation']['requiredFields'][number] => {
  const fieldType = requireApiString(dto, 'field_type', endpoint);
  if (!['text', 'email', 'textarea', 'select'].includes(fieldType)) {
    return apiContract(endpoint, `${field}.field_type is unsupported`, fieldType);
  }
  return {
    key: requireApiString(dto, 'key', endpoint),
    label: requireApiString(dto, 'label', endpoint),
    fieldType: fieldType as GeospatialProviderAccountSetup['automation']['requiredFields'][number]['fieldType'],
    required: requireApiBoolean(dto, 'required', endpoint),
    sensitive: requireApiBoolean(dto, 'sensitive', endpoint),
    helpText: requireApiStringOrNull(dto, 'help_text', endpoint),
  };
};

export const mapGeospatialProviderSignupAutomation = (
  dto: Record<string, unknown>,
  endpoint = 'geospatial provider account setup',
): GeospatialProviderAccountSetup['automation'] => {
  const support = requireApiString(dto, 'support', endpoint);
  if (!['manual_only', 'guided_playwright', 'agent_assisted', 'unsupported'].includes(support)) {
    return apiContract(endpoint, 'automation.support is unsupported', support);
  }
  const requiredFields = requireApiArray(dto.required_fields, endpoint, 'automation.required_fields')
    .map((item, index) => mapGeospatialProviderSignupField(
      requireApiRecord(item, endpoint, `automation.required_fields[${index}]`),
      endpoint,
      `automation.required_fields[${index}]`,
    ))
    .filter((field) => !field.sensitive);
  return {
    support: support as GeospatialProviderAccountSetup['automation']['support'],
    signupUrl: requireApiStringOrNull(dto, 'signup_url', endpoint),
    developerPortalUrl: requireApiStringOrNull(dto, 'developer_portal_url', endpoint),
    docsUrl: requireApiStringOrNull(dto, 'docs_url', endpoint),
    requiredFields,
    userActionNotes: requireApiStringArray(dto, 'user_action_notes', endpoint),
    safetyNotes: requireApiStringArray(dto, 'safety_notes', endpoint),
    experimental: requireApiBoolean(dto, 'experimental', endpoint),
    experimentalLabel: requireApiString(dto, 'experimental_label', endpoint),
  };
};

export const mapGeospatialProviderAccountSetup = (
  dto: Record<string, unknown>,
  endpoint = 'geospatial provider account setup',
): GeospatialProviderAccountSetup => ({
  providerId: requireApiString(dto, 'provider_id', endpoint),
  name: requireApiString(dto, 'name', endpoint),
  requiresCredentials: requireApiBoolean(dto, 'requires_credentials', endpoint),
  authMode: requireApiString(dto, 'auth_mode', endpoint),
  docsUrl: requireApiStringOrNull(dto, 'docs_url', endpoint),
  configured: requireApiBoolean(dto, 'configured', endpoint),
  instructions: requireApiStringArray(dto, 'instructions', endpoint),
  automation: mapGeospatialProviderSignupAutomation(
    requireApiRecord(dto.automation, endpoint, 'automation'),
    endpoint,
  ),
  credentialStorageKey: requireApiString(dto, 'credential_storage_key', endpoint),
  credentialLabel: requireApiString(dto, 'credential_label', endpoint),
  keyFormatHint: requireApiStringOrNull(dto, 'key_format_hint', endpoint),
  validationSupported: requireApiBoolean(dto, 'validation_supported', endpoint),
});

export const parseGeospatialProviderAccountSetups = (
  value: unknown,
  endpoint = 'geospatial provider account setup',
): GeospatialProviderAccountSetupListResponse => {
  const record = requireApiRecord(value, endpoint);
  const providers = requireApiArray(record.providers, endpoint, 'providers')
    .map((item, index) => mapGeospatialProviderAccountSetup(
      requireApiRecord(item, endpoint, `providers[${index}]`),
      endpoint,
    ));
  return { providers };
};

export const parseGeospatialProviderPayload = (
  value: unknown,
  endpoint = 'geospatial provider',
): GeospatialProviderPayload => {
  const record = requireApiRecord(value, endpoint);
  const parsed: GeospatialProviderPayload = {
    status: requireApiString(record, 'status', endpoint),
    provider: requireApiString(record, 'provider', endpoint),
  };
  if ('payload' in record) {
    if (record.payload !== null) {
      parsed.payload = requireApiJsonObject(record.payload, endpoint, 'payload');
    }
  }
  if ('attribution' in record) {
    parsed.attribution = requireApiStringArray(record, 'attribution', endpoint);
  }
  if ('warnings' in record) {
    parsed.warnings = requireApiStringArray(record, 'warnings', endpoint);
  }
  if ('stale' in record) {
    parsed.stale = requireApiBoolean(record, 'stale', endpoint);
  }
  if ('result_status' in record) {
    parsed.result_status = requireApiStringOrNull(record, 'result_status', endpoint);
  }
  if ('result_type' in record) {
    parsed.result_type = requireApiStringOrNull(record, 'result_type', endpoint);
  }
  if ('fetched_at' in record) {
    parsed.fetched_at = requireApiStringOrNull(record, 'fetched_at', endpoint);
  }
  if ('observation_time' in record) {
    parsed.observation_time = requireApiStringOrNull(record, 'observation_time', endpoint);
  }
  if ('coverage' in record) {
    parsed.coverage = record.coverage === null
      ? null
      : requireApiJsonObject(record.coverage, endpoint, 'coverage');
  }
  if ('spatial_resolution' in record) {
    parsed.spatial_resolution = requireApiStringOrNull(record, 'spatial_resolution', endpoint);
  }
  if ('units' in record) {
    const units = requireApiJsonObject(record.units, endpoint, 'units');
    if (!Object.values(units).every((unit) => typeof unit === 'string')) {
      return apiContract(endpoint, 'units values must be strings', record.units);
    }
    parsed.units = Object.fromEntries(
      Object.entries(units).map(([key, unit]) => [key, String(unit)]),
    );
  }
  if ('source_url' in record) {
    parsed.source_url = safeHttpUrl(record.source_url);
  }
  if ('partial' in record) {
    parsed.partial = requireApiBoolean(record, 'partial', endpoint);
  }
  if ('message' in record) {
    const message = requireApiStringOrNull(record, 'message', endpoint);
    if (message !== null) {
      parsed.message = message;
    }
  }
  return parsed;
};

export const parseGeospatialLayersResponse = (
  value: unknown,
): Pick<CatalogResponse, 'basemaps' | 'overlays' | 'cameras' | 'transit'> => {
  const endpoint = 'geospatial layers';
  const record = requireApiRecord(value, endpoint);
  return {
    basemaps: normalizeCapabilities(record.basemaps, endpoint, 'basemaps'),
    overlays: normalizeCapabilities(record.overlays, endpoint, 'overlays'),
    cameras: normalizeCapabilities(record.cameras, endpoint, 'cameras'),
    transit: normalizeCapabilities(record.transit, endpoint, 'transit'),
  };
};

export const parseGeospatialCredentialStatus = (
  value: unknown,
): GeospatialCredentialStatus => {
  const endpoint = 'geospatial credential status';
  const record = requireApiRecord(value, endpoint);
  return {
    provider: requireApiString(record, 'provider', endpoint),
    required: requireApiBoolean(record, 'required', endpoint),
    configured: requireApiBoolean(record, 'configured', endpoint),
  };
};

export const parseConversationCreateResponse = (
  value: unknown,
): ConversationCreateResponse => {
  const endpoint = 'conversation create';
  const record = requireApiRecord(value, endpoint);
  return {
    conversation_id: requireApiString(record, 'conversation_id', endpoint),
    title: requireApiStringOrNull(record, 'title', endpoint),
  };
};

export const parseGenericObjectResponse = (
  value: unknown,
  endpoint: string,
): GenericObjectResponse => requireApiRecord(value, endpoint);

const stringOrNull = (value: unknown): string | null => (
  typeof value === 'string' && value.trim() ? value : null
);

const numberOrNull = (value: unknown): number | null => (
  typeof value === 'number' && Number.isFinite(value) ? value : null
);

const isValidLatitude = (value: unknown): value is number => (
  isFiniteNumber(value) && value >= -90 && value <= 90
);

const isValidLongitude = (value: unknown): value is number => (
  isFiniteNumber(value) && value >= -180 && value <= 180
);

const normalizeBoundsTuple = (
  value: unknown,
): [number, number, number, number] | null => {
  if (
    !Array.isArray(value)
    || value.length !== 4
    || !value.every(isFiniteNumber)
  ) {
    return null;
  }
  const [west, south, east, north] = value;
  if (
    !isValidLongitude(west)
    || !isValidLatitude(south)
    || !isValidLongitude(east)
    || !isValidLatitude(north)
    || west > east
    || south > north
  ) {
    return null;
  }
  return [west, south, east, north];
};

const isValidGeoJsonCoordinateArray = (value: unknown): boolean => {
  if (!Array.isArray(value) || value.length === 0) {
    return false;
  }
  if (value.every(isFiniteNumber)) {
    return value.length >= 2 && isValidLongitude(value[0]) && isValidLatitude(value[1]);
  }
  return value.every(isValidGeoJsonCoordinateArray);
};

const isValidGeoJsonGeometry = (value: unknown): value is Record<string, JsonValue> => {
  if (!isRecord(value) || typeof value.type !== 'string') {
    return false;
  }
  if (value.type === 'GeometryCollection') {
    return Array.isArray(value.geometries)
      && value.geometries.every((geometry) => isValidGeoJsonGeometry(geometry));
  }
  if (!['Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'].includes(value.type)) {
    return false;
  }
  return isValidGeoJsonCoordinateArray(value.coordinates);
};

const normalizeGeoJsonFeatureCollection = (value: unknown): MapOverlayEntry['data'] | null => {
  if (!isRecord(value) || value.type !== 'FeatureCollection' || !Array.isArray(value.features)) {
    return null;
  }
  const features = value.features.map((feature) => {
    if (!isRecord(feature) || feature.type !== 'Feature' || !isValidGeoJsonGeometry(feature.geometry)) {
      return null;
    }
    if (feature.properties !== undefined && feature.properties !== null && !isJsonObject(feature.properties)) {
      return null;
    }
    return {
      type: 'Feature' as const,
      ...(typeof feature.id === 'string' || typeof feature.id === 'number' ? { id: feature.id } : {}),
      geometry: feature.geometry as GeoJsonFeatureCollection['features'][number]['geometry'],
      ...(feature.properties === undefined ? {} : { properties: feature.properties as JsonObject | null }),
    };
  });
  return features.every((feature): feature is NonNullable<typeof feature> => feature !== null)
    ? { type: 'FeatureCollection', features }
    : null;
};

const safeHttpUrl = (value: unknown): string | null => {
  if (typeof value !== 'string') {
    return null;
  }
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? value.slice(0, 500) : null;
  } catch {
    return null;
  }
};

const normalizeInspection = (value: unknown): MapInspection | null => {
  if (!isRecord(value) || typeof value.inspection_id !== 'string' || typeof value.title !== 'string') {
    return null;
  }
  const fields = Array.isArray(value.fields)
    ? value.fields.flatMap((field): MapInspection['fields'] => {
      if (!isRecord(field) || typeof field.key !== 'string' || typeof field.label !== 'string') {
        return [];
      }
      const scalar = field.value;
      if (scalar !== null && typeof scalar !== 'string' && typeof scalar !== 'number' && typeof scalar !== 'boolean') {
        return [];
      }
      return [{
        key: field.key.slice(0, 80),
        label: field.label.slice(0, 120),
        value: scalar,
        unit: typeof field.unit === 'string' ? field.unit.slice(0, 40) : null,
        category: typeof field.category === 'string' ? field.category : 'general',
        source_url: safeHttpUrl(field.source_url),
        order: typeof field.order === 'number' ? field.order : 0,
      }];
    })
    : [];
  return {
    inspection_id: value.inspection_id,
    title: value.title.slice(0, 240),
    association: typeof value.association === 'string' ? value.association : 'non_spatial',
    provider: typeof value.provider === 'string' ? value.provider : null,
    feature_id: typeof value.feature_id === 'string' ? value.feature_id : null,
    fields,
    source_url: safeHttpUrl(value.source_url),
    freshness: typeof value.freshness === 'string' ? value.freshness : null,
    stale: Boolean(value.stale),
    warnings: isStringArray(value.warnings) ? value.warnings.slice(0, 5) : [],
    geometry: isValidGeoJsonGeometry(value.geometry) ? value.geometry : null,
  };
};

const normalizeOverlayCollection = (value: unknown): OverlayCollectionState | null => {
  if (
    !isRecord(value)
    || typeof value.collection_id !== 'string'
    || !isFiniteNumber(value.revision)
    || value.revision < 0
    || !Array.isArray(value.instances)
  ) {
    return null;
  }
  const instances: OverlayInstance[] = [];
  for (const entry of value.instances) {
    if (
      !isRecord(entry)
      || typeof entry.instance_id !== 'string'
      || typeof entry.capability_id !== 'string'
      || typeof entry.label !== 'string'
      || typeof entry.provider !== 'string'
      || typeof entry.overlay_type !== 'string'
      || typeof entry.rendering_mode !== 'string'
      || typeof entry.scope_key !== 'string'
      || !isRecord(entry.scope)
      || typeof entry.visible !== 'boolean'
      || !isFiniteNumber(entry.opacity)
      || entry.opacity < 0
      || entry.opacity > 1
      || !isRecord(entry.render_variant)
      || !isRecord(entry.descriptor)
      || !Array.isArray(entry.inspections)
    ) {
      return null;
    }
    const renderVariant: Record<string, string | null> = {};
    for (const [key, item] of Object.entries(entry.render_variant)) {
      if (item !== null && typeof item !== 'string') {
        return null;
      }
      renderVariant[key] = item;
    }
    const inspections: MapInspection[] = [];
    for (const inspection of entry.inspections) {
      const normalized = normalizeInspection(inspection);
      if (!normalized) {
        return null;
      }
      inspections.push(normalized);
    }
    instances.push({
      instance_id: entry.instance_id,
      capability_id: entry.capability_id,
      label: entry.label,
      provider: entry.provider,
      overlay_type: entry.overlay_type,
      rendering_mode: entry.rendering_mode,
      scope_key: entry.scope_key,
      scope: entry.scope as Record<string, JsonValue>,
      resolved_location: isRecord(entry.resolved_location)
        ? entry.resolved_location as unknown as OverlayInstance['resolved_location']
        : undefined,
      viewport: isRecord(entry.viewport)
        ? entry.viewport as unknown as OverlayInstance['viewport']
        : undefined,
      visible: entry.visible,
      opacity: entry.opacity,
      render_variant: renderVariant,
      descriptor: entry.descriptor as Record<string, JsonValue>,
      inspections,
    });
  }
  return { collection_id: value.collection_id, revision: Math.max(0, value.revision), instances };
};

export const normalizeLayerRenderDescriptor = (
  value: unknown,
): GeospatialLayerRenderDescriptor | null => {
  if (!isRecord(value)) {
    return null;
  }
  const provider = stringOrNull(value.provider);
  const layerId = stringOrNull(value.layer_id);
  const renderingMode = stringOrNull(value.rendering_mode);
  const sourceProtocol = stringOrNull(value.source_protocol);
  if (!provider || !layerId || !renderingMode || !sourceProtocol) {
    return null;
  }
  return {
    provider,
    layer_id: layerId,
    rendering_mode: renderingMode,
    source_protocol: sourceProtocol,
    url: stringOrNull(value.url),
    tile_url_template: stringOrNull(value.tile_url_template),
    crs: stringOrNull(value.crs),
    format: stringOrNull(value.format),
    style: stringOrNull(value.style),
    time: stringOrNull(value.time),
    default_time: stringOrNull(value.default_time),
    tile_matrix_set: stringOrNull(value.tile_matrix_set),
    tile_size: numberOrNull(value.tile_size),
    min_zoom: numberOrNull(value.min_zoom),
    max_zoom: numberOrNull(value.max_zoom),
    attribution: isStringArray(value.attribution) ? value.attribution : [],
    attribution_url: safeHttpUrl(value.attribution_url),
    warnings: isStringArray(value.warnings) ? value.warnings : [],
  };
};

export const normalizeMapOverlayEntry = (value: unknown): MapOverlayEntry | null => {
  if (!isRecord(value) || typeof value.id !== 'string') {
    return null;
  }
  const render = normalizeLayerRenderDescriptor(value.render);
  const bounds = value.bounds === undefined ? undefined : normalizeBoundsTuple(value.bounds);
  if (value.bounds !== undefined && !bounds) {
    return null;
  }
  const normalizedBounds = bounds ?? undefined;
  const data = value.data === undefined ? undefined : normalizeGeoJsonFeatureCollection(value.data);
  if (value.data !== undefined && !data) {
    return null;
  }
  const normalizedData = data ?? undefined;
  return {
    id: String(value.id),
    instance_id: typeof value.instance_id === 'string' ? value.instance_id : undefined,
    capability_id: typeof value.capability_id === 'string' ? value.capability_id : undefined,
    label: String(value.label ?? value.id),
    provider: String(value.provider ?? render?.provider ?? 'unknown'),
    type: String(value.type ?? value.rendering_mode ?? render?.rendering_mode ?? 'metadata-only'),
    rendering_mode: typeof value.rendering_mode === 'string' ? value.rendering_mode : render?.rendering_mode,
    default_opacity: typeof value.default_opacity === 'number' ? value.default_opacity : undefined,
    visible: typeof value.visible === 'boolean' ? value.visible : undefined,
    url: stringOrNull(value.url ?? render?.url),
    tile_url_template: stringOrNull(value.tile_url_template ?? render?.tile_url_template) ?? undefined,
    layers: stringOrNull(value.layers) ?? undefined,
    layer_id: stringOrNull(value.layer_id ?? render?.layer_id) ?? undefined,
    source_layer: stringOrNull(value.source_layer) ?? undefined,
    tile_matrix_set: stringOrNull(value.tile_matrix_set ?? render?.tile_matrix_set) ?? undefined,
    tile_size: numberOrNull(value.tile_size ?? render?.tile_size) ?? undefined,
    min_zoom: numberOrNull(value.min_zoom ?? render?.min_zoom) ?? undefined,
    max_zoom: numberOrNull(value.max_zoom ?? render?.max_zoom) ?? undefined,
    bounds: normalizedBounds,
    attribution: stringOrNull(value.attribution) ?? render?.attribution?.join('; '),
    attribution_url: safeHttpUrl(value.attribution_url ?? render?.attribution_url),
    source_protocol: stringOrNull(value.source_protocol ?? render?.source_protocol) ?? undefined,
    data_format: stringOrNull(value.data_format) ?? undefined,
    geometry_type: stringOrNull(value.geometry_type) ?? undefined,
    crs: stringOrNull(value.crs ?? render?.crs),
    format: stringOrNull(value.format ?? render?.format),
    style: stringOrNull(value.style ?? render?.style),
    time: stringOrNull(value.time ?? render?.time),
    default_time: stringOrNull(value.default_time ?? render?.default_time),
    result_status: stringOrNull(value.result_status),
    fetched_at: stringOrNull(value.fetched_at),
    observation_time: stringOrNull(value.observation_time),
    coverage: safeJsonRecord(value.coverage),
    spatial_resolution: stringOrNull(value.spatial_resolution),
    units: safeStringRecord(value.units),
    source_url: stringOrNull(value.source_url),
    partial: typeof value.partial === 'boolean' ? value.partial : undefined,
    stale: typeof value.stale === 'boolean' ? value.stale : undefined,
    requested_variables: isStringArray(value.requested_variables) ? value.requested_variables : undefined,
    request_parameters: safeJsonRecord(value.request_parameters) ?? undefined,
    warnings: isStringArray(value.warnings) ? value.warnings : render?.warnings,
    data: normalizedData,
    inspections: Array.isArray(value.inspections)
      ? value.inspections.flatMap((inspection) => {
        const normalized = normalizeInspection(inspection);
        return normalized ? [normalized] : [];
      })
      : [],
    render,
  };
};

export const mapOverlayEntryFromInstance = (instance: OverlayInstance): MapOverlayEntry | null => (
  normalizeMapOverlayEntry({
    ...instance.descriptor,
    id: instance.instance_id,
    instance_id: instance.instance_id,
    capability_id: instance.capability_id,
    label: instance.label,
    provider: instance.provider,
    type: instance.overlay_type,
    rendering_mode: instance.rendering_mode,
    visible: instance.visible,
    default_opacity: instance.opacity,
    inspections: instance.inspections,
  })
);

export const normalizeMapSession = (value: unknown): MapSession | null => {
  const supersededFields = [
    'overlay_ids',
    'overlays',
    'requested_overlay_ids',
    'rendered_overlay_ids',
    'failed_overlays',
    'overlay_collection_revision',
    'inspections',
  ];
  if (!isRecord(value) || Array.isArray(value)) {
    return null;
  }
  const basemap = isRecord(value.basemap) ? value.basemap : null;
  const resolvedLocation = isRecord(value.resolved_location) ? value.resolved_location : null;
  const viewport = isRecord(value.viewport) ? value.viewport : null;
  const center = value.center === undefined || value.center === null
    ? null
    : isRecord(value.center) ? value.center : undefined;
  const bounds = value.bounds === undefined ? undefined : normalizeBoundsTuple(value.bounds);
  if (
    !isRecord(value)
    || typeof value.session_id !== 'string'
    || !resolvedLocation
    || !isValidLatitude(resolvedLocation.latitude)
    || !isValidLongitude(resolvedLocation.longitude)
    || typeof value.basemap_id !== 'string'
    || !viewport
    || !isValidLatitude(viewport.center_latitude)
    || !isValidLongitude(viewport.center_longitude)
    || !isFiniteNumber(viewport.radius_m)
    || viewport.radius_m <= 0
    || !basemap
    || typeof basemap.id !== 'string'
    || basemap.id !== value.basemap_id
    || center === undefined
    || (center !== null && (!isValidLatitude(center.latitude) || !isValidLongitude(center.longitude)))
    || (value.bounds !== undefined && !bounds)
    || supersededFields.some((field) => field in value)
  ) {
    return null;
  }
  const normalizedBounds = bounds ?? undefined;
  const overlayCollection = normalizeOverlayCollection(value.overlay_collection);
  if (!overlayCollection) {
    return null;
  }
  return {
    session_id: String(value.session_id),
    resolved_location: resolvedLocation as unknown as MapSession['resolved_location'],
    basemap_id: value.basemap_id,
    viewport: viewport as unknown as MapSession['viewport'],
    generated_at: typeof value.generated_at === 'string' ? value.generated_at : undefined,
    payload: isRecord(value.payload) ? value.payload as Record<string, JsonValue> : {},
    center: center as MapSession['center'],
    bounds: normalizedBounds,
    basemap: basemap as MapSession['basemap'],
    compliance_warnings: isStringArray(value.compliance_warnings) ? value.compliance_warnings : [],
    overlay_collection: overlayCollection,
  };
};

const TASK_STATUSES: readonly ConversationTaskSnapshot['tasks'][number]['status'][] = [
  'pending', 'in_progress', 'completed', 'failed', 'blocked', 'skipped', 'superseded',
];

const RUN_STATES: readonly AgentRunState[] = [
  'pending',
  'running',
  'updating',
  'waiting_for_clarification',
  'completed',
  'failed',
  'cancelled',
];

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0;

const isNonNegativeInteger = (value: unknown): value is number =>
  isFiniteNumber(value) && Number.isInteger(value) && value >= 0;

const isTaskStatus = (
  value: unknown,
): value is ConversationTaskSnapshot['tasks'][number]['status'] =>
  typeof value === 'string' && TASK_STATUSES.includes(value as ConversationTaskSnapshot['tasks'][number]['status']);

const normalizeTaskGoal = (
  value: unknown,
): NonNullable<ConversationTaskSnapshot['goal']> | null | undefined => {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)
    || !isNonEmptyString(value.id)
    || !isNonEmptyString(value.text)
    || !['active', 'completed', 'partial', 'superseded'].includes(String(value.status))
    || !isNonNegativeInteger(value.revision)) {
    return undefined;
  }
  return {
    id: value.id,
    text: value.text,
    status: value.status as NonNullable<ConversationTaskSnapshot['goal']>['status'],
    revision: value.revision,
  };
};

export const normalizeConversationTaskSnapshot = (
  value: unknown,
): ConversationTaskSnapshot | undefined => {
  if (
    !isJsonObject(value)
    || value.schema_version !== 3
    || !isNonEmptyString(value.conversation_key)
    || !Array.isArray(value.tasks)
    || !isRecord(value.geospatial_state)
    || !isStringArray(value.evidence_refs)
    || !isStringArray(value.assumptions)
    || !isStringArray(value.unresolved_questions)
  ) {
    return undefined;
  }

  const tasks: ConversationTaskSnapshot['tasks'] = [];
  for (const item of value.tasks) {
    if (!isJsonObject(item)
      || !isNonEmptyString(item.id)
      || !isNonEmptyString(item.description)
      || !isNonEmptyString(item.kind)
      || !isTaskStatus(item.status)
      || !isStringArray(item.depends_on)
      || typeof item.required !== 'boolean'
      || !isStringArray(item.input_refs)
      || !isStringArray(item.output_refs)
      || !isNonNegativeInteger(item.attempt_count)
      || !isNonNegativeInteger(item.scope_revision)) {
      return undefined;
    }

    const task: ConversationTaskSnapshot['tasks'][number] = {
      id: item.id,
      description: item.description,
      kind: item.kind,
      status: item.status,
      depends_on: item.depends_on,
      required: item.required,
      input_refs: item.input_refs,
      output_refs: item.output_refs,
      attempt_count: item.attempt_count,
      scope_revision: item.scope_revision,
    };
    if (item.last_failure === null) {
      task.last_failure = null;
    } else if (Object.prototype.hasOwnProperty.call(item, 'last_failure')) {
      if (!isJsonObject(item.last_failure)) {
        return undefined;
      }
      task.last_failure = item.last_failure;
    }
    tasks.push(task);
  }

  const snapshot: ConversationTaskSnapshot = {
    schema_version: 3,
    conversation_key: value.conversation_key,
    tasks,
    geospatial_state: value.geospatial_state,
    evidence_refs: value.evidence_refs,
    assumptions: value.assumptions,
    unresolved_questions: value.unresolved_questions,
  };

  if (Object.prototype.hasOwnProperty.call(value, 'current_task_id')) {
    if (value.current_task_id !== null && !isNonEmptyString(value.current_task_id)) {
      return undefined;
    }
    snapshot.current_task_id = value.current_task_id as string | null;
  }

  if (Object.prototype.hasOwnProperty.call(value, 'active_map_session')) {
    if (value.active_map_session === null) {
      snapshot.active_map_session = null;
    } else {
      const mapSession = normalizeMapSession(value.active_map_session);
      if (!mapSession) {
        return undefined;
      }
      snapshot.active_map_session = mapSession;
    }
  }

  if (Object.prototype.hasOwnProperty.call(value, 'goal')) {
    const goal = normalizeTaskGoal(value.goal);
    if (goal === undefined) {
      return undefined;
    }
    snapshot.goal = goal;
  }

  if (Object.prototype.hasOwnProperty.call(value, 'conversation_summary')) {
    if (value.conversation_summary !== null && !isJsonObject(value.conversation_summary)) {
      return undefined;
    }
    snapshot.conversation_summary = value.conversation_summary;
  }

  return snapshot;
};

const parseProviderLayerDescriptor = (value: unknown): GeospatialProviderLayerDescriptor | null => {
  if (!isRecord(value) || typeof value.layer_id !== 'string') {
    return null;
  }
  return {
    provider: String(value.provider ?? ''),
    layer_id: String(value.layer_id),
    title: String(value.title ?? value.layer_id),
    abstract: stringOrNull(value.abstract),
    rendering_mode: String(value.rendering_mode ?? 'metadata-only'),
    source_protocol: String(value.source_protocol ?? 'provider-api'),
    data_format: String(value.data_format ?? ''),
    geometry_type: String(value.geometry_type ?? ''),
    queryable: Boolean(value.queryable),
    crs: isStringArray(value.crs) ? value.crs : [],
    formats: isStringArray(value.formats) ? value.formats : [],
    styles: isStringArray(value.styles) ? value.styles : [],
    time_extent: stringOrNull(value.time_extent),
    default_time: stringOrNull(value.default_time),
    tile_matrix_sets: isStringArray(value.tile_matrix_sets) ? value.tile_matrix_sets : [],
    render: normalizeLayerRenderDescriptor(value.render),
    attribution: isStringArray(value.attribution) ? value.attribution : [],
    warnings: isStringArray(value.warnings) ? value.warnings : [],
  };
};

export const parseContextUsage = (input: unknown): ChatTurnResponse['context_usage'] => {
  if (!isRecord(input)) {
    return undefined;
  }
  const estimatedInputTokens = input.estimated_input_tokens;
  const usagePercent = input.usage_percent;
  if (!isFiniteNumber(estimatedInputTokens) || (usagePercent !== null && !isFiniteNumber(usagePercent))) {
    return undefined;
  }
  return {
    estimated_input_tokens: estimatedInputTokens,
    reported_input_tokens: isFiniteNumber(input.reported_input_tokens) ? input.reported_input_tokens : null,
    reported_output_tokens: isFiniteNumber(input.reported_output_tokens) ? input.reported_output_tokens : null,
    selected_context_window: isFiniteNumber(input.selected_context_window) ? input.selected_context_window : null,
    model_context_limit: isFiniteNumber(input.model_context_limit) ? input.model_context_limit : null,
    usage_percent: usagePercent,
    provider: typeof input.provider === 'string' ? input.provider : '',
    model: typeof input.model === 'string' ? input.model : '',
    usage_source: typeof input.usage_source === 'string' ? input.usage_source : 'estimated',
    reserved_output_tokens: isFiniteNumber(input.reserved_output_tokens) ? input.reserved_output_tokens : undefined,
    tool_schema_tokens: isFiniteNumber(input.tool_schema_tokens) ? input.tool_schema_tokens : undefined,
    response_schema_tokens: isFiniteNumber(input.response_schema_tokens) ? input.response_schema_tokens : undefined,
    safety_margin_tokens: isFiniteNumber(input.safety_margin_tokens) ? input.safety_margin_tokens : undefined,
    usable_prompt_budget_tokens: isFiniteNumber(input.usable_prompt_budget_tokens) ? input.usable_prompt_budget_tokens : null,
    current_conversation_tokens: isFiniteNumber(input.current_conversation_tokens) ? input.current_conversation_tokens : null,
    expected_output_tokens: isFiniteNumber(input.expected_output_tokens) ? input.expected_output_tokens : null,
    context_profile_source: typeof input.context_profile_source === 'string' ? input.context_profile_source : 'unknown',
    compaction_applied: Boolean(input.compaction_applied),
    phases: isRecord(input.phases) ? input.phases : undefined,
    peak_request_tokens: isFiniteNumber(input.peak_request_tokens) ? input.peak_request_tokens : null,
    total_input_tokens: isFiniteNumber(input.total_input_tokens) ? input.total_input_tokens : null,
    total_output_tokens: isFiniteNumber(input.total_output_tokens) ? input.total_output_tokens : null,
  };
};

export const buildModelDescription = (item: Record<string, unknown>): string => {
  const rawDescription = String(item.description ?? '').trim();
  const metadata = isRecord(item.metadata) ? item.metadata : {};
  const family = typeof metadata.family === 'string' ? metadata.family : '';
  const parameterSize = typeof metadata.parameter_size === 'string' ? metadata.parameter_size : '';
  const quantization = typeof metadata.quantization_level === 'string' ? metadata.quantization_level : '';
  const details = [family, parameterSize, quantization].filter(Boolean).join(' ');
  const technicalDescription = [family, parameterSize, quantization].filter(Boolean).join(' | ').toLowerCase();
  const normalizedDescription = rawDescription.toLowerCase();
  if (
    rawDescription
    && normalizedDescription !== 'local'
    && normalizedDescription !== technicalDescription
    && !normalizedDescription.startsWith('local ollama model ')
  ) {
    return rawDescription;
  }
  return details ? `Optimized for ${details}.` : 'General purpose local model.';
};

export const normalizeModelCards = (
  input: unknown,
  endpoint = 'chat model library',
  field = 'models',
): ModelCardDescriptor[] => requireApiArray(input, endpoint, field).map((raw, index) => {
  const item = requireApiRecord(raw, endpoint, `${field}[${index}]`);
  return {
    id: requireApiString(item, 'id', endpoint),
    name: requireApiString(item, 'name', endpoint),
    description: buildModelDescription({
      ...item,
      description: requireApiString(item, 'description', endpoint),
    }),
    provider: requireApiString(item, 'provider', endpoint),
    capabilities: requireApiStringArray(item, 'capabilities', endpoint),
    supports_tools: optionalApiNullableBoolean(item, 'supports_tools', endpoint),
    supports_structured_output: optionalApiNullableBoolean(item, 'supports_structured_output', endpoint),
    supports_vision: optionalApiNullableBoolean(item, 'supports_vision', endpoint),
    supports_embeddings: optionalApiNullableBoolean(item, 'supports_embeddings', endpoint),
    tool_support_source: requireApiString(item, 'tool_support_source', endpoint),
    context_window_tokens: optionalApiNumber(item, 'context_window_tokens', endpoint) ?? null,
    maximum_output_tokens: optionalApiNumber(item, 'maximum_output_tokens', endpoint) ?? null,
    context_profile_source: requireApiString(item, 'context_profile_source', endpoint),
    metadata: requireApiJsonObject(item.metadata, endpoint, `${field}[${index}].metadata`),
  };
});

export const parseModelLibrarySources = (
  input: unknown,
  endpoint = 'chat model library',
): ModelLibraryResponse['sources'] => {
  const record = requireApiRecord(input, endpoint, 'sources');
  const sources: ModelLibraryResponse['sources'] = {};
  Object.entries(record).forEach(([key, value]) => {
    const source = requireApiRecord(value, endpoint, `sources.${key}`);
    sources[key] = {
      ok: requireApiBoolean(source, 'ok', endpoint),
      reachable: optionalApiNullableBoolean(source, 'reachable', endpoint) ?? null,
      message: optionalApiString(source, 'message', endpoint) ?? null,
      model_count: optionalApiNumber(source, 'model_count', endpoint) ?? null,
    };
  });
  return sources;
};

export const parseModelLibraryResponse = (value: unknown): ModelLibraryResponse => {
  const endpoint = 'chat model library';
  const record = requireApiRecord(value, endpoint);
  return {
    cloud: normalizeModelCards(record.cloud, endpoint, 'cloud'),
    local: normalizeModelCards(record.local, endpoint, 'local'),
    sources: parseModelLibrarySources(record.sources, endpoint),
  };
};

export const parseCatalogResponse = (value: unknown): CatalogResponse => {
  const endpoint = 'geospatial catalog';
  const record = requireApiRecord(value, endpoint);
  const normalized = normalizeCapabilities(record.capabilities, endpoint, 'capabilities');
  const providers = normalizeCapabilities(record.providers, endpoint, 'providers');
  const basemaps = normalizeCapabilities(record.basemaps, endpoint, 'basemaps');
  const overlays = normalizeCapabilities(record.overlays, endpoint, 'overlays');
  const tools = normalizeCapabilities(record.tools, endpoint, 'tools');
  const cameras = normalizeCapabilities(record.cameras, endpoint, 'cameras');
  const transit = normalizeCapabilities(record.transit, endpoint, 'transit');
  return {
    capabilities: normalized,
    providers,
    basemaps,
    overlays,
    cameras,
    transit,
    tools,
  };
};

export const parseModelSettingsResponse = (value: unknown): ModelSettingsResponse => {
  const endpoint = 'model settings';
  const record = requireApiRecord(value, endpoint);
  const activeProviderMode = requireApiString(record, 'active_provider_mode', endpoint);
  if (activeProviderMode !== 'local' && activeProviderMode !== 'cloud') {
    return apiContract(endpoint, 'active_provider_mode is unsupported', activeProviderMode);
  }
  const credentialHealthRecord = requireApiRecord(record.credential_health, endpoint, 'credential_health');
  const credentialHealth: ModelSettingsResponse['credential_health'] = {};
  Object.entries(credentialHealthRecord).forEach(([provider, providerValue]) => {
    const providerRecord = requireApiRecord(providerValue, endpoint, `credential_health.${provider}`);
    const statuses: Record<string, string> = {};
    Object.entries(providerRecord).forEach(([key, status]) => {
      statuses[key] = requireApiString(providerRecord, key, endpoint);
    });
    credentialHealth[provider] = statuses;
  });
  const selectedModelContextRecord = requireApiRecord(
    record.selected_model_context,
    endpoint,
    'selected_model_context',
  );
  const selectedModelContext: SelectedModelContext = {
    provider: requireApiString(selectedModelContextRecord, 'provider', endpoint),
    model: requireApiString(selectedModelContextRecord, 'model', endpoint),
    context_window_tokens: optionalApiNumber(
      selectedModelContextRecord,
      'context_window_tokens',
      endpoint,
    ) ?? null,
    maximum_output_tokens: optionalApiNumber(
      selectedModelContextRecord,
      'maximum_output_tokens',
      endpoint,
    ) ?? null,
    context_profile_source: requireApiString(
      selectedModelContextRecord,
      'context_profile_source',
      endpoint,
    ),
  };
  return {
    active_provider_mode: activeProviderMode,
    agent_model_provider: requireApiString(record, 'agent_model_provider', endpoint),
    agent_model_name: requireApiString(record, 'agent_model_name', endpoint),
    ollama_url: requireApiString(record, 'ollama_url', endpoint),
    openai_base_url: requireApiStringOrNull(record, 'openai_base_url', endpoint),
    google_base_url: requireApiStringOrNull(record, 'google_base_url', endpoint),
    deepseek_base_url: requireApiStringOrNull(record, 'deepseek_base_url', endpoint),
    credentials: parseBooleanCredentialMap(record.credentials, endpoint),
    credential_health: credentialHealth,
    selected_model_context: selectedModelContext,
  };
};

export const parseOllamaRefreshResponse = (value: unknown): GenericObjectResponse => {
  const endpoint = 'Ollama model refresh';
  const record = requireApiRecord(value, endpoint);
  return {
    status: requireApiString(record, 'status', endpoint),
    library_models: requireApiStringArray(record, 'library_models', endpoint),
    local_models: requireApiStringArray(record, 'local_models', endpoint),
    local_model_capabilities: normalizeModelCards(
      record.local_model_capabilities,
      endpoint,
      'local_model_capabilities',
    ),
  };
};

export const parseOllamaHealthResponse = (value: unknown): OllamaHealthResponse => {
  const endpoint = 'Ollama health';
  const record = requireApiRecord(value, endpoint);
  if (!('ok' in record) || (record.ok !== null && typeof record.ok !== 'boolean')) {
    return apiContract(endpoint, 'ok must be a boolean or null', record.ok);
  }
  return {
    ...record,
    ok: record.ok as boolean | null,
    detail: requireApiStringOrNull(record, 'detail', endpoint),
  };
};

export const parseChatTurnResponse = (value: unknown): ChatTurnResponse => {
  const endpoint = 'chat turn';
  const record = requireApiRecord(value, endpoint);
  const operation = optionalApiRecord(record, 'operation', endpoint);
  const toolPayload = optionalApiRecord(record, 'tool_payload', endpoint);
  if (toolPayload && 'map_session' in toolPayload) {
    if (toolPayload.map_session === null) {
      toolPayload.map_session = null;
    } else {
      const normalizedToolMap = normalizeMapSession(toolPayload.map_session);
      if (!normalizedToolMap) {
        return apiContract(endpoint, 'tool_payload.map_session is malformed', toolPayload.map_session);
      }
      toolPayload.map_session = normalizedToolMap;
    }
  }

  let mapSession: MapSession | null | undefined;
  if (!('map_session' in record) || record.map_session === undefined) {
    mapSession = undefined;
  } else if (record.map_session === null) {
    mapSession = null;
  } else {
    mapSession = normalizeMapSession(record.map_session);
    if (!mapSession) {
      return apiContract(endpoint, 'map_session is malformed', record.map_session);
    }
  }

  const contextUsage = record.context_usage === undefined
    ? undefined
    : record.context_usage === null
      ? null
      : parseContextUsage(record.context_usage);
  if (record.context_usage !== undefined && record.context_usage !== null && !contextUsage) {
    return apiContract(endpoint, 'context_usage is malformed', record.context_usage);
  }

  const taskSnapshot = record.task_snapshot === undefined
    ? undefined
    : record.task_snapshot === null
      ? null
      : normalizeConversationTaskSnapshot(record.task_snapshot);
  if (record.task_snapshot !== undefined && record.task_snapshot !== null && !taskSnapshot) {
    return apiContract(endpoint, 'task_snapshot is malformed', record.task_snapshot);
  }

  const toolPlan = optionalApiRecord(record, 'tool_plan', endpoint);
  const failureDiagnostic = optionalApiRecord(record, 'failure_diagnostic', endpoint);
  const visualizationUpdate = optionalApiRecord(record, 'visualization_update', endpoint);
  const contextRevision = optionalApiNumber(record, 'context_revision', endpoint);

  return {
    conversation_id: requireString(record.conversation_id, 'conversation_id'),
    request_id: requireString(record.request_id, 'request_id'),
    assistant_message: requireString(record.assistant_message, 'assistant_message'),
    turn_contract: requireRecord(record.turn_contract, 'turn_contract') as unknown as ChatTurnResponse['turn_contract'],
    decision: requireRecord(record.decision, 'decision') as unknown as ChatTurnResponse['decision'],
    operation: operation as unknown as ChatTurnResponse['operation'],
    tool_payload: toolPayload as ChatTurnResponse['tool_payload'],
    map_session: mapSession,
    memory_snapshot: requireApiJsonObject(record.memory_snapshot, endpoint, 'memory_snapshot'),
    context_usage: contextUsage,
    task_snapshot: taskSnapshot as unknown as ChatTurnResponse['task_snapshot'],
    tool_plan: toolPlan as unknown as ChatTurnResponse['tool_plan'],
    failure_diagnostic: failureDiagnostic as unknown as ChatTurnResponse['failure_diagnostic'],
    visualization_update: visualizationUpdate as unknown as ChatTurnResponse['visualization_update'],
    context_revision: contextRevision,
  };
};

const normalizeConversationMessage = (value: unknown): ChatMessage | undefined => {
  if (!isRecord(value)
    || !isNonEmptyString(value.role)
    || !['user', 'assistant', 'system', 'tool'].includes(value.role)
    || typeof value.content !== 'string'
    || !isNonEmptyString(value.created_at)) {
    return undefined;
  }
  return {
    role: value.role as ChatRole,
    content: value.content,
    created_at: value.created_at,
    kind: 'normal',
  };
};

const normalizeActiveConversationRun = (
  value: unknown,
): ActiveConversationRunSnapshot | null | undefined => {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)
    || !isNonEmptyString(value.run_id)
    || !isNonNegativeInteger(value.run_version)
    || value.run_version < 1
    || typeof value.state !== 'string'
    || !RUN_STATES.includes(value.state as AgentRunState)) {
    return undefined;
  }
  return {
    run_id: value.run_id,
    run_version: value.run_version,
    state: value.state as AgentRunState,
  };
};

export const parseConversationSnapshotResponse = (
  value: unknown,
): ConversationSnapshotResponse => {
  if (!isJsonObject(value)
    || !isNonEmptyString(value.conversation_id)
    || !isNonNegativeInteger(value.context_revision)
    || !Array.isArray(value.messages)
    || !isJsonObject(value.memory_snapshot)) {
    throw new Error('Unexpected conversation snapshot response format');
  }

  const parsedMessages = value.messages.map(normalizeConversationMessage);
  if (parsedMessages.some((message) => message === undefined)) {
    throw new Error('Unexpected conversation snapshot message format');
  }
  const messages = parsedMessages.filter((message): message is ChatMessage => message !== undefined);

  const taskSnapshot = value.task_snapshot === undefined || value.task_snapshot === null
    ? value.task_snapshot ?? undefined
    : normalizeConversationTaskSnapshot(value.task_snapshot);
  if (value.task_snapshot !== undefined
    && value.task_snapshot !== null
    && !taskSnapshot) {
    throw new Error('Unexpected conversation snapshot task format');
  }

  const mapSession = value.map_session === undefined || value.map_session === null
    ? value.map_session ?? undefined
    : normalizeMapSession(value.map_session);
  if (value.map_session !== undefined
    && value.map_session !== null
    && !mapSession) {
    throw new Error('Unexpected conversation snapshot map format');
  }

  const activeRun = value.active_run === undefined || value.active_run === null
    ? value.active_run ?? undefined
    : normalizeActiveConversationRun(value.active_run);
  if (value.active_run !== undefined
    && value.active_run !== null
    && !activeRun) {
    throw new Error('Unexpected conversation snapshot run format');
  }

  if (value.title !== undefined && value.title !== null && typeof value.title !== 'string') {
    throw new Error('Unexpected conversation snapshot title format');
  }

  return {
    conversation_id: value.conversation_id,
    title: value.title as string | null | undefined,
    context_revision: value.context_revision,
    messages,
    task_snapshot: taskSnapshot,
    memory_snapshot: value.memory_snapshot,
    map_session: mapSession,
    active_run: activeRun,
  };
};
