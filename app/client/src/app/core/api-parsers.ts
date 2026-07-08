import {
  CatalogResponse,
  ChatTurnResponse,
  GeospatialLayerRenderDescriptor,
  GeospatialProviderAccountSetup,
  GeospatialProviderAccountSetupListResponse,
  GeospatialProviderLayerDescriptor,
  JsonValue,
  MapOverlayEntry,
  MapSession,
  ModelCardDescriptor,
  ModelLibraryResponse,
  ModelSettingsResponse,
} from './types';
import { isRecord, isStringArray } from './type-guards';

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
    endpoint_health: typeof item.endpoint_health === 'string' ? item.endpoint_health : undefined,
    auth_mode: typeof item.auth_mode === 'string' ? item.auth_mode : undefined,
    official_docs_url: typeof item.official_docs_url === 'string' ? item.official_docs_url : undefined,
    capability_kind: typeof item.capability_kind === 'string'
      ? item.capability_kind
      : (typeof item.capabilityKind === 'string' ? item.capabilityKind : undefined),
    rendering_mode: typeof item.rendering_mode === 'string'
      ? item.rendering_mode
      : (typeof item.renderingMode === 'string' ? item.renderingMode : undefined),
    reliability: isRecord(item.reliability)
      ? {
        status: String(item.reliability.status ?? 'unknown'),
        lastAudited: typeof item.reliability.lastAudited === 'string'
          ? item.reliability.lastAudited
          : undefined,
        knownLimitations: isStringArray(item.reliability.knownLimitations)
          ? item.reliability.knownLimitations
          : undefined,
      }
      : undefined,
    auth: isRecord(item.auth)
      ? {
        type: String(item.auth.type ?? 'none'),
        required: Boolean(item.auth.required),
        providerKey: typeof item.auth.providerKey === 'string' ? item.auth.providerKey : null,
        accessPageProviderId: typeof item.auth.accessPageProviderId === 'string'
          ? item.auth.accessPageProviderId
          : null,
      }
      : undefined,
    action_tags: Array.isArray(item.action_tags)
      ? item.action_tags.filter((v): v is string => typeof v === 'string')
      : [],
    task_tags: Array.isArray(item.task_tags)
      ? item.task_tags.filter((v): v is string => typeof v === 'string')
      : [],
    metadata: isRecord(item.metadata) ? item.metadata as Record<string, JsonValue> : {},
  }));

interface GeospatialProviderSignupFieldDto {
  key?: unknown;
  label?: unknown;
  field_type?: unknown;
  required?: unknown;
  sensitive?: unknown;
  help_text?: unknown;
}

interface GeospatialProviderSignupAutomationDto {
  support?: unknown;
  signup_url?: unknown;
  developer_portal_url?: unknown;
  docs_url?: unknown;
  required_fields?: unknown;
  user_action_notes?: unknown;
  safety_notes?: unknown;
  experimental?: unknown;
  experimental_label?: unknown;
}

interface GeospatialProviderAccountSetupDto {
  provider_id?: unknown;
  name?: unknown;
  requires_credentials?: unknown;
  auth_mode?: unknown;
  docs_url?: unknown;
  environment_variable?: unknown;
  configured?: unknown;
  instructions?: unknown;
  automation?: unknown;
  credential_storage_key?: unknown;
  credential_label?: unknown;
  key_format_hint?: unknown;
  validation_supported?: unknown;
}

export const mapGeospatialProviderSignupField = (
  dto: GeospatialProviderSignupFieldDto,
): GeospatialProviderAccountSetup['automation']['requiredFields'][number] => ({
  key: String(dto.key ?? ''),
  label: String(dto.label ?? dto.key ?? ''),
  fieldType: dto.field_type === 'email' || dto.field_type === 'textarea' || dto.field_type === 'select'
    ? dto.field_type
    : 'text',
  required: dto.required !== false,
  sensitive: Boolean(dto.sensitive),
  helpText: typeof dto.help_text === 'string' ? dto.help_text : null,
});

