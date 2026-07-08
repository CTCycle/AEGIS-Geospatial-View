import { Injectable } from '@angular/core';

import { ApiClientService } from './api-client.service';
import { providerDisplayLabel } from './model-selection';
import { ModelSettingsResponse } from './types';
import { UserFacingErrorService } from './user-facing-error.service';

export type AgentReadinessStatus = 'checking' | 'active' | 'needs_attention' | 'unknown';

export interface AgentReadinessState {
  status: AgentReadinessStatus;
  label: string;
  message: string;
}

export const INITIAL_AGENT_READINESS_STATE: AgentReadinessState = {
  status: 'checking',
  label: 'Checking',
  message: 'Validating selected agent model status.',
};

@Injectable({ providedIn: 'root' })
export class AgentReadinessService {
  constructor(
    private readonly apiClient: ApiClientService,
    private readonly userFacingErrorService: UserFacingErrorService,
  ) {}

  async loadReadiness(): Promise<AgentReadinessState> {
    try {
      const settings = await this.apiClient.fetchChatSettings();
      const issue = await this.resolveIssue(settings);
      if (issue) {
        return {
          status: 'needs_attention',
          label: 'Needs attention',
          message: issue,
        };
      }
      return {
        status: 'active',
        label: 'Active',
        message: this.describeActiveAgent(settings),
      };
    } catch {
      return {
        status: 'unknown',
        label: 'Unknown',
        message: 'Could not verify selected agent readiness.',
      };
    }
  }

  private async resolveIssue(settings: ModelSettingsResponse): Promise<string | null> {
    const provider = settings.agent_model_provider.trim().toLowerCase();
    const model = settings.agent_model_name.trim();
    if (!provider || !model) {
      return 'No agent model is selected. Open Model Settings before using the workspace.';
    }

    if (provider === 'ollama') {
      return this.resolveOllamaIssue(settings, model);
    }

    const credentialHealth = settings.credential_health?.[provider]?.['api_key'];
    if (credentialHealth && credentialHealth !== 'healthy') {
      return `Selected ${providerDisplayLabel(provider)} credential needs attention (${credentialHealth}).`;
    }
    const configured = settings.credentials?.[provider]?.['api_key'];
    if (configured === false) {
      return `Selected ${providerDisplayLabel(provider)} model is missing its API key.`;
    }
    return null;
  }

  private async resolveOllamaIssue(settings: ModelSettingsResponse, model: string): Promise<string | null> {
    const [healthResult, modelsResult] = await Promise.allSettled([
      this.apiClient.checkOllamaHealth(),
      this.apiClient.fetchChatModels(),
    ]);
    const localModelIds = modelsResult.status === 'fulfilled'
      ? new Set(modelsResult.value.local.map((entry) => entry.id))
      : new Set<string>();
    if (modelsResult.status === 'fulfilled' && !localModelIds.has(model)) {
      return `Selected local model unavailable. ${model} is selected but not installed in Ollama.`;
    }
    if (healthResult.status === 'fulfilled' && healthResult.value.ok === false) {
      return this.userFacingErrorService.normalizeDisplayText(
        String(healthResult.value.detail ?? '').trim(),
        `Unable to reach Ollama at ${settings.ollama_url}.`,
      );
    }
    if (healthResult.status === 'rejected') {
      return `Unable to verify Ollama at ${settings.ollama_url}.`;
    }
    return null;
  }

  private describeActiveAgent(settings: ModelSettingsResponse): string {
    const provider = settings.agent_model_provider.trim();
    const model = settings.agent_model_name.trim();
    if (!provider || !model) {
      return 'No agent model selected.';
    }
    return `${model} is ready through ${providerDisplayLabel(provider)}.`;
  }
}
