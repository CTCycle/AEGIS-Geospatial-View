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

describe('overlay legend parsing', () => {
  const base = {id: 'dem', type: 'raster'};
  const legend = {
    kind: 'continuous',
    title: 'Elevation',
    units: 'm',
    entries: [{color: '#0044ca', value: -100, label: '-100'}, {color: '#ff0000', value: 3000, label: '3000'}],
    nodata_colors: ['#000000'],
  };

  it('keeps a valid legend and ignores malformed ones', () => {
    expect(normalizeMapOverlayEntry({...base, legend})?.legend).toEqual(legend as never);
    for (const bad of [
      {...legend, kind: 'gradient'},
      {...legend, entries: []},
      {...legend, entries: [{color: 'red', value: 1, label: 'x'}]},
      {...legend, entries: [{color: '#0044ca', label: 'no value'}]},
      'legend',
    ]) {
      expect(normalizeMapOverlayEntry({...base, legend: bad})?.legend).toBeUndefined();
    }
  });

  it('allows categorical entries without values', () => {
    const categorical = {...legend, kind: 'categorical', units: undefined, entries: [{color: '#006400', label: 'Tree cover'}]};
    expect(normalizeMapOverlayEntry({...base, legend: categorical})?.legend).toEqual({
      ...categorical,
      units: null,
    } as never);
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
