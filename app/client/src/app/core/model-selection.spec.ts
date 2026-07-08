import {
  agentSelectionDisabledReason,
  buildAgentModelSelectionPayload,
  buildSelectedAgentModelSummary,
  canSelectAgentModel,
  enrichInstalledOllamaModel,
  mergeModelCard,
  mergeModelCards,
  providerDisplayLabel,
} from './model-selection';
import { ModelCardDescriptor, ModelSettingsResponse } from './types';

const baseSettings = (): ModelSettingsResponse => ({
  active_provider_mode: 'cloud',
  agent_model_provider: 'google',
  agent_model_name: 'gemini-2.5-flash',
  ollama_url: 'http://127.0.0.1:11434',
  openai_base_url: null,
  google_base_url: null,
  deepseek_base_url: null,
  credentials: {},
});

const model = (overrides: Partial<ModelCardDescriptor> = {}): ModelCardDescriptor => ({
  id: 'm',
  name: 'm',
  description: 'model',
  provider: 'openai',
  capabilities: ['chat'],
  supports_tools: true,
  supports_structured_output: true,
  supports_vision: false,
  supports_embeddings: false,
  tool_support_source: 'unknown',
  metadata: {},
  ...overrides,
});

describe('model-selection', () => {
  it('merges model card groups by provider and id', () => {
    const merged = mergeModelCards(
      [model({ id: 'same', provider: 'openai', description: 'short', capabilities: [] })],
      [model({ id: 'same', provider: 'openai', description: 'much richer description', capabilities: ['tools'] })],
    );
    expect(merged.length).toBe(1);
    expect(merged[0].description).toBe('much richer description');
    expect(merged[0].capabilities).toEqual(['tools']);
  });

  it('prefers the richer model description when merging a card', () => {
    const merged = mergeModelCard(
      model({ description: 'brief', metadata: { family: 'qwen2' } }),
      model({ description: 'A provider-authored model summary.', metadata: { details: '7B' } }),
    );
    const metadata = merged.metadata as Record<string, unknown>;
    expect(merged.description).toBe('A provider-authored model summary.');
    expect(metadata['family']).toBe('qwen2');
    expect(metadata['details']).toBe('7B');
  });

  it('enriches installed ollama models from matching library entries', () => {
    const installed = model({
      id: 'qwen2.5:7b',
      name: 'qwen2.5:7b',
      provider: 'ollama',
      description: 'local',
      capabilities: [],
      metadata: { family: 'qwen2.5' },
    });
    const library = [
      model({
        id: 'qwen2.5',
        name: 'qwen2.5:7b-instruct',
        provider: 'ollama',
        description: 'Optimized for qwen2.5 7B.',
        capabilities: ['tools'],
        metadata: { details: '7B instruct' },
      }),
    ];

    const enriched = enrichInstalledOllamaModel(installed, library);
    const metadata = enriched.metadata as Record<string, unknown>;
    expect(enriched.description).toBe('Optimized for qwen2.5 7B.');
    expect(enriched.capabilities).toEqual(['tools']);
    expect(metadata['details']).toBe('7B instruct');
    expect(metadata['family']).toBe('qwen2.5');
  });

  it('blocks selected agent models without tools or structured output', () => {
    expect(canSelectAgentModel(model({ supports_tools: false }))).toBeFalse();
    expect(agentSelectionDisabledReason(model({ supports_tools: false }))).toBe('Agent model requires native tool calling.');
    expect(canSelectAgentModel(model({ supports_structured_output: false }))).toBeFalse();
    expect(agentSelectionDisabledReason(model({ supports_structured_output: false }))).toBe('Agent model requires structured output.');
  });

  it('builds a single selected-agent payload', () => {
    const payload = buildAgentModelSelectionPayload(
      baseSettings(),
      model({ provider: 'deepseek', name: 'deepseek-chat' }),
    );

    expect(payload).toEqual({
      active_provider_mode: 'cloud',
      agent_model_provider: 'deepseek',
      agent_model_name: 'deepseek-chat',
      credentials: {},
    });
    expect(payload.ollama_url).toBeUndefined();
  });

  it('builds a selected-agent summary with capabilities and local status', () => {
    const settings = baseSettings();
    settings.agent_model_provider = 'ollama';
    settings.agent_model_name = 'llama3.2';

    const summary = buildSelectedAgentModelSummary(
      settings,
      new Set<string>(['llama3.2']),
      [model({ provider: 'ollama', name: 'llama3.2', capabilities: ['tools', 'json'], tool_support_source: 'ollama_probe' })],
    );

    expect(summary).toEqual(jasmine.objectContaining({
      model: 'llama3.2',
      provider: 'ollama',
      runtimeMode: 'local',
      installedLocally: true,
      supportsTools: true,
      supportsStructuredOutput: true,
      toolSupportSource: 'ollama_probe',
    }));
    expect(summary?.capabilities).toEqual(['tools', 'json']);
  });

  it('formats provider and provider-group labels consistently', () => {
    expect(providerDisplayLabel('ollama')).toBe('Ollama');
    expect(providerDisplayLabel('ollama-installed')).toBe('ollama · installed');
    expect(providerDisplayLabel('openai')).toBe('OpenAI');
    expect(providerDisplayLabel('custom-provider')).toBe('custom-provider');
  });
});
