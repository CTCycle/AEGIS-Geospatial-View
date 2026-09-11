import { parseModelLibraryResponse } from './api-parsers';

describe('model library API parsing', () => {
  it('preserves the source stale flag without rejecting the response contract', () => {
    const parsed = parseModelLibraryResponse({
      cloud: [],
      local: [],
      sources: {
        'opencode-go': {
          ok: true,
          reachable: true,
          stale: false,
          message: null,
          model_count: 1,
        },
      },
    });

    expect(parsed.sources['opencode-go'].stale).toBeFalse();
  });

  it('defaults stale to false for older source payloads', () => {
    const parsed = parseModelLibraryResponse({
      cloud: [],
      local: [],
      sources: { ollama: { ok: true } },
    });

    expect(parsed.sources.ollama.stale).toBeFalse();
  });
});
