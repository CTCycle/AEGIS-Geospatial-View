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
    ...settings,
    active_provider_mode: nextProviderMode,
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
  const rows = new Map<string, SelectedModelStat>();
  const assignments: Array<{ role: string; provider: string; name: string }> = [
    { role: 'Parser', provider: settings.parser_model_provider, name: settings.parser_model_name },
    { role: 'Chat', provider: settings.chat_model_provider, name: settings.chat_model_name },
    { role: 'Agent', provider: settings.agent_model_provider, name: settings.agent_model_name },
  ];

  assignments.forEach(({ role, provider, name }) => {
    const normalizedProvider = provider.trim();
    const normalizedName = name.trim();
    if (!normalizedProvider || !normalizedName) {
      return;
    }
    const key = `${normalizedProvider}:${normalizedName}`;
    const existing = rows.get(key);
    const local = localModelIds.has(normalizedName);
    if (existing) {
      existing.local = existing.local || local;
      if (!existing.assignedRoles.includes(role)) {
        existing.assignedRoles.push(role);
      }
      return;
    }
    rows.set(key, {
      model: normalizedName,
      provider: normalizedProvider,
      local,
      assignedRoles: [role],
    });
  });

  return Array.from(rows.values());
};
