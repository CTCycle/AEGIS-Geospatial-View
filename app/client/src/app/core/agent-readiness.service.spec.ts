import { TestBed } from '@angular/core/testing';

import { AgentReadinessService } from './agent-readiness.service';
import { ApiClientService } from './api-client.service';
import { ModelCardDescriptor, ModelLibraryResponse, ModelSettingsResponse } from './types';
import { UserFacingErrorService } from './user-facing-error.service';

const settings = (overrides: Partial<ModelSettingsResponse> = {}): ModelSettingsResponse => ({
  active_provider_mode: 'cloud',
  agent_model_provider: 'openai',
  agent_model_name: 'gpt-4.1-mini',
  ollama_url: 'http://127.0.0.1:11434',
  openai_base_url: null,
  google_base_url: null,
  deepseek_base_url: null,
  credentials: { openai: { api_key: true } },
  credential_health: { openai: { api_key: 'healthy' } },
  selected_model_context: {
    provider: 'openai',
    model: 'gpt-4.1-mini',
    context_window_tokens: 1047576,
    maximum_output_tokens: 32768,
    context_profile_source: 'openai_model_catalog',
  },
  ...overrides,
});

const model = (
  provider: string,
  name: string,
  supportsTools: boolean | null,
): ModelCardDescriptor => ({
  id: name,
  name,
  description: '',
  provider,
  capabilities: ['chat'],
  supports_tools: supportsTools,
  supports_structured_output: null,
  supports_vision: null,
  supports_embeddings: null,
  tool_support_source: 'catalog',
  metadata: {},
});

const library = (
  cloud: ModelCardDescriptor[] = [],
  local: ModelCardDescriptor[] = [],
): ModelLibraryResponse => ({ cloud, local, sources: {} });

describe('AgentReadinessService', () => {
  let service: AgentReadinessService;
  let apiClient: jasmine.SpyObj<ApiClientService>;
  let errors: jasmine.SpyObj<UserFacingErrorService>;

  beforeEach(() => {
    apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', [
      'fetchChatSettings',
      'fetchChatModels',
      'checkOllamaHealth',
    ]);
    errors = jasmine.createSpyObj<UserFacingErrorService>('UserFacingErrorService', ['normalizeDisplayText']);
    errors.normalizeDisplayText.and.callFake((text: string, fallback: string) => text || fallback);

    TestBed.configureTestingModule({
      providers: [
        AgentReadinessService,
        { provide: ApiClientService, useValue: apiClient },
        { provide: UserFacingErrorService, useValue: errors },
      ],
    });
    service = TestBed.inject(AgentReadinessService);
  });

  it('uses catalog metadata without making a model inference call', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings());
    apiClient.fetchChatModels.and.resolveTo(library([model('openai', 'gpt-4.1-mini', true)]));

    const readiness = await service.loadReadiness();

    expect(readiness.status).toBe('active');
    expect(readiness.label).toBe('Configured');
    expect(readiness.message).toContain('Model metadata reports tool calling support');
    expect(readiness.message).toContain('normal workspace requests exercise live behavior');
    expect(apiClient.fetchChatModels).toHaveBeenCalledOnceWith(undefined);
  });

  it('flags models whose metadata says tool calling is unavailable', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings());
    apiClient.fetchChatModels.and.resolveTo(library([model('openai', 'gpt-4.1-mini', false)]));

    const readiness = await service.loadReadiness();

    expect(readiness.status).toBe('needs_attention');
    expect(readiness.message).toContain('tool calling is unavailable');
  });

  it('leaves unknown tool-support metadata unverified without a model-call fallback', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings());
    apiClient.fetchChatModels.and.resolveTo(library([model('openai', 'gpt-4.1-mini', null)]));

    const readiness = await service.loadReadiness();

    expect(readiness).toEqual({
      status: 'unknown',
      label: 'Not verified',
      message: 'The model catalog does not report whether this model supports tool calling.',
    });
  });

  it('requests the selected dynamic provider catalog by metadata only', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings({
      agent_model_provider: 'opencode-go',
      agent_model_name: 'beam-free',
      credentials: { 'opencode-go': { api_key: true } },
      credential_health: { 'opencode-go': { api_key: 'healthy' } },
    }));
    apiClient.fetchChatModels.and.resolveTo(library([model('opencode-go', 'beam-free', true)]));

    const readiness = await service.loadReadiness();

    expect(readiness.status).toBe('active');
    expect(apiClient.fetchChatModels).toHaveBeenCalledOnceWith('opencode-go');
  });

  it('reports cloud credential problems before requesting model metadata', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings({
      credential_health: { openai: { api_key: 'unreadable' } },
    }));

    const readiness = await service.loadReadiness();

    expect(readiness.status).toBe('needs_attention');
    expect(readiness.message).toBe('Selected OpenAI credential needs attention (unreadable).');
    expect(apiClient.fetchChatModels).not.toHaveBeenCalled();
  });

  it('reports unavailable local Ollama models', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings({
      active_provider_mode: 'local',
      agent_model_provider: 'ollama',
      agent_model_name: 'llama3.2',
      credentials: {},
      credential_health: {},
    }));
    apiClient.checkOllamaHealth.and.resolveTo({ ok: true, detail: 'ok' });
    apiClient.fetchChatModels.and.resolveTo(library([], []));

    const readiness = await service.loadReadiness();

    expect(readiness.status).toBe('needs_attention');
    expect(readiness.message).toBe('Selected local model unavailable. llama3.2 is selected but not installed in Ollama.');
  });

  it('reports unknown readiness when model metadata cannot be loaded', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings());
    apiClient.fetchChatModels.and.rejectWith(new Error('catalog unavailable'));

    const readiness = await service.loadReadiness();

    expect(readiness.status).toBe('unknown');
    expect(readiness.label).toBe('Not verified');
    expect(readiness.message).toBe('Could not load selected model capability metadata. Tool calling is not verified.');
  });

  it('reports unknown readiness when settings cannot be loaded', async () => {
    apiClient.fetchChatSettings.and.rejectWith(new Error('boom'));

    const readiness = await service.loadReadiness();

    expect(readiness).toEqual({
      status: 'unknown',
      label: 'Not verified',
      message: 'Could not verify selected agent readiness from model metadata.',
    });
  });

  it('rejects a noncanonical provider instead of normalizing it', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings({
      agent_model_provider: 'OpenAI',
    }));

    const readiness = await service.loadReadiness();

    expect(readiness.status).toBe('needs_attention');
    expect(readiness.message).toBe(
      'Selected provider ID is not supported: OpenAI. Choose a canonical provider in Settings.',
    );
    expect(apiClient.fetchChatModels).not.toHaveBeenCalled();
  });
});
