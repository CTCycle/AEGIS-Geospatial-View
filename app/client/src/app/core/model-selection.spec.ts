import { buildSelectedModelStats, MODEL_ROLES } from './model-selection';
import { ModelSettingsResponse } from './types';

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
  credentials: {},
});

describe('model-selection', () => {
  it('keeps model role order stable', () => {
    expect(MODEL_ROLES).toEqual(['parser', 'chat', 'agent']);
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
});
