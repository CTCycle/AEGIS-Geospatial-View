import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import maplibregl from 'maplibre-gl';

import { MapPreviewComponent } from '../components/map-preview.component';
import { ApiClientService } from '../core/api-client.service';
import { defaultAppState } from '../core/app-state';
import { AppStateStoreService } from '../core/app-state-store.service';
import { DEFAULT_BASE_TILE_PROXY_URL } from '../core/constants';
import { ChatTurnResponse } from '../core/types';
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
      normalized_intent: {
        intent_id: 'mocked_map',
        intent_label: 'Mocked map',
        task_tags: ['map'],
        intent_tags: ['geospatial'],
        requires_location: true,
      },
      temporal_signal: { mode: 'none' },
      ambiguities: [],
      parser_confidence: 0.95,
    },
    decision: {
      plan: {
        state: 'map_search',
        intent_id: 'mocked_map',
        basemap_id: 'osm_default',
        overlay_ids: ['mock_clustered_points', 'windy_webcams_missing_key', 'metadata_context'],
      },
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
      overlay_ids: ['mock_clustered_points', 'windy_webcams_missing_key', 'metadata_context'],
      center: { latitude: 41.9, longitude: 12.5 },
      viewport: { center_latitude: 41.9, center_longitude: 12.5, radius_m: 5000 },
      bounds: [12.45, 41.86, 12.55, 41.94],
      compliance_warnings: ['Windy Webcams credentials are missing; configure access before live camera previews.'],
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
      imports: [GeospatialPageComponent],
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
  });

  it('keeps camera missing-credential scenarios in the e2e catalog', async () => {
    const component = fixture.componentInstance;
    component.composerDraft = 'show mocked map';

    await component.sendMessage();
    fixture.detectChanges();

    expect(component.payload?.map_session?.overlay_ids).toContain('windy_webcams_missing_key');
    expect(fixture.nativeElement.textContent).toContain('Windy Webcams credentials are missing');
  });
});
