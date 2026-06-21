import {
  ModelCardDescriptor,
  ModelProviderMode,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
} from './types';

export type ModelRole = 'parser' | 'chat' | 'agent';

export const MODEL_ROLES: readonly ModelRole[] = ['parser', 'chat', 'agent'];

export const MODEL_ROLE_LABELS: Record<ModelRole, string> = {
  parser: 'Parser',
  chat: 'Chat',
  agent: 'Agent',
};

const ROLE_FIELD_MAP: Record<ModelRole, { provider: keyof ModelSettingsResponse; name: keyof ModelSettingsResponse }> = {
  parser: { provider: 'parser_model_provider', name: 'parser_model_name' },
  chat: { provider: 'chat_model_provider', name: 'chat_model_name' },
  agent: { provider: 'agent_model_provider', name: 'agent_model_name' },
};

const normalizeSettingField = (value: ModelSettingsResponse[keyof ModelSettingsResponse]): string =>
  typeof value === 'string' ? value.trim() : '';

const toSelectionUpdateCredentials = (
  credentials: ModelSettingsResponse['credentials'],
): ModelSettingsUpdateRequest['credentials'] => {
  const updateCredentials: ModelSettingsUpdateRequest['credentials'] = {};
  Object.keys(credentials).forEach((provider) => {
    updateCredentials[provider] = {};
  });
  return updateCredentials;
};

export const modelRoleLabel = (role: ModelRole): string => MODEL_ROLE_LABELS[role];

export const modelRoleStatusLabel = (role: ModelRole): string => modelRoleLabel(role).toLowerCase();

export const isModelSelectedForRole = (
  settings: ModelSettingsResponse,
  role: ModelRole,
  model: ModelCardDescriptor,
): boolean => {
  const roleFields = ROLE_FIELD_MAP[role];
  const selectedProvider = normalizeSettingField(settings[roleFields.provider]);
  const selectedName = normalizeSettingField(settings[roleFields.name]);
  return model.provider === selectedProvider && model.name === selectedName;
};

export const roleDisabledReason = (model: ModelCardDescriptor, role: ModelRole): string | null => {
  if (role === 'agent' && !model.supports_tools) {
    return 'Agent role requires native tool calling.';
  }
  if (role === 'parser' && !model.supports_structured_output) {
    return 'Parser role requires structured output.';
  }
  return null;
};

export const canAssignRole = (model: ModelCardDescriptor, role: ModelRole): boolean =>
  roleDisabledReason(model, role) === null;

export const buildModelSelectionPayload = (
  settings: ModelSettingsResponse,
  role: ModelRole,
  model: ModelCardDescriptor,
): ModelSettingsUpdateRequest => {
  const disabledReason = roleDisabledReason(model, role);
  if (disabledReason) {
    throw new Error(disabledReason);
  }
  const roleFields = ROLE_FIELD_MAP[role];
  const nextProviderMode: ModelProviderMode = model.provider === 'ollama' ? 'local' : 'cloud';
  return {
    active_provider_mode: nextProviderMode,
    chat_model_provider: settings.chat_model_provider,
    chat_model_name: settings.chat_model_name,
    parser_model_provider: settings.parser_model_provider,
    parser_model_name: settings.parser_model_name,
    agent_model_provider: settings.agent_model_provider,
    agent_model_name: settings.agent_model_name,
    ollama_url: settings.ollama_url,
    openai_base_url: settings.openai_base_url,
    google_base_url: settings.google_base_url,
    deepseek_base_url: settings.deepseek_base_url,
    [roleFields.provider]: model.provider,
    [roleFields.name]: model.name,
    credentials: toSelectionUpdateCredentials(settings.credentials),
  };
};

export const mergeModelCard = (current: ModelCardDescriptor, next: ModelCardDescriptor): ModelCardDescriptor => {
  const currentDescription = current.description.trim();
  const nextDescription = next.description.trim();
  const richerDescription = nextDescription.length > currentDescription.length ? nextDescription : currentDescription;
  return {
    ...current,
    ...next,
    description: richerDescription || current.description || next.description,
    capabilities: next.capabilities.length ? next.capabilities : current.capabilities,
    metadata: { ...current.metadata, ...next.metadata },
  };
};

export const mergeModelCards = (...groups: ModelCardDescriptor[][]): ModelCardDescriptor[] => {
  const models = new Map<string, ModelCardDescriptor>();
  groups.flat().forEach((model) => {
    const key = `${model.provider}:${model.id}`;
    const current = models.get(key);
    models.set(key, current ? mergeModelCard(current, model) : model);
  });
  return [...models.values()];
};

export const baseModelName = (value: string): string =>
  value.toLowerCase().split('/').pop()?.split(':')[0] ?? '';

export const findOllamaLibraryMatch = (
  model: ModelCardDescriptor,
  library: ModelCardDescriptor[],
): ModelCardDescriptor | undefined => {
  const modelKeys = new Set([
    model.id.toLowerCase(),
    model.name.toLowerCase(),
    baseModelName(model.id),
    baseModelName(model.name),
    String(model.metadata['family'] ?? '').toLowerCase(),
  ].filter(Boolean));
  return library.find((candidate) => (
    candidate.provider === 'ollama'
    && (
      modelKeys.has(candidate.id.toLowerCase())
      || modelKeys.has(candidate.name.toLowerCase())
      || modelKeys.has(baseModelName(candidate.id))
      || modelKeys.has(baseModelName(candidate.name))
    )
  ));
};

export const modelDetails = (model: ModelCardDescriptor): string => {
  const details = String(model.metadata['details'] ?? '').trim();
  if (details) {
    return details;
  }
  return model.name;
};

export const modelDisplayDescription = (model: ModelCardDescriptor): string => {
  const description = model.description.trim();
  if (description && description.toLowerCase() !== 'local') {
    return description;
  }
  if (model.provider === 'ollama') {
    return `Installed Ollama model available for parser, chat, and agent duties. ${modelDetails(model)}`;
  }
  return description || 'Model available for assignment.';
};

export const enrichInstalledOllamaModel = (
  model: ModelCardDescriptor,
  library: ModelCardDescriptor[],
): ModelCardDescriptor => {
  if (model.provider !== 'ollama') {
    return model;
  }
  const libraryMatch = findOllamaLibraryMatch(model, library);
  if (!libraryMatch) {
    return model;
  }
  return {
    ...model,
    description: libraryMatch.description,
    metadata: { ...libraryMatch.metadata, ...model.metadata },
    capabilities: model.capabilities.length ? model.capabilities : libraryMatch.capabilities,
  };
};

export interface SelectedModelStat {
  model: string;
  provider: string;
  local: boolean;
  assignedRoles: ModelRole[];
}

export const buildSelectedModelStats = (
  settings: ModelSettingsResponse,
  localModelIds: ReadonlySet<string>,
): SelectedModelStat[] => {
  const rows: SelectedModelStat[] = [];
  const assignments: Array<{ role: ModelRole; provider: string; name: string }> = MODEL_ROLES.map((role) => {
    const fields = ROLE_FIELD_MAP[role];
    return {
      role,
      provider: normalizeSettingField(settings[fields.provider]),
      name: normalizeSettingField(settings[fields.name]),
    };
  });

  assignments.forEach(({ role, provider, name }) => {
    const hasSelection = Boolean(provider) && Boolean(name);
    const local = hasSelection && localModelIds.has(name);
    rows.push({
      model: hasSelection ? name : 'Not selected',
      provider: hasSelection ? provider : '-',
      local,
      assignedRoles: [role],
    });
  });

  return rows;
};
