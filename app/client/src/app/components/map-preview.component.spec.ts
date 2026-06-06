import { ComponentFixture, TestBed } from '@angular/core/testing';
import maplibregl from 'maplibre-gl';

import { DEFAULT_BASE_TILE_MAX_ZOOM, DEFAULT_BASE_TILE_PROXY_URL, DEFAULT_MAP_FIT_MAX_ZOOM } from '../core/constants';
import { MapPreviewComponent } from './map-preview.component';

describe('components/map-preview.component', () => {
  let fixture: ComponentFixture<MapPreviewComponent>;
  let component: MapPreviewComponent;
  const makeMapSession = (overrides: Record<string, unknown> = {}) => ({
    session_id: 'map-1',
    resolved_location: { label: 'Rome', latitude: 41.9, longitude: 12.5 },
    basemap_id: 'osm_default',
    overlay_ids: [],
    viewport: { center_latitude: 41.9, center_longitude: 12.5, radius_m: 2500 },
    center: { latitude: 41.9, longitude: 12.5 },
    overlays: [],
    ...overrides,
  });
  let fakeMap: {
    addSource: jasmine.Spy;
    addLayer: jasmine.Spy;
    addControl: jasmine.Spy;
    on: jasmine.Spy;
    fitBounds: jasmine.Spy;
    getLayer: jasmine.Spy;
    setLayoutProperty: jasmine.Spy;
    setPaintProperty: jasmine.Spy;
    zoomIn: jasmine.Spy;
    zoomOut: jasmine.Spy;
    resize: jasmine.Spy;
    remove: jasmine.Spy;
  };

  beforeEach(async () => {
    fakeMap = {
      addSource: jasmine.createSpy('addSource'),
      addLayer: jasmine.createSpy('addLayer'),
      addControl: jasmine.createSpy('addControl'),
      on: jasmine.createSpy('on').and.callFake((_: string, callback: () => void) => callback()),
      fitBounds: jasmine.createSpy('fitBounds'),
      getLayer: jasmine.createSpy('getLayer').and.returnValue({}),
      setLayoutProperty: jasmine.createSpy('setLayoutProperty'),
      setPaintProperty: jasmine.createSpy('setPaintProperty'),
      zoomIn: jasmine.createSpy('zoomIn'),
      zoomOut: jasmine.createSpy('zoomOut'),
      resize: jasmine.createSpy('resize'),
      remove: jasmine.createSpy('remove'),
    };
    spyOn(maplibregl, 'Map').and.returnValue(fakeMap as never);

    await TestBed.configureTestingModule({
      imports: [MapPreviewComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(MapPreviewComponent);
    component = fixture.componentInstance;
  });

  it('builds basemap style with defaults when basemap not provided', () => {
    component.payload = { map_session: makeMapSession() as never };
    fixture.detectChanges();
    expect(maplibregl.Map).toHaveBeenCalled();
    const style = (maplibregl.Map as unknown as jasmine.Spy).calls.mostRecent().args[0].style;
    expect(style.sources.basemap.tiles[0]).toBe(DEFAULT_BASE_TILE_PROXY_URL);
    expect(style.sources.basemap.maxzoom).toBe(DEFAULT_BASE_TILE_MAX_ZOOM);
    expect(style.layers.find((layer: { id: string }) => layer.id === 'basemap')?.maxzoom).toBe(DEFAULT_BASE_TILE_MAX_ZOOM);
  });

  it('preserves external satellite imagery tile URLs', () => {
    component.payload = {
      map_session: makeMapSession({
        basemap_id: 'gibs_satellite',
        basemap: {
          id: 'gibs_satellite',
          label: 'Satellite Imagery',
          provider: 'gibs',
          tile_url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        },
      }) as never,
    };
    fixture.detectChanges();
    const style = (maplibregl.Map as unknown as jasmine.Spy).calls.mostRecent().args[0].style;
    expect(style.sources.basemap.tiles[0]).toContain('World_Imagery/MapServer/tile/{z}/{y}/{x}');
  });

  it('fits bounds with a capped max zoom and resizes after load', () => {
    component.payload = {
      map_session: makeMapSession({
        center: { latitude: 41.9028, longitude: 12.4964 },
        bounds: [12.4963044, 41.902725, 12.4964044, 41.902825],
      }) as never,
    };

    fixture.detectChanges();

    expect(fakeMap.resize).toHaveBeenCalled();
    expect(fakeMap.fitBounds).toHaveBeenCalledWith(
      [[12.4963044, 41.902725], [12.4964044, 41.902825]],
      { padding: 30, duration: 0, maxZoom: DEFAULT_MAP_FIT_MAX_ZOOM },
    );
  });

  it('ignores invalid bounds for fitBounds', () => {
    component.payload = {
      map_session: makeMapSession({
        bounds: [12.49, Number.NaN, 12.50, 41.9],
      }) as never,
    };
    fixture.detectChanges();
    expect(fakeMap.fitBounds).not.toHaveBeenCalled();
  });

  it('creates a MapLibre map only when center coordinates are finite numbers', () => {
    component.payload = {
      map_session: makeMapSession({
        center: { latitude: Number.NaN, longitude: 12.4964 },
      }) as never,
    };

    fixture.detectChanges();

    expect(maplibregl.Map).not.toHaveBeenCalled();
  });

  it('rebuilds overlay state from session and emits notice for stale ids', () => {
    component.initialOverlayVisibility = { stale_overlay: true };
    component.initialOverlayOpacity = { stale_overlay: 0.2 };
    component.payload = {
      map_session: makeMapSession({
        overlays: [{ id: 'openaq', label: 'OpenAQ', type: 'tile', provider: 'openaq', url: 'https://x/{z}/{x}/{y}.png' }],
      }) as never,
    };
    fixture.detectChanges();
    expect(component.overlayVisibility['openaq']).toBeTrue();
    expect(component.restoreNotice).toContain('could not be restored');
  });

  it('emits visibility and opacity updates', () => {
    const emitted: Array<{ overlayVisibility: Record<string, boolean>; overlayOpacity: Record<string, number> }> = [];
    component.overlayStateChange.subscribe((value) => emitted.push(value));
    component.payload = {
      map_session: makeMapSession({
        overlays: [{ id: 'ov1', label: 'Overlay', type: 'tile', provider: 'x', url: 'https://x/{z}/{x}/{y}.png' }],
      }) as never,
    };
    fixture.detectChanges();
    component.setOverlayVisibility('ov1', false);
    component.setOverlayOpacity('ov1', '25');
    expect(emitted.at(-1)?.overlayVisibility['ov1']).toBeFalse();
    expect(emitted.at(-1)?.overlayOpacity['ov1']).toBeCloseTo(0.25, 2);
  });

  it('clamps and ignores invalid overlay opacity values', () => {
    component.payload = {
      map_session: makeMapSession({
        overlays: [{ id: 'ov1', label: 'Overlay', type: 'tile', provider: 'x', url: 'https://x/{z}/{x}/{y}.png' }],
      }) as never,
    };
    fixture.detectChanges();

    component.setOverlayOpacity('ov1', '250');
    expect(component.overlayOpacity['ov1']).toBe(1);

    component.setOverlayOpacity('ov1', 'not-a-number');
    expect(component.overlayOpacity['ov1']).toBe(1);
  });

  it('exposes lightweight zoom controls', () => {
    component.payload = { map_session: makeMapSession() as never };
    fixture.detectChanges();
    expect(component.zoomIn()).toBeTrue();
    expect(component.zoomOut()).toBeTrue();
    expect(fakeMap.zoomIn).toHaveBeenCalledWith({ duration: 120 });
    expect(fakeMap.zoomOut).toHaveBeenCalledWith({ duration: 120 });
  });

  it('builds raster, WMS, and WMTS source URLs', () => {
    component.payload = {
      map_session: makeMapSession({
        overlays: [
          { id: 'tile_1', label: 'Tile', type: 'tile', provider: 'x', url: 'https://tiles/{z}/{x}/{y}.png' },
          {
            id: 'wms_1',
            label: 'WMS',
            type: 'wms',
            provider: 'x',
            url: 'https://wms.example',
            tile_url_template: 'https://wms.example?service=WMS&request=GetMap&layers=abc',
            layers: 'abc',
          },
          {
            id: 'wmts_1',
            label: 'WMTS',
            type: 'wmts',
            provider: 'x',
            url: 'https://wmts.example',
            tile_url_template: 'https://wmts.example?service=WMTS&request=GetTile&layer=layer',
            layer_id: 'layer',
            tile_matrix_set: 'EPSG:3857',
          },
        ],
      }) as never,
    };
    fixture.detectChanges();
    const calls = fakeMap.addSource.calls.allArgs().map((args) => args[1]);
    const sourceTiles = calls
      .map((entry) => (entry as { tiles?: string[] }).tiles?.[0])
      .filter((entry): entry is string => typeof entry === 'string');
    expect(sourceTiles.some((url) => url.includes('tiles/{z}/{x}/{y}.png'))).toBeTrue();
    expect(sourceTiles).toContain('https://wms.example?service=WMS&request=GetMap&layers=abc');
    expect(sourceTiles).toContain('https://wmts.example?service=WMTS&request=GetTile&layer=layer');
  });

  it('ignores malformed overlays without preventing the base map from rendering', () => {
    component.payload = {
      map_session: makeMapSession({
        overlays: [
          { id: 'broken_overlay', label: 'Broken overlay', provider: 'fixture', type: 'mystery' },
        ],
      }) as never,
    };

    fixture.detectChanges();

    expect(maplibregl.Map).toHaveBeenCalled();
    const style = (maplibregl.Map as unknown as jasmine.Spy).calls.mostRecent().args[0].style;
    expect(style.sources.basemap.tiles[0]).toBe(DEFAULT_BASE_TILE_PROXY_URL);
    expect(fakeMap.addSource.calls.allArgs().length).toBe(0);
  });

  it('renders GeoJSON overlay sources as vector layers', () => {
    component.payload = {
      map_session: makeMapSession({
        overlays: [
          {
            id: 'census_hydro',
            label: 'Hydro',
            type: 'arcgis-geojson',
            provider: 'census',
            url: 'https://example.test/query?f=geojson',
            data_format: 'GeoJSON',
            geometry_type: 'LineString',
          },
        ],
      }) as never,
    };
    fixture.detectChanges();
    const source = fakeMap.addSource.calls.mostRecent().args[1] as { type: string; data?: string };
    expect(source.type).toBe('geojson');
    expect(source.data).toContain('f=geojson');
    expect(fakeMap.addLayer.calls.mostRecent().args[0].type).toBe('line');
  });

  it('renders choropleth and camera point modes with distinct map layers', () => {
    component.payload = {
      map_session: makeMapSession({
        overlays: [
          {
            id: 'demographics',
            label: 'Demographics',
            type: 'geojson',
            rendering_mode: 'choropleth',
            provider: 'census',
            url: 'https://example.test/demographics.geojson',
            data_format: 'GeoJSON',
            geometry_type: 'Polygon',
          },
          {
            id: 'webcams',
            label: 'Webcams',
            type: 'geojson',
            rendering_mode: 'camera-points',
            provider: 'windy_webcams',
            url: 'https://example.test/cameras.geojson',
            data_format: 'GeoJSON',
            geometry_type: 'Point',
          },
        ],
      }) as never,
    };
    fixture.detectChanges();
    const layers = fakeMap.addLayer.calls.allArgs().map((args) => args[0] as { type: string; paint: Record<string, unknown> });
    expect(layers.some((layer) => layer.type === 'fill' && 'fill-opacity' in layer.paint)).toBeTrue();
    expect(layers.some((layer) => layer.type === 'circle' && layer.paint['circle-color'] === '#f97316')).toBeTrue();
  });

  it('renders vector tile overlays and exposes metadata-only notices', () => {
    component.payload = {
      map_session: makeMapSession({
        overlays: [
          {
            id: 'natural_earth',
            label: 'Natural Earth',
            type: 'vector-tile',
            rendering_mode: 'vector-tile',
            provider: 'natural_earth',
            url: 'https://example.test/tiles/{z}/{x}/{y}.pbf',
            tile_url_template: 'https://proxy.test/tiles/natural_earth/{z}/{x}/{y}.pbf',
            layer_id: 'admin',
            source_layer: 'admin_boundaries',
            attribution: 'Natural Earth',
          },
          {
            id: 'parcel_template',
            label: 'Parcel template',
            type: 'metadata-only',
            rendering_mode: 'metadata-only',
            provider: 'local_open_data',
          },
        ],
      }) as never,
    };
    fixture.detectChanges();
    const vectorSource = fakeMap.addSource.calls.allArgs()
      .map((args) => args[1] as { type?: string; tiles?: string[] })
      .find((source) => source.type === 'vector');
    expect(vectorSource?.tiles?.[0]).toBe('https://proxy.test/tiles/natural_earth/{z}/{x}/{y}.pbf');
    const vectorLayer = fakeMap.addLayer.calls.allArgs()
      .map((args) => args[0] as { id?: string; ['source-layer']?: string })
      .find((layer) => layer.id === 'overlay-layer-natural_earth');
    expect(vectorLayer?.['source-layer']).toBe('admin_boundaries');
    expect(component.metadataOnlyOverlays.map((overlay) => overlay.id)).toContain('parcel_template');
    expect(component.attributionEntries).toContain('Natural Earth');
  });

  it('does not crash when map session is absent', () => {
    component.payload = {};
    fixture.detectChanges();
    expect(component.mapSession).toBeUndefined();
  });

  it('binds embedded html as plain srcdoc string', () => {
    component.payload = {
      satellite_imagery: { map_html: '<html><body><h1>Map</h1></body></html>' },
    } as never;
    fixture.detectChanges();
    const iframe = fixture.nativeElement.querySelector('iframe') as HTMLIFrameElement | null;
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('srcdoc')).toContain('<h1>Map</h1>');
    expect(iframe?.getAttribute('srcdoc')).not.toContain('SafeValue must use [property]=');
  });

  it('does not materialize credential-bearing URLs into chosen map session state or source definitions', () => {
    component.payload = {
      map_session: makeMapSession({
        overlays: [
          {
            id: 'safe_overlay',
            label: 'Safe overlay',
            type: 'geojson',
            provider: 'fixture',
            url: '/api/geospatial/layers/safe_overlay/features',
            data_format: 'GeoJSON',
            geometry_type: 'Point',
          },
        ],
      }) as never,
    };

    fixture.detectChanges();

    expect(JSON.stringify(component.mapSession)).not.toContain('api_key=');
    expect(JSON.stringify(component.mapSession)).not.toContain('sk_live');
    expect(JSON.stringify(fakeMap.addSource.calls.allArgs())).not.toContain('api_key=');
    expect(fixture.nativeElement.outerHTML).not.toContain('api_key=');
  });

  it('maps overlay ids directly when overlay descriptors are absent', () => {
    component.payload = {
      map_session: {
        ...makeMapSession(),
        center: { latitude: 45.4642, longitude: 9.19 },
        basemap_id: 'osm_default',
        overlay_ids: ['openmeteo_weather_forecast', 'rainviewer_precipitation_radar'],
      } as never,
    };
    fixture.detectChanges();
    expect(component.mapSession?.overlay_ids).toEqual([
      'openmeteo_weather_forecast',
      'rainviewer_precipitation_radar',
    ]);
    expect(component.overlays.map((overlay) => overlay.id)).toEqual([
      'openmeteo_weather_forecast',
      'rainviewer_precipitation_radar',
    ]);
    expect(component.mapSession?.basemap?.id).toBe('osm_default');
  });

  it('cleans up map on destroy', () => {
    component.payload = { map_session: makeMapSession() as never };
    fixture.detectChanges();
    fixture.destroy();
    expect(fakeMap.remove).toHaveBeenCalled();
  });
});
