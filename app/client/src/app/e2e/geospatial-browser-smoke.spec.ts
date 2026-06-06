import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import maplibregl from 'maplibre-gl';

import { CameraPopupComponent } from '../components/camera-popup.component';
import { MapPreviewComponent } from '../components/map-preview.component';
import { ApiClientService } from '../core/api-client.service';
import { defaultAppState } from '../core/app-state';
import { AppStateStoreService } from '../core/app-state-store.service';
import { DEFAULT_BASE_TILE_PROXY_URL } from '../core/constants';
import { CameraFeature, ChatTurnResponse } from '../core/types';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { GeospatialPageComponent } from '../pages/geospatial-page.component';

describe('e2e/geospatial browser smoke', () => {
  const forbiddenSecret = 'sk_live_DO_NOT_RENDER';
  let fixture: ComponentFixture<GeospatialPageComponent>;
  let apiClient: jasmine.SpyObj<ApiClientService>;
  let store: jasmine.SpyObj<AppStateStoreService>;
  let fakeMap: {
    addSource: jasmine.Spy;
    addLayer: jasmine.Spy;
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

  const mockedMapResponse: ChatTurnResponse = {
    request_id: 'browser-smoke-1',
    session_id: 101,
    assistant_message: 'Rendered a mocked geospatial session.',
    turn_contract: {
      user_text: 'show mocked map',
      task_class: 'map_search',
      location_signals: [],
      normalized_action: {
        action_id: 'mocked_map',
        action_label: 'Mocked map',
        task_tags: ['map'],
        action_tags: ['geospatial'],
        requires_location: true,
      },
      temporal_signal: { mode: 'none' },
      ambiguities: [],
      parser_confidence: 0.95,
    },
    decision: {
      plan: {
        state: 'map_search',
        action_id: 'mocked_map',
        basemap_id: 'osm_default',
        overlay_ids: [
          'mock_clustered_points',
          'rainviewer_precipitation_radar_stale',
          'tomtom_traffic_flow_mocked',
          'tomtom_traffic_incidents_mocked',
          'eea_noise_wms',
          'esa_worldcover_wmts',
          'eurostat_metadata_only',
          'eurostat_join_required',
          'gtfs_stops_routes_alerts_vehicles',
          'overpass_poi_amenities_1000_clustered',
          'geospatial_5000_feature_performance',
          'windy_webcams_missing_key',
          'metadata_context',
        ],
      },
    },
    operation: {
      kind: 'map_session',
      status: 'success',
      message: 'Rendered a mocked geospatial session.',
      warnings: [],
    },
    memory_snapshot: { provider_secret_sample: forbiddenSecret },
    map_session: {
      session_id: 'mock-map-session',
      resolved_location: { label: 'Mock City', latitude: 41.9, longitude: 12.5 },
      basemap_id: 'osm_default',
      basemap: {
        id: 'osm_default',
        label: 'OpenStreetMap',
        provider: 'openstreetmap',
        tile_url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        attribution: 'OpenStreetMap contributors',
      },
      overlay_ids: [
        'mock_clustered_points',
        'rainviewer_precipitation_radar_stale',
        'tomtom_traffic_flow_mocked',
        'tomtom_traffic_incidents_mocked',
        'eea_noise_wms',
        'esa_worldcover_wmts',
        'eurostat_metadata_only',
        'eurostat_join_required',
        'gtfs_stops_routes_alerts_vehicles',
        'overpass_poi_amenities_1000_clustered',
        'geospatial_5000_feature_performance',
        'windy_webcams_missing_key',
        'metadata_context',
      ],
      center: { latitude: 41.9, longitude: 12.5 },
      viewport: { center_latitude: 41.9, center_longitude: 12.5, radius_m: 5000 },
      bounds: [12.45, 41.86, 12.55, 41.94],
      compliance_warnings: [
        'Windy Webcams credentials are missing; configure access before live camera previews.',
        'RainViewer radar frame is stale; showing cached public radar tiles.',
      ],
      overlays: [
        {
          id: 'mock_clustered_points',
          label: 'Mock GeoJSON clustered points',
          provider: 'mock_provider',
          type: 'geojson',
          rendering_mode: 'clustered-points',
          data_format: 'GeoJSON',
          geometry_type: 'Point',
          url: '/api/geospatial/layers/mock_clustered_points/features?bbox=12.45,41.86,12.55,41.94',
          attribution: 'Mock source',
          default_opacity: 0.8,
        },
        {
          id: 'rainviewer_precipitation_radar_stale',
          label: 'RainViewer stale radar',
          provider: 'rainviewer',
          type: 'tile',
          rendering_mode: 'raster-tile',
          url: '/api/geospatial/layers/rainviewer_precipitation_radar/tiles/{z}/{x}/{y}.png?frame=stale',
          attribution: 'RainViewer',
          default_opacity: 0.65,
        },
        {
          id: 'tomtom_traffic_flow_mocked',
          label: 'TomTom Traffic Flow',
          provider: 'tomtom',
          type: 'tile',
          rendering_mode: 'raster-tile',
          url: '/api/geospatial/layers/tomtom_traffic_flow/tiles/{z}/{x}/{y}.png',
          attribution: 'TomTom',
          default_opacity: 0.7,
        },
        {
          id: 'tomtom_traffic_incidents_mocked',
          label: 'TomTom Traffic Incidents',
          provider: 'tomtom',
          type: 'geojson',
          rendering_mode: 'geojson',
          data_format: 'GeoJSON',
          geometry_type: 'LineString',
          url: '/api/geospatial/layers/tomtom_traffic_incidents/features?bbox=12.45,41.86,12.55,41.94',
          attribution: 'TomTom',
        },
        {
          id: 'eea_noise_wms',
          label: 'EEA Noise WMS',
          provider: 'eea',
          type: 'wms',
          rendering_mode: 'wms',
          url: '/api/geospatial/layers/eea_noise_wms/wms',
          layers: 'eea:noise',
          attribution: 'European Environment Agency',
          bounds: [-25, 34, 45, 72],
        },
        {
          id: 'esa_worldcover_wmts',
          label: 'ESA WorldCover WMTS',
          provider: 'esa',
          type: 'wmts',
          rendering_mode: 'wmts',
          url: '/api/geospatial/layers/esa_worldcover_wmts/wmts',
          layer_id: 'ESA_WorldCover_10m_2021_v200',
          tile_matrix_set: 'EPSG3857',
          attribution: 'ESA WorldCover',
        },
        {
          id: 'eurostat_metadata_only',
          label: 'Eurostat metadata-only population',
          provider: 'eurostat',
          type: 'metadata-only',
          rendering_mode: 'metadata-only',
          attribution: 'Eurostat',
        },
        {
          id: 'eurostat_join_required',
          label: 'Eurostat NUTS join required',
          provider: 'eurostat',
          type: 'metadata-only',
          rendering_mode: 'metadata-only',
          attribution: 'Eurostat GISCO',
        },
        {
          id: 'gtfs_stops_routes_alerts_vehicles',
          label: 'GTFS stops routes alerts vehicles',
          provider: 'gtfs',
          type: 'geojson',
          rendering_mode: 'clustered-points',
          data_format: 'GeoJSON',
          geometry_type: 'Point',
          url: '/api/geospatial/layers/gtfs_realtime/features?include=stops,routes,alerts,vehicles',
          attribution: 'GTFS feed agency',
        },
        {
          id: 'overpass_poi_amenities_1000_clustered',
          label: '1,000 clustered POIs',
          provider: 'overpass',
          type: 'geojson',
          rendering_mode: 'clustered-points',
          data_format: 'GeoJSON',
          geometry_type: 'Point',
          url: '/api/geospatial/layers/overpass_poi_amenities/features?fixture=1000-pois',
          attribution: 'OpenStreetMap contributors',
        },
        {
          id: 'geospatial_5000_feature_performance',
          label: '5,000 feature performance layer',
          provider: 'fixture',
          type: 'geojson',
          rendering_mode: 'choropleth',
          data_format: 'GeoJSON',
          geometry_type: 'Polygon',
          url: '/api/geospatial/layers/performance_fixture/features?feature_count=5000',
          attribution: 'AEGIS fixture',
          default_opacity: 0.5,
        },
        {
          id: 'metadata_context',
          label: 'Metadata setup layer',
          provider: 'mock_metadata',
          type: 'metadata-only',
          rendering_mode: 'metadata-only',
          attribution: 'Metadata source',
        },
      ],
    },
  };

  beforeEach(async () => {
    fakeMap = {
      addSource: jasmine.createSpy('addSource'),
      addLayer: jasmine.createSpy('addLayer'),
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

    apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', ['sendChatTurn', 'fetchCatalog']);
    apiClient.sendChatTurn.and.resolveTo(mockedMapResponse);
    apiClient.fetchCatalog.and.resolveTo({ capabilities: [], basemaps: [], overlays: [], tools: [] });

    store = jasmine.createSpyObj<AppStateStoreService>('AppStateStoreService', [
      'getChatPage',
      'updateChatPage',
      'resetChatPage',
    ]);
    store.getChatPage.and.returnValue(defaultAppState().chatPage);

    await TestBed.configureTestingModule({
      imports: [GeospatialPageComponent, CameraPopupComponent],
      providers: [
        provideRouter([]),
        { provide: ApiClientService, useValue: apiClient },
        { provide: AppStateStoreService, useValue: store },
        {
          provide: UserFacingErrorService,
          useValue: { toUserFacingError: () => 'Request failed.' },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
  });

  afterEach(() => {
    fixture.destroy();
  });

  it('renders a mocked map session without leaking credentials into DOM or map requests', async () => {
    const component = fixture.componentInstance;
    component.composerDraft = 'show mocked map';

    await component.sendMessage();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const pageElement: HTMLElement = fixture.nativeElement;
    const mapPreview = pageElement.querySelector('app-map-preview');
    expect(mapPreview).withContext('map preview should render in the real browser DOM').not.toBeNull();

    expect(apiClient.sendChatTurn).toHaveBeenCalledWith({
      session_id: undefined,
      message: 'show mocked map',
    });
    expect(maplibregl.Map).toHaveBeenCalled();
    const mapOptions = (maplibregl.Map as unknown as jasmine.Spy).calls.mostRecent().args[0];
    expect(mapOptions.style.sources.basemap.tiles[0]).toBe(DEFAULT_BASE_TILE_PROXY_URL);

    const geoJsonSource = fakeMap.addSource.calls.allArgs()
      .map((args) => args[1] as { type?: string; data?: string; tiles?: string[] })
      .find((source) => source.type === 'geojson');
    expect(geoJsonSource?.data).toContain('/api/geospatial/layers/mock_clustered_points/features');

    const clusteredLayer = fakeMap.addLayer.calls.allArgs()
      .map((args) => args[0] as { type?: string; paint?: Record<string, unknown> })
      .find((layer) => layer.type === 'circle');
    expect(clusteredLayer?.paint?.['circle-color']).toBe('#0ea5e9');

    expect(pageElement.textContent).toContain('Metadata setup layer');
    expect(pageElement.textContent).toContain('credentials are missing');
    expect(pageElement.textContent).toContain('Mock GeoJSON clustered points');

    const renderedMarkup = pageElement.outerHTML;
    const mapRequestInputs = JSON.stringify([
      mapOptions.style,
      fakeMap.addSource.calls.allArgs(),
      fakeMap.addLayer.calls.allArgs(),
    ]);
    expect(renderedMarkup).not.toContain(forbiddenSecret);
    expect(mapRequestInputs).not.toContain(forbiddenSecret);
    expect(mapRequestInputs).not.toContain('api_key=');
    expect(mapRequestInputs).not.toContain('x-windy-api-key');
  });

  it('renders mocked provider families with attribution, stale state, and backend-only URLs', async () => {
    const component = fixture.componentInstance;
    component.composerDraft = 'show mocked map';

    await component.sendMessage();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const pageElement: HTMLElement = fixture.nativeElement;
    const sourceInputs = JSON.stringify(fakeMap.addSource.calls.allArgs());
    const layerInputs = fakeMap.addLayer.calls.allArgs().map((args) => args[0] as { id?: string; type?: string });

    expect(sourceInputs).toContain('rainviewer_precipitation_radar/tiles');
    expect(sourceInputs).toContain('tomtom_traffic_flow/tiles');
    expect(sourceInputs).toContain('tomtom_traffic_incidents/features');
    expect(sourceInputs).toContain('service=WMS');
    expect(sourceInputs).toContain('service=WMTS');
    expect(sourceInputs).toContain('include=stops,routes,alerts,vehicles');
    expect(sourceInputs).toContain('fixture=1000-pois');
    expect(sourceInputs).toContain('feature_count=5000');

    expect(layerInputs.some((layer) => layer.id === 'overlay-layer-geospatial_5000_feature_performance' && layer.type === 'fill')).toBeTrue();
    expect(layerInputs.some((layer) => layer.id === 'overlay-layer-tomtom_traffic_incidents_mocked' && layer.type === 'line')).toBeTrue();
    expect(pageElement.textContent).toContain('RainViewer radar frame is stale');
    expect(pageElement.textContent).toContain('European Environment Agency');
    expect(pageElement.textContent).toContain('ESA WorldCover');
    expect(pageElement.textContent).toContain('Eurostat metadata-only population');
    expect(pageElement.textContent).toContain('Eurostat NUTS join required');
    expect(pageElement.outerHTML).not.toContain(forbiddenSecret);
    expect(sourceInputs).not.toContain('api_key=');
    expect(sourceInputs).not.toContain('sk_live');
  });

  it('keeps camera missing-credential scenarios in the e2e catalog', async () => {
    const component = fixture.componentInstance;
    component.composerDraft = 'show mocked map';

    await component.sendMessage();
    fixture.detectChanges();

    expect(component.payload?.map_session?.overlay_ids).toContain('windy_webcams_missing_key');
    expect(fixture.nativeElement.textContent).toContain('Windy Webcams credentials are missing');
  });

  it('renders Windy popup states without embedding unless provider permission is explicit', async () => {
    const activeCamera: CameraFeature = {
      id: 'windy_webcams/active',
      name: 'Windy Active Harbor',
      provider: 'windy_webcams',
      camera_type: 'webcam',
      latitude: 41.9028,
      longitude: 12.4964,
      last_update_time: '2026-05-12T09:00:00Z',
      preview_image_url: 'https://images.windy.example/preview.jpg',
      official_url: 'https://www.windy.com/webcams/active',
      embed_url: 'https://embed.windy.example/active',
      embedding_allowed: true,
      stale: false,
      metadata: { attribution: 'Windy Webcams' },
    };
    const staleCamera: CameraFeature = {
      ...activeCamera,
      id: 'windy_webcams/stale',
      name: 'Windy Stale Mountain',
      preview_image_url: null,
      embed_url: 'https://embed.windy.example/stale',
      embedding_allowed: false,
      stale: true,
    };

    const activeFixture = TestBed.createComponent(CameraPopupComponent);
    activeFixture.componentInstance.camera = activeCamera;
    activeFixture.detectChanges();
    expect(activeFixture.nativeElement.textContent).toContain('Windy Active Harbor');
    expect(activeFixture.nativeElement.textContent).toContain('41.90280, 12.49640');
    expect(activeFixture.nativeElement.querySelector('img')?.getAttribute('src')).toBe(activeCamera.preview_image_url);
    expect(activeFixture.nativeElement.querySelector('iframe')).not.toBeNull();

    const staleFixture = TestBed.createComponent(CameraPopupComponent);
    staleFixture.componentInstance.camera = staleCamera;
    staleFixture.detectChanges();
    expect(staleFixture.nativeElement.textContent).toContain('Stale');
    expect(staleFixture.nativeElement.querySelector('img')).toBeNull();
    expect(staleFixture.nativeElement.querySelector('iframe')).toBeNull();
    expect(staleFixture.nativeElement.textContent).toContain('Official link');
    expect(staleFixture.nativeElement.outerHTML).not.toContain(forbiddenSecret);

    activeFixture.destroy();
    staleFixture.destroy();
  });
});
