import {
  buildModelSelectionPayload,
  buildSelectedModelStats,
  canAssignRole,
  enrichInstalledOllamaModel,
  mergeModelCard,
  mergeModelCards,
  MODEL_ROLES,
  modelRoleLabel,
  modelRoleStatusLabel,
  roleDisabledReason,
} from './model-selection';
import { ModelCardDescriptor, ModelSettingsResponse } from './types';

const baseSettings = (): ModelSettingsResponse => ({
  active_provider_mode: 'cloud',
  chat_model_provider: 'openai',
  chat_model_name: 'gpt-4.1',
  parser_model_provider: 'openai',
  parser_model_name: 'gpt-4.1-mini',
  agent_model_provider: 'google',
  agent_model_name: 'gemini-2.0-flash',
  ollama_url: 'http://localhost:11434',
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
  supports_tools: false,
  supports_structured_output: false,
  supports_vision: false,
  supports_embeddings: false,
  tool_support_source: 'unknown',
  metadata: {},
  ...overrides,
});

describe('model-selection', () => {
  it('keeps model role order stable', () => {
    expect(MODEL_ROLES).toEqual(['parser', 'chat', 'agent']);
  });

  it('returns stable role labels', () => {
    expect(modelRoleLabel('parser')).toBe('Parser');
    expect(modelRoleStatusLabel('parser')).toBe('parser');
  });

  it('returns assigned roles as model role values', () => {
    const rows = buildSelectedModelStats(baseSettings(), new Set<string>(['gpt-4.1-mini']));
    expect(rows[0].assignedRoles).toEqual(['parser']);
    expect(rows[1].assignedRoles).toEqual(['chat']);
    expect(rows[2].assignedRoles).toEqual(['agent']);
  });

  it('keeps multiple selected roles grouped under the same model rows', () => {
    const settings = baseSettings();
    settings.chat_model_provider = 'openai';
    settings.chat_model_name = 'shared-model';
    settings.parser_model_provider = 'openai';
    settings.parser_model_name = 'shared-model';

    const rows = buildSelectedModelStats(settings, new Set<string>(['shared-model']));
    expect(rows[0]).toEqual(jasmine.objectContaining({ model: 'shared-model', assignedRoles: ['parser'] }));
    expect(rows[1]).toEqual(jasmine.objectContaining({ model: 'shared-model', assignedRoles: ['chat'] }));
  });

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

  it('blocks agent assignment without tools', () => {
    expect(canAssignRole(model({ supports_tools: false }), 'agent')).toBeFalse();
    expect(roleDisabledReason(model({ supports_tools: false }), 'agent')).toBe('Agent role requires native tool calling.');
  });

  it('blocks parser assignment without structured output', () => {
    expect(canAssignRole(model({ supports_structured_output: false }), 'parser')).toBeFalse();
    expect(roleDisabledReason(model({ supports_structured_output: false }), 'parser')).toBe(
      'Parser role requires structured output.',
    );
  });

  it('allows chat assignment for normal chat models', () => {
    expect(canAssignRole(model(), 'chat')).toBeTrue();
  });

  it('rejects invalid role assignments when building payloads', () => {
    expect(() => buildModelSelectionPayload(baseSettings(), 'agent', model({ supports_tools: false }))).toThrowError(
      'Agent role requires native tool calling.',
    );
  });
});
