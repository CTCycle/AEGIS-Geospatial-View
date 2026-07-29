import {
  ModelCardDescriptor,
  ModelProviderMode,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
} from './types';

const normalizeSettingField = (value: string | null | undefined): string =>
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

export interface SelectedAgentModelSummary {
  model: string;
  provider: string;
  runtimeMode: ModelProviderMode;
  installedLocally: boolean;
  supportsTools: boolean;
  supportsStructuredOutput: boolean;
  supportsVision: boolean;
  supportsEmbeddings: boolean;
  toolSupportSource: string;
  capabilities: string[];
}

export const providerDisplayLabel = (providerKey: string): string => {
  const normalized = providerKey.trim().toLowerCase();
  if (normalized === 'ollama-installed') {
    return 'ollama · installed';
  }
  if (normalized === 'ollama-library') {
    return 'ollama · available to pull';
  }
  if (normalized === 'ollama') {
    return 'Ollama';
  }
  if (normalized === 'openai') {
    return 'OpenAI';
  }
  if (normalized === 'google') {
    return 'Google';
  }
  if (normalized === 'deepseek') {
    return 'DeepSeek';
  }
  if (normalized === 'opencode') {
    return 'OpenCode Zen';
  }
  if (normalized === 'opencode-go') {
    return 'OpenCode Go';
  }
  return providerKey;
};

export const isSelectedAgentModel = (
  settings: ModelSettingsResponse,
  model: ModelCardDescriptor,
): boolean => {
  const selectedProvider = normalizeSettingField(settings.agent_model_provider);
  const selectedName = normalizeSettingField(settings.agent_model_name);
  return model.provider === selectedProvider && model.name === selectedName;
};

export const agentSelectionDisabledReason = (model: ModelCardDescriptor): string | null => {
  if (!model.supports_tools) {
    return 'Agent model requires native tool calling.';
  }
  if (!model.supports_structured_output) {
    return 'Agent model requires structured output.';
  }
  return null;
};

export const canSelectAgentModel = (model: ModelCardDescriptor): boolean =>
  agentSelectionDisabledReason(model) === null;

export const buildAgentModelSelectionPayload = (
  settings: ModelSettingsResponse,
  model: ModelCardDescriptor,
): ModelSettingsUpdateRequest => {
  const disabledReason = agentSelectionDisabledReason(model);
  if (disabledReason) {
    throw new Error(disabledReason);
  }
  const nextProviderMode: ModelProviderMode = model.provider === 'ollama' ? 'local' : 'cloud';
  return {
    active_provider_mode: nextProviderMode,
    agent_model_provider: model.provider,
    agent_model_name: model.name,
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
    return `Installed Ollama model available for agent duties, structured extraction, tool calling, and chat. ${modelDetails(model)}`;
  }
  return description || 'Model available for agent selection.';
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

export const buildSelectedAgentModelSummary = (
  settings: ModelSettingsResponse,
  localModelIds: ReadonlySet<string>,
  allModels: readonly ModelCardDescriptor[],
): SelectedAgentModelSummary | null => {
  const provider = normalizeSettingField(settings.agent_model_provider);
  const name = normalizeSettingField(settings.agent_model_name);
  if (!provider || !name) {
    return null;
  }
  const model = allModels.find((item) => item.provider === provider && item.name === name);
  return {
    model: name,
    provider,
    runtimeMode: provider === 'ollama' ? 'local' : 'cloud',
    installedLocally: provider === 'ollama' && localModelIds.has(name),
    supportsTools: Boolean(model?.supports_tools),
    supportsStructuredOutput: Boolean(model?.supports_structured_output),
    supportsVision: Boolean(model?.supports_vision),
    supportsEmbeddings: Boolean(model?.supports_embeddings),
    toolSupportSource: model?.tool_support_source || 'unknown',
    capabilities: model?.capabilities ?? [],
  };
};
