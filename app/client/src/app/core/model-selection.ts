import {
  ModelCardDescriptor,
  ModelProviderMode,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
} from './types';

export type ModelRole = 'parser' | 'chat' | 'agent';

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

export const buildModelSelectionPayload = (
  settings: ModelSettingsResponse,
  role: ModelRole,
  model: ModelCardDescriptor,
): ModelSettingsUpdateRequest => {
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
    [roleFields.provider]: model.provider,
    [roleFields.name]: model.name,
    credentials: toSelectionUpdateCredentials(settings.credentials),
  };
};

export interface SelectedModelStat {
  model: string;
  provider: string;
  local: boolean;
  assignedRoles: string[];
}

export const buildSelectedModelStats = (
  settings: ModelSettingsResponse,
  localModelIds: ReadonlySet<string>,
): SelectedModelStat[] => {
  const rows: SelectedModelStat[] = [];
  const assignments: Array<{ role: string; provider: string; name: string }> = [
    { role: 'Parser', provider: settings.parser_model_provider, name: settings.parser_model_name },
    { role: 'Chat', provider: settings.chat_model_provider, name: settings.chat_model_name },
    { role: 'Agent', provider: settings.agent_model_provider, name: settings.agent_model_name },
  ];

  assignments.forEach(({ role, provider, name }) => {
    const normalizedProvider = provider.trim();
    const normalizedName = name.trim();
    const hasSelection = Boolean(normalizedProvider) && Boolean(normalizedName);
    const local = hasSelection && localModelIds.has(normalizedName);
    rows.push({
      model: hasSelection ? normalizedName : 'Not selected',
      provider: hasSelection ? normalizedProvider : '-',
      local,
      assignedRoles: [role],
    });
  });

  return rows;
};
