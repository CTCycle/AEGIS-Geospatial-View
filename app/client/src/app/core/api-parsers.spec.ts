import { normalizeMapOverlayEntry, parseChatOperation, parseModelLibraryResponse } from './api-parsers';

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

describe('value encoding parsing', () => {
  it('preserves valid encodings and drops invalid encodings', () => {
    const base = {id: 'grid', type: 'geojson'};
    const valid = {mode: 'graduated', field: 'rain', min: 0, max: 20};
    expect(normalizeMapOverlayEntry({...base, value_encoding: valid})?.value_encoding).toEqual(valid as never);
    for (const encoding of [{...valid, max: -1}, {...valid, min: NaN}, {...valid, field: ''}, {...valid, mode: 'random'}]) {
      expect(normalizeMapOverlayEntry({...base, value_encoding: encoding})?.value_encoding).toBeUndefined();
    }
  });
});

describe('chat operation parsing', () => {
  it('accepts the internal and render-recovery failure categories', () => {
    for (const category of ['internal_error', 'render_recovery_exhausted']) {
      const parsed = parseChatOperation(
        { kind: 'error', status: 'failed', message: 'Stopped.', failure_category: category },
        '/api/chat',
      );
      expect(parsed.failure_category).toBe(category as typeof parsed.failure_category);
    }
  });
});
