import { TestBed } from '@angular/core/testing';

import { AgentReadinessService } from './agent-readiness.service';
import { ApiClientService } from './api-client.service';
import { ModelSettingsResponse } from './types';
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

  it('reports configured readiness without claiming live inference', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings());

    const readiness = await service.loadReadiness();

    expect(readiness).toEqual({
      status: 'active',
      label: 'Configured',
      message: 'gpt-4.1-mini is configured through OpenAI. Live inference is verified on the first request.',
    });
  });

  it('reports cloud credential problems with a typed readiness status', async () => {
    apiClient.fetchChatSettings.and.resolveTo(settings({
      credential_health: { openai: { api_key: 'unreadable' } },
    }));

    const readiness = await service.loadReadiness();

    expect(readiness.status).toBe('needs_attention');
    expect(readiness.label).toBe('Needs attention');
    expect(readiness.message).toBe('Selected OpenAI credential needs attention (unreadable).');
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
    apiClient.fetchChatModels.and.resolveTo({ cloud: [], local: [], sources: {} });

    const readiness = await service.loadReadiness();

    expect(readiness.status).toBe('needs_attention');
    expect(readiness.message).toBe('Selected local model unavailable. llama3.2 is selected but not installed in Ollama.');
  });

  it('reports unknown readiness when settings cannot be loaded', async () => {
    apiClient.fetchChatSettings.and.rejectWith(new Error('boom'));

    const readiness = await service.loadReadiness();

    expect(readiness).toEqual({
      status: 'unknown',
      label: 'Unknown',
      message: 'Could not verify selected agent readiness.',
    });
  });
});
