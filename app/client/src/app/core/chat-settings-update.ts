import { ModelSettingsResponse, ModelSettingsUpdateRequest } from './types';

export type CloudCredentialProvider = 'openai' | 'google' | 'deepseek' | 'opencode' | 'opencode-go';
export type ModelProviderFilter = 'all' | 'ollama' | CloudCredentialProvider;
export type ApiKeyValidationErrors = Partial<Record<CloudCredentialProvider, string>>;
export type CloudCredentialDrafts = Record<CloudCredentialProvider, string>;

export const CLOUD_CREDENTIAL_PROVIDERS: readonly CloudCredentialProvider[] = [
  'openai',
  'google',
  'deepseek',
  'opencode',
  'opencode-go',
];

export const buildSettingsUpdateBase = (
  settings: ModelSettingsResponse,
): ModelSettingsUpdateRequest => ({
  active_provider_mode: settings.active_provider_mode,
  agent_model_provider: settings.agent_model_provider,
  agent_model_name: settings.agent_model_name,
  ollama_url: settings.ollama_url,
  openai_base_url: settings.openai_base_url,
  google_base_url: settings.google_base_url,
  deepseek_base_url: settings.deepseek_base_url,
  credentials: {},
});

export const buildCredentialUpdateRequest = (
  _settings: ModelSettingsResponse,
  provider: string,
  apiKey: string,
): ModelSettingsUpdateRequest => ({
  credentials: {
    [provider]: { api_key: apiKey },
  },
});

export const buildCloudCredentialUpdateRequest = (
  _settings: ModelSettingsResponse,
  drafts: CloudCredentialDrafts,
): ModelSettingsUpdateRequest => ({
  credentials: CLOUD_CREDENTIAL_PROVIDERS.reduce<ModelSettingsUpdateRequest['credentials']>((acc, provider) => {
    const apiKey = drafts[provider].trim();
    acc[provider] = apiKey ? { api_key: apiKey } : {};
    return acc;
  }, {}),
});