export const mapGeospatialProviderSignupAutomation = (
  dto: GeospatialProviderSignupAutomationDto,
): GeospatialProviderAccountSetup['automation'] => ({
  support: dto.support === 'guided_playwright' || dto.support === 'agent_assisted' || dto.support === 'unsupported'
    ? dto.support
    : 'manual_only',
  signupUrl: typeof dto.signup_url === 'string' ? dto.signup_url : null,
  developerPortalUrl: typeof dto.developer_portal_url === 'string' ? dto.developer_portal_url : null,
  docsUrl: typeof dto.docs_url === 'string' ? dto.docs_url : null,
  requiredFields: Array.isArray(dto.required_fields)
    ? dto.required_fields
      .filter((item): item is GeospatialProviderSignupFieldDto => isRecord(item))
      .map(mapGeospatialProviderSignupField)
      .filter((field) => !field.sensitive)
    : [],
  userActionNotes: isStringArray(dto.user_action_notes) ? dto.user_action_notes : [],
  safetyNotes: isStringArray(dto.safety_notes) ? dto.safety_notes : [],
  experimental: dto.experimental !== false,
  experimentalLabel: typeof dto.experimental_label === 'string' ? dto.experimental_label : 'Experimental guided setup',
});

export const mapGeospatialProviderAccountSetup = (
  dto: GeospatialProviderAccountSetupDto,
): GeospatialProviderAccountSetup => ({
  providerId: String(dto.provider_id ?? ''),
  name: String(dto.name ?? dto.provider_id ?? ''),
  requiresCredentials: Boolean(dto.requires_credentials),
  authMode: String(dto.auth_mode ?? 'api-key'),
  docsUrl: typeof dto.docs_url === 'string' ? dto.docs_url : null,
  environmentVariable: typeof dto.environment_variable === 'string' ? dto.environment_variable : null,
  configured: Boolean(dto.configured),
  instructions: isStringArray(dto.instructions) ? dto.instructions : [],
  automation: mapGeospatialProviderSignupAutomation(isRecord(dto.automation) ? dto.automation : {}),
  credentialStorageKey: String(dto.credential_storage_key ?? dto.provider_id ?? ''),
  credentialLabel: String(dto.credential_label ?? 'api_key'),
  keyFormatHint: typeof dto.key_format_hint === 'string' ? dto.key_format_hint : null,
  validationSupported: Boolean(dto.validation_supported),
});

export const parseGeospatialProviderAccountSetups = (
  value: unknown,
): GeospatialProviderAccountSetupListResponse => {
  const providers = isRecord(value) && Array.isArray(value.providers)
    ? value.providers
      .filter((item): item is GeospatialProviderAccountSetupDto => isRecord(item))
      .map(mapGeospatialProviderAccountSetup)
    : [];
  return { providers };
};

const stringOrNull = (value: unknown): string | null => (
  typeof value === 'string' && value.trim() ? value : null
);

const numberOrNull = (value: unknown): number | null => (
  typeof value === 'number' && Number.isFinite(value) ? value : null
);

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
    warnings: isStringArray(value.warnings) ? value.warnings : [],
  };
};

