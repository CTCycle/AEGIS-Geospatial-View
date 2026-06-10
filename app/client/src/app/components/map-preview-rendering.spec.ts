import { DEFAULT_BASE_TILE_PROXY_URL } from '../core/constants';
import { buildStyle, normalizeBounds, recordBooleanEqual, recordNumberEqual } from './map-preview-rendering';

describe('map-preview-rendering', () => {
  it('compares boolean records by keys and values', () => {
    expect(recordBooleanEqual({ a: true }, { a: true })).toBeTrue();
    expect(recordBooleanEqual({ a: true }, { a: false })).toBeFalse();
    expect(recordBooleanEqual({ a: true }, { a: true, b: false })).toBeFalse();
  });

  it('compares number records by keys and values', () => {
    expect(recordNumberEqual({ a: 0.5 }, { a: 0.5 })).toBeTrue();
    expect(recordNumberEqual({ a: 0.5 }, { a: 0.6 })).toBeFalse();
    expect(recordNumberEqual({ a: 0.5 }, { a: 0.5, b: 1 })).toBeFalse();
  });

  it('returns null for malformed bounds', () => {
    expect(normalizeBounds([12.4, Number.NaN, 13.1, 42.1])).toBeNull();
    expect(normalizeBounds([12.4, 41.9, 13.1] as unknown)).toBeNull();
  });

  it('returns maplibre bounds for finite tuples', () => {
    expect(normalizeBounds([12.4, 41.9, 13.1, 42.1])).toEqual([[12.4, 41.9], [13.1, 42.1]]);
  });

  it('uses the proxied default OSM basemap tile URL', () => {
    const style = buildStyle();
    const basemapSource = style.sources['basemap'] as { tiles?: string[] };
    expect(basemapSource.tiles?.[0]).toBe(DEFAULT_BASE_TILE_PROXY_URL);
  });
});
