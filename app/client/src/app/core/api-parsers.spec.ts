import { normalizeMapOverlayEntry, parseModelLibraryResponse } from './api-parsers';

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