export const normalizeMapOverlayEntry = (value: unknown): MapOverlayEntry | null => {
  if (!isRecord(value) || typeof value.id !== 'string') {
    return null;
  }
  const render = normalizeLayerRenderDescriptor(value.render);
  return {
    id: String(value.id),
    label: String(value.label ?? value.id),
    provider: String(value.provider ?? render?.provider ?? 'unknown'),
    type: String(value.type ?? value.rendering_mode ?? render?.rendering_mode ?? 'metadata-only'),
    rendering_mode: typeof value.rendering_mode === 'string' ? value.rendering_mode : render?.rendering_mode,
    default_opacity: typeof value.default_opacity === 'number' ? value.default_opacity : undefined,
    url: stringOrNull(value.url ?? render?.url),
    tile_url_template: stringOrNull(value.tile_url_template ?? render?.tile_url_template) ?? undefined,
    layers: stringOrNull(value.layers) ?? undefined,
    layer_id: stringOrNull(value.layer_id ?? render?.layer_id) ?? undefined,
    source_layer: stringOrNull(value.source_layer) ?? undefined,
    tile_matrix_set: stringOrNull(value.tile_matrix_set ?? render?.tile_matrix_set) ?? undefined,
    tile_size: numberOrNull(value.tile_size ?? render?.tile_size) ?? undefined,
    minzoom: numberOrNull(value.minzoom ?? render?.min_zoom) ?? undefined,
    maxzoom: numberOrNull(value.maxzoom ?? render?.max_zoom) ?? undefined,
    render_params: isRecord(value.render_params) ? value.render_params as Record<string, JsonValue> : undefined,
    bounds: Array.isArray(value.bounds) && value.bounds.length === 4
      ? value.bounds as [number, number, number, number]
      : undefined,
    attribution: stringOrNull(value.attribution) ?? render?.attribution?.join('; '),
    source_protocol: stringOrNull(value.source_protocol ?? render?.source_protocol) ?? undefined,
    data_format: stringOrNull(value.data_format) ?? undefined,
    geometry_type: stringOrNull(value.geometry_type) ?? undefined,
    crs: stringOrNull(value.crs ?? render?.crs),
    format: stringOrNull(value.format ?? render?.format),
    style: stringOrNull(value.style ?? render?.style),
    time: stringOrNull(value.time ?? render?.time),
    default_time: stringOrNull(value.default_time ?? render?.default_time),
    warnings: isStringArray(value.warnings) ? value.warnings : render?.warnings,
    render,
  };
};

