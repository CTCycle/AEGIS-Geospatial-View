import { ModelSettingsResponse, ModelSettingsUpdateRequest } from './types';

export type CloudCredentialProvider = 'openai' | 'google' | 'deepseek';
export type ModelProviderFilter = 'all' | 'ollama' | CloudCredentialProvider;
export type ApiKeyValidationErrors = Partial<Record<CloudCredentialProvider, string>>;
export type CloudCredentialDrafts = Record<CloudCredentialProvider, string>;

export const CLOUD_CREDENTIAL_PROVIDERS: readonly CloudCredentialProvider[] = ['openai', 'google', 'deepseek'];

export const buildSettingsUpdateBase = (
  settings: ModelSettingsResponse,
): ModelSettingsUpdateRequest => ({
  active_provider_mode: settings.active_provider_mode,
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
  credentials: {},
});

export const buildCredentialUpdateRequest = (
  settings: ModelSettingsResponse,
  provider: string,
  apiKey: string,
): ModelSettingsUpdateRequest => ({
  ...buildSettingsUpdateBase(settings),
  credentials: {
    [provider]: { api_key: apiKey },
  },
});

export const buildCloudCredentialUpdateRequest = (
  settings: ModelSettingsResponse,
  drafts: CloudCredentialDrafts,
): ModelSettingsUpdateRequest => ({
  ...buildSettingsUpdateBase(settings),
  credentials: CLOUD_CREDENTIAL_PROVIDERS.reduce<ModelSettingsUpdateRequest['credentials']>((acc, provider) => {
    const apiKey = drafts[provider].trim();
    acc[provider] = apiKey ? { api_key: apiKey } : {};
    return acc;
  }, {}),
});
