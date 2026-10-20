import { Injectable } from '@angular/core';

import { ApiClientService } from './api-client.service';
import { isDynamicCloudProvider } from './model-library';
import { providerDisplayLabel } from './model-selection';
import { ModelCardDescriptor, ModelLibraryResponse, ModelSettingsResponse } from './types';
import { UserFacingErrorService } from './user-facing-error.service';

export type AgentReadinessStatus = 'checking' | 'active' | 'needs_attention' | 'unknown';

export interface AgentReadinessState {
  status: AgentReadinessStatus;
  label: string;
  message: string;
  /** Catalog-reported image input support; absent or null when unknown. */
  supportsVision?: boolean | null;
}

export const INITIAL_AGENT_READINESS_STATE: AgentReadinessState = {
  status: 'checking',
  label: 'Checking',
  message: 'Reading selected model capability metadata.',
};

const CANONICAL_LLM_PROVIDERS = new Set([
  'openai',
  'google',
  'deepseek',
  'opencode',
  'opencode-go',
  'ollama',
]);

@Injectable({ providedIn: 'root' })
export class AgentReadinessService {
  constructor(
    private readonly apiClient: ApiClientService,
    private readonly userFacingErrorService: UserFacingErrorService,
  ) {}

  async loadReadiness(): Promise<AgentReadinessState> {
    try {
      const settings = await this.apiClient.fetchChatSettings();
      const provider = settings.agent_model_provider;
      const model = settings.agent_model_name.trim();
      if (!provider || !model) {
        return this.needsAttention('No agent model is selected. Open Settings before using the workspace.');
      }
      if (!CANONICAL_LLM_PROVIDERS.has(provider)) {
        return this.needsAttention(
          `Selected provider ID is not supported: ${provider}. Choose a canonical provider in Settings.`,
        );
      }
      if (provider === 'ollama') {
        return await this.resolveOllamaReadiness(settings, model);
      }

      const credentialIssue = this.resolveCloudCredentialIssue(settings, provider);
      if (credentialIssue) {
        return this.needsAttention(credentialIssue);
      }

      const dynamicProvider = isDynamicCloudProvider(provider) ? provider : undefined;
      let library: ModelLibraryResponse;
      try {
        library = await this.apiClient.fetchChatModels(dynamicProvider);
      } catch {
        return this.notVerified('Could not load selected model capability metadata. Tool calling is not verified.');
      }
      const descriptor = library.cloud.find((entry) => entry.provider === provider && entry.id === model);
      return this.describeToolSupport(settings, descriptor);
    } catch {
      return this.notVerified('Could not verify selected agent readiness from model metadata.');
    }
  }

  private resolveCloudCredentialIssue(settings: ModelSettingsResponse, provider: string): string | null {
    const credentialHealth = settings.credential_health?.[provider]?.['api_key'];
    if (credentialHealth && credentialHealth !== 'healthy') {
      return `Selected ${providerDisplayLabel(provider)} credential needs attention (${credentialHealth}).`;
    }
    if (settings.credentials?.[provider]?.['api_key'] === false) {
      return `Selected ${providerDisplayLabel(provider)} model is missing its API key.`;
    }
    return null;
  }

  private async resolveOllamaReadiness(
    settings: ModelSettingsResponse,
    model: string,
  ): Promise<AgentReadinessState> {
    const [healthResult, modelsResult] = await Promise.allSettled([
      this.apiClient.checkOllamaHealth(),
      this.apiClient.fetchChatModels(),
    ]);
    const descriptor = modelsResult.status === 'fulfilled'
      ? modelsResult.value.local.find((entry) => entry.id === model)
      : undefined;
    if (modelsResult.status === 'fulfilled' && !descriptor) {
      return this.needsAttention(`Selected local model unavailable. ${model} is selected but not installed in Ollama.`);
    }
    if (healthResult.status === 'fulfilled' && healthResult.value.ok === false) {
      return this.needsAttention(this.userFacingErrorService.normalizeDisplayText(
        String(healthResult.value.detail ?? '').trim(),
        `Unable to reach Ollama at ${settings.ollama_url}.`,
      ));
    }
    if (healthResult.status === 'rejected') {
      return this.needsAttention(`Unable to verify Ollama at ${settings.ollama_url}.`);
    }
    if (!descriptor) {
      return this.notVerified('Could not load selected model capability metadata. Tool calling is not verified.');
    }
    return this.describeToolSupport(settings, descriptor);
  }

  private describeToolSupport(
    settings: ModelSettingsResponse,
    descriptor: ModelCardDescriptor | undefined,
  ): AgentReadinessState {
    if (!descriptor || descriptor.supports_tools == null) {
      return this.notVerified('The model catalog does not report whether this model supports tool calling.');
    }
    if (descriptor.supports_tools === false) {
      return this.needsAttention('Model metadata reports that tool calling is unavailable for the selected model. Choose a model with tool support in Settings.');
    }
    return {
      status: 'active',
      label: 'Configured',
      message: `${this.describeActiveAgent(settings)} Model metadata reports tool calling support; normal workspace requests exercise live behavior.`,
      supportsVision: descriptor.supports_vision ?? null,
    };
  }

  private describeActiveAgent(settings: ModelSettingsResponse): string {
    const provider = settings.agent_model_provider;
    const model = settings.agent_model_name.trim();
    return `${model} is configured through ${providerDisplayLabel(provider)}.`;
  }

  private needsAttention(message: string): AgentReadinessState {
    return { status: 'needs_attention', label: 'Needs attention', message };
  }

  private notVerified(message: string): AgentReadinessState {
    return { status: 'unknown', label: 'Not verified', message };
  }
}