export const normalizeMapSession = (value: unknown): MapSession | null => {
  if (!isRecord(value) || typeof value.session_id !== 'string' || !isRecord(value.resolved_location)) {
    return null;
  }
  const overlays = Array.isArray(value.overlays)
    ? value.overlays.map(normalizeMapOverlayEntry).filter((item): item is MapOverlayEntry => item !== null)
    : [];
  return {
    ...value,
    session_id: String(value.session_id),
    resolved_location: value.resolved_location as unknown as MapSession['resolved_location'],
    basemap_id: String(value.basemap_id ?? ''),
    overlay_ids: isStringArray(value.overlay_ids) ? value.overlay_ids : overlays.map((overlay) => overlay.id),
    viewport: isRecord(value.viewport) ? value.viewport as unknown as MapSession['viewport'] : {
      center_latitude: 0,
      center_longitude: 0,
      radius_m: 2500,
    },
    payload: isRecord(value.payload) ? value.payload as Record<string, JsonValue> : {},
    center: isRecord(value.center) ? value.center as MapSession['center'] : undefined,
    bounds: Array.isArray(value.bounds) ? value.bounds as number[] : undefined,
    basemap: isRecord(value.basemap) ? value.basemap as MapSession['basemap'] : undefined,
    overlays,
    requested_overlay_ids: isStringArray(value.requested_overlay_ids) ? value.requested_overlay_ids : undefined,
    rendered_overlay_ids: isStringArray(value.rendered_overlay_ids)
      ? value.rendered_overlay_ids
      : overlays.map((overlay) => overlay.id),
    failed_overlays: Array.isArray(value.failed_overlays)
      ? value.failed_overlays.filter((item): item is { id: string; reason: string } => (
        isRecord(item) && typeof item.id === 'string' && typeof item.reason === 'string'
      ))
      : [],
    compliance_warnings: isStringArray(value.compliance_warnings) ? value.compliance_warnings : [],
  };
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

export const normalizeModelCards = (input: unknown): ModelCardDescriptor[] => {
  if (!Array.isArray(input)) {
    return [];
  }
  return input
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((item) => {
      const capabilities = isStringArray(item.capabilities) ? item.capabilities : [];
      return {
        id: String(item.id ?? item.name ?? ''),
        name: String(item.name ?? item.id ?? ''),
        description: buildModelDescription(item),
        provider: String(item.provider ?? ''),
        capabilities,
        supports_tools: typeof item.supports_tools === 'boolean' ? item.supports_tools : capabilities.includes('tools'),
        supports_structured_output: typeof item.supports_structured_output === 'boolean'
          ? item.supports_structured_output
          : capabilities.includes('structured') || capabilities.includes('structured_output'),
        supports_vision: typeof item.supports_vision === 'boolean' ? item.supports_vision : capabilities.includes('vision'),
        supports_embeddings: typeof item.supports_embeddings === 'boolean'
          ? item.supports_embeddings
          : capabilities.includes('embeddings'),
        tool_support_source: typeof item.tool_support_source === 'string' ? item.tool_support_source : 'unknown',
        metadata: isRecord(item.metadata) ? item.metadata as Record<string, JsonValue> : {},
      };
    });
};

export const parseModelLibrarySources = (
  input: unknown,
): ModelLibraryResponse['sources'] => {
  if (!isRecord(input)) {
    return {};
  }
  const sources: ModelLibraryResponse['sources'] = {};
  Object.entries(input).forEach(([key, value]) => {
    if (!isRecord(value)) {
      return;
    }
    sources[key] = {
      ok: Boolean(value.ok),
      reachable: typeof value.reachable === 'boolean' ? value.reachable : null,
      message: typeof value.message === 'string' ? value.message : null,
      model_count: typeof value.model_count === 'number' ? value.model_count : null,
    };
  });
  return sources;
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
  const cameras = normalizeCapabilities(value.cameras);
  const transit = normalizeCapabilities(value.transit);
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
  if (!isRecord(value)) {
    throw new Error('Unexpected settings response format');
  }
  return {
    active_provider_mode: (value.active_provider_mode === 'local' ? 'local' : 'cloud'),
    agent_model_provider: String(value.agent_model_provider ?? ''),
    agent_model_name: String(value.agent_model_name ?? ''),
    ollama_url: String(value.ollama_url ?? 'http://127.0.0.1:11434'),
    openai_base_url: typeof value.openai_base_url === 'string' ? value.openai_base_url : null,
    google_base_url: typeof value.google_base_url === 'string' ? value.google_base_url : null,
    deepseek_base_url: typeof value.deepseek_base_url === 'string' ? value.deepseek_base_url : null,
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
  const operation = isRecord(value.operation) ? { ...value.operation } as Record<string, unknown> : undefined;
  if (operation && isRecord(operation.map_session)) {
    operation.map_session = normalizeMapSession(operation.map_session);
  }
  const toolPayload = isRecord(value.tool_payload) ? { ...value.tool_payload } as Record<string, unknown> : undefined;
  if (toolPayload && isRecord(toolPayload.map_session)) {
    toolPayload.map_session = normalizeMapSession(toolPayload.map_session);
  }

  return {
    request_id: requireString(value.request_id, 'request_id'),
    session_id: requireNumber(value.session_id, 'session_id'),
    assistant_message: requireString(value.assistant_message, 'assistant_message'),
    turn_contract: requireRecord(value.turn_contract, 'turn_contract') as unknown as ChatTurnResponse['turn_contract'],
    decision: requireRecord(value.decision, 'decision') as unknown as ChatTurnResponse['decision'],
    operation: operation as unknown as ChatTurnResponse['operation'],
    tool_payload: toolPayload as ChatTurnResponse['tool_payload'],
    map_session: normalizeMapSession(value.map_session),
    memory_snapshot: isRecord(value.memory_snapshot) ? value.memory_snapshot as Record<string, JsonValue> : {},
    context_usage: parseContextUsage(value.context_usage),
    task_snapshot: isRecord(value.task_snapshot) ? value.task_snapshot as unknown as ChatTurnResponse['task_snapshot'] : undefined,
    tool_plan: isRecord(value.tool_plan) ? value.tool_plan as unknown as ChatTurnResponse['tool_plan'] : undefined,
    failure_diagnostic: isRecord(value.failure_diagnostic)
      ? value.failure_diagnostic as unknown as ChatTurnResponse['failure_diagnostic']
      : undefined,
    visualization_update: isRecord(value.visualization_update)
      ? value.visualization_update as unknown as ChatTurnResponse['visualization_update']
      : undefined,
  };
};
