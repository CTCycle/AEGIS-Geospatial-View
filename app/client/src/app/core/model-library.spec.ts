import { isDynamicCloudProvider, mergeModelLibraries } from './model-library';
import type { ModelCardDescriptor, ModelLibraryResponse } from './types';

const model = (overrides: Partial<ModelCardDescriptor> = {}): ModelCardDescriptor => ({
  id: 'model-1',
  name: 'Model 1',
  description: 'Model description',
  provider: 'openai',
  capabilities: ['chat'],
  supports_tools: true,
  supports_structured_output: true,
  supports_vision: false,
  supports_embeddings: false,
  tool_support_source: 'catalog',
  metadata: {},
  ...overrides,
});

const library = (overrides: Partial<ModelLibraryResponse> = {}): ModelLibraryResponse => ({
  cloud: [],
  local: [],
  sources: {},
  ...overrides,
});

describe('model-library', () => {
  it('narrows only dynamically loaded cloud providers', () => {
    expect(isDynamicCloudProvider('deepseek')).toBeTrue();
    expect(isDynamicCloudProvider('openai')).toBeFalse();
  });

  it('replaces one dynamic provider while retaining the base catalog and source status', () => {
    const merged = mergeModelLibraries(
      library({
        cloud: [
          model({ id: 'openai-1', provider: 'openai' }),
          model({ id: 'old-deepseek', provider: 'deepseek' }),
        ],
        local: [model({ id: 'local-1', provider: 'ollama' })],
        sources: { openai: { ok: true }, deepseek: { ok: false, message: 'stale' } },
      }),
      library({
        cloud: [model({ id: 'new-deepseek', provider: 'deepseek' })],
        local: [],
        sources: { deepseek: { ok: true } },
      }),
      'deepseek',
    );

    expect(merged.cloud.map((entry) => entry.id)).toEqual(['openai-1', 'new-deepseek']);
    expect(merged.local.map((entry) => entry.id)).toEqual(['local-1']);
    expect(merged.sources).toEqual({ openai: { ok: true }, deepseek: { ok: true } });
  });
});
