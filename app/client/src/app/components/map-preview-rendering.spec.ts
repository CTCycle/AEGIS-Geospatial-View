import { DEFAULT_BASE_TILE_PROXY_URL } from '../core/constants';
import { MapOverlayEntry, MapSession } from '../core/types';
import {
  addOverlayLayers,
  buildStyle,
  isGeoJsonOverlay,
  normalizeBounds,
  recordBooleanEqual,
  recordNumberEqual,
} from './map-preview-rendering';

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

  it('does not silently substitute OSM when a non-OSM descriptor is unavailable', () => {
    const style = buildStyle({
      basemap_id: 'esri_world_imagery',
      basemap: {
        id: 'esri_world_imagery',
        label: 'Satellite Imagery',
        provider: 'arcgis',
        render_status: 'unavailable',
        unavailable_reason: 'render_descriptor_missing',
      },
    } as never);
    const basemapSource = style.sources['basemap'] as { tiles?: string[] };
    expect(basemapSource.tiles).toEqual([]);
  });

  it('treats GeoJSON rendering modes as GeoJSON when descriptor metadata is sparse', () => {
    const baseOverlay = {
      id: 'mode-only',
      label: 'Mode only',
      provider: 'fixture',
      type: 'feature-layer',
      url: '/features.geojson',
    } as MapOverlayEntry;

    for (const rendering_mode of ['geojson', 'arcgis-geojson', 'clustered-points', 'choropleth', 'camera-points']) {
      expect(isGeoJsonOverlay({ ...baseOverlay, rendering_mode })).toBeTrue();
    }
    expect(isGeoJsonOverlay({ ...baseOverlay, rendering_mode: 'camera-points', url: null })).toBeFalse();
  });

  const renderCases: Array<{
    mode: string;
    overlay: Partial<MapOverlayEntry>;
    sourceType?: string;
    layerType?: string;
    status?: 'loaded' | 'metadata-only';
  }> = [
    {
      mode: 'xyz',
      overlay: { type: 'tile', url: 'https://example.test/{z}/{x}/{y}.png' },
      sourceType: 'raster',
      layerType: 'raster',
    },
    {
      mode: 'raster-tile',
      overlay: { type: 'raster-tile', url: 'https://example.test/{z}/{x}/{y}.png' },
      sourceType: 'raster',
      layerType: 'raster',
    },
    {
      mode: 'wms',
      overlay: { type: 'wms', url: 'https://example.test/wms', layers: 'test' },
      sourceType: 'raster',
      layerType: 'raster',
    },
    {
      mode: 'wmts',
      overlay: {
        type: 'wmts',
        url: 'https://example.test/wmts',
        layer_id: 'test',
        tile_matrix_set: 'EPSG:3857',
      },
      sourceType: 'raster',
      layerType: 'raster',
    },
    {
      mode: 'geojson',
      overlay: { type: 'geojson', url: '/test.geojson', data_format: 'GeoJSON' },
      sourceType: 'geojson',
      layerType: 'line',
    },
    {
      mode: 'clustered-points',
      overlay: {
        type: 'geojson',
        url: '/test.geojson',
        data_format: 'GeoJSON',
        geometry_type: 'Point',
      },
      sourceType: 'geojson',
      layerType: 'circle',
    },
    {
      mode: 'choropleth',
      overlay: {
        type: 'geojson',
        url: '/test.geojson',
        data_format: 'GeoJSON',
        geometry_type: 'Polygon',
      },
      sourceType: 'geojson',
      layerType: 'fill',
    },
    {
      mode: 'camera-points',
      overlay: {
        type: 'geojson',
        url: '/cameras.geojson',
        data_format: 'GeoJSON',
        geometry_type: 'Point',
      },
      sourceType: 'geojson',
      layerType: 'circle',
    },
    {
      mode: 'vector-tile',
      overlay: {
        type: 'vector-tile',
        tile_url_template: 'https://example.test/{z}/{x}/{y}.pbf',
        source_layer: 'test',
      },
      sourceType: 'vector',
      layerType: 'fill',
    },
    {
      mode: 'metadata-only',
      overlay: { type: 'metadata-only' },
      status: 'metadata-only',
    },
  ];

  renderCases.forEach(({ mode, overlay, sourceType, layerType, status = 'loaded' }) => {
    it(`renders ${mode} descriptors`, () => {
      const sources: unknown[] = [];
      const layers: unknown[] = [];
      const map = {
        addSource: (_id: string, source: unknown) => sources.push(source),
        addLayer: (layer: unknown) => layers.push(layer),
      };
      const session = {
        overlays: [{
          id: `test-${mode}`,
          label: mode,
          provider: 'test',
          rendering_mode: mode,
          ...overlay,
        }],
      } as unknown as MapSession;

      const result = addOverlayLayers(map as never, session);

      expect(result).toEqual([jasmine.objectContaining({ status })]);
      if (status === 'metadata-only') {
        expect(sources).toEqual([]);
        expect(layers).toEqual([]);
      } else {
        expect(sources[0]).toEqual(jasmine.objectContaining({ type: sourceType }));
        expect(layers[0]).toEqual(jasmine.objectContaining({ type: layerType }));
      }
    });
  });

  it('uses canonical render zoom fields and WMS tile templates', () => {
    const sources: Array<Record<string, unknown>> = [];
    const map = {
      addSource: (_id: string, source: Record<string, unknown>) => sources.push(source),
      addLayer: () => undefined,
    };
    const session = {
      overlays: [{
        id: 'canonical-wms',
        label: 'WMS',
        provider: 'test',
        type: 'wms',
        rendering_mode: 'wms',
        render: {
          provider: 'test',
          layer_id: 'layer',
          rendering_mode: 'wms',
          source_protocol: 'wms',
          url: 'https://example.test/wms',
          min_zoom: 2,
          max_zoom: 9,
        },
      }],
    } as unknown as MapSession;

    expect(addOverlayLayers(map as never, session)[0].status).toBe('loaded');
    expect(sources[0]['minzoom']).toBe(2);
    expect(sources[0]['maxzoom']).toBe(9);
    expect((sources[0]['tiles'] as string[])[0]).toContain('request=GetMap');
  });

  it('uses verified inline GeoJSON data without issuing a browser fetch', () => {
    const sources: Array<Record<string, unknown>> = [];
    const layers: Array<Record<string, unknown>> = [];
    const map = {
      addSource: (_id: string, source: Record<string, unknown>) => sources.push(source),
      addLayer: (layer: Record<string, unknown>) => layers.push(layer),
    };
    const session = {
      overlays: [{
        id: 'overpass_poi',
        label: 'Rail stations',
        provider: 'overpass',
        type: 'clustered-points',
        rendering_mode: 'clustered-points',
        data: {
          type: 'FeatureCollection',
          features: [{
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [139.767, 35.681] },
            properties: { category: 'station' },
          }],
        },
      }],
    } as unknown as MapSession;

    expect(addOverlayLayers(map as never, session)[0].status).toBe('loaded');
    expect(sources[0].type).toBe('geojson');
    expect((sources[0].data as { type: string }).type).toBe('FeatureCollection');
    expect(layers[0].type).toBe('circle');
  });
});
