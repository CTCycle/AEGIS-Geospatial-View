import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import { ApiClientService } from '../core/api-client.service';
import { defaultAppState } from '../core/app-state';
import { AppStateStoreService } from '../core/app-state-store.service';
import { ChatTurnResponse } from '../core/types';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { GeospatialPageComponent } from './geospatial-page.component';

describe('pages/geospatial-page.component', () => {
  let router: Router;
  let store: jasmine.SpyObj<AppStateStoreService>;
  let errors: jasmine.SpyObj<UserFacingErrorService>;
  let apiClient: jasmine.SpyObj<ApiClientService>;
  let sendChatTurnMock: jasmine.Spy;
  let fetchCatalogMock: jasmine.Spy;

  const makeTurnResponse = (overrides: Record<string, unknown> = {}): ChatTurnResponse => ({
    request_id: 'chat-1',
    session_id: 1,
    assistant_message: 'ok',
    turn_contract: {
      user_text: 'x',
      task_class: 'direct_query',
      location_signals: [],
      normalized_action: { action_id: 'x', action_label: 'X', task_tags: [], action_tags: [], requires_location: false },
      temporal_signal: { mode: 'none' },
      ambiguities: [],
      parser_confidence: 0.9,
    },
    decision: { plan: { state: 'reject', action_id: 'x', overlay_ids: [] } },
    operation: { kind: 'rejection', status: 'failed', message: 'ok', warnings: [] },
    memory_snapshot: {},
    ...overrides,
  });

  beforeEach(async () => {
    store = jasmine.createSpyObj<AppStateStoreService>('AppStateStoreService', ['getChatPage', 'updateChatPage', 'resetChatPage']);
    store.getChatPage.and.returnValue(defaultAppState().chatPage);
    errors = jasmine.createSpyObj<UserFacingErrorService>('UserFacingErrorService', ['toUserFacingError']);
    errors.toUserFacingError.and.returnValue('fallback error');

    apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', ['sendChatTurn', 'fetchCatalog']);
    sendChatTurnMock = jasmine.createSpy('sendChatTurn').and.resolveTo(makeTurnResponse());
    fetchCatalogMock = jasmine.createSpy('fetchCatalog').and.resolveTo({ capabilities: [], basemaps: [], overlays: [], tools: [] });
    apiClient.sendChatTurn.and.callFake((payload) => sendChatTurnMock(payload));
    apiClient.fetchCatalog.and.callFake(() => fetchCatalogMock());

    await TestBed.configureTestingModule({
      imports: [GeospatialPageComponent],
      providers: [
        provideRouter([]),
        { provide: ApiClientService, useValue: apiClient },
        { provide: AppStateStoreService, useValue: store },
        { provide: UserFacingErrorService, useValue: errors },
      ],
    }).compileComponents();
    router = TestBed.inject(Router);
  });

  it('loads initial persisted state', () => {
    const seeded = defaultAppState().chatPage;
    seeded.chatPanel.composerDraft = 'seed draft';
    seeded.chatPanel.messages = [{ role: 'user', content: 'hello' }];
    store.getChatPage.and.returnValue(seeded);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.composerDraft).toBe('seed draft');
    expect(fixture.componentInstance.messages.length).toBe(1);
  });

  it('sendMessage happy path updates status and appends assistant', async () => {
    sendChatTurnMock.and.resolveTo(makeTurnResponse({
      session_id: 42,
      assistant_message: 'Search executed successfully.',
      operation: { kind: 'direct_answer', status: 'success', message: 'Search executed successfully.', warnings: [] },
      map_session: null,
      context_usage: {
        estimated_input_tokens: 120,
        selected_context_window: 2048,
        model_context_limit: 8192,
        usage_percent: 5.9,
        provider: 'ollama',
        model: 'llama3.2',
      },
    }));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show map';
    await component.sendMessage();
    expect(component.status).toBe('Complete');
    expect(component.messages.at(-1)?.content).toContain('Search executed successfully.');
    expect(component.contextUsagePercent).toBe(6);
  });

  it('renders context tracker fallback and telemetry detail', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    expect(component.contextUsageLabel).toBe('0%');
    expect(component.contextUsageDetail).toContain('awaiting first request');

    component.contextUsage = {
      estimated_input_tokens: 321,
      selected_context_window: 2048,
      model_context_limit: 8192,
      usage_percent: 15.7,
      provider: 'ollama',
      model: 'llama3.2',
    };
    fixture.detectChanges();

    const element: HTMLElement = fixture.nativeElement;
    expect(component.contextUsageLabel).toBe('16%');
    expect(element.textContent).toContain('321 / 2048 tokens');
  });

  it('clarification responses set Need more detail status', async () => {
    sendChatTurnMock.and.resolveTo(makeTurnResponse({
      session_id: 42,
      assistant_message: 'Which location should I use?',
      operation: { kind: 'clarification', status: 'partial', message: 'Which location should I use?', warnings: [] },
      decision: { plan: { state: 'clarify', action_id: 'weather', overlay_ids: [] } },
      map_session: null,
      tool_payload: null,
    }));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show weather';
    await component.sendMessage();
    expect(component.status).toBe('Need more detail');
    expect(component.messages.at(-1)?.content).toContain('Which location should I use?');
  });

  it('direct tool payload responses render as assistant message without map session', async () => {
    sendChatTurnMock.and.resolveTo(makeTurnResponse({
      session_id: 42,
      assistant_message: 'Coordinates: 41.8902, 12.4922',
      operation: {
        kind: 'direct_answer',
        status: 'success',
        message: 'Coordinates: 41.8902, 12.4922',
        direct_result: { latitude: 41.8902, longitude: 12.4922 },
        warnings: [],
      },
      decision: { plan: { state: 'direct_tool', action_id: 'location_lookup', overlay_ids: [], tool_id: 'location_to_coordinates' } },
      tool_payload: { tool_id: 'location_to_coordinates', result: { latitude: 41.8902, longitude: 12.4922 } },
      map_session: null,
    }));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'what are the coordinates of the colosseum';
    await component.sendMessage();
    expect(component.status).toBe('Complete');
    expect(component.mapSession).toBeUndefined();
    expect(component.messages.at(-1)?.content).toContain('Coordinates: 41.8902, 12.4922');
  });

  it('prefers operation.map_session over the top-level response map_session', async () => {
    sendChatTurnMock.and.resolveTo(makeTurnResponse({
      assistant_message: 'Map ready.',
      operation: {
        kind: 'map_session',
        status: 'success',
        message: 'Map ready.',
        warnings: [],
        map_session: {
          session_id: 'operation-map',
          resolved_location: { label: 'Rome', latitude: 41.9, longitude: 12.5 },
          basemap_id: 'osm_default',
          overlay_ids: ['safe_overlay'],
          viewport: { center_latitude: 41.9, center_longitude: 12.5, radius_m: 2500 },
          center: { latitude: 41.9, longitude: 12.5 },
          overlays: [{ id: 'safe_overlay', label: 'Safe overlay', provider: 'fixture', type: 'geojson', url: '/api/geospatial/layers/safe_overlay/features' }],
        },
      },
      map_session: {
        session_id: 'fallback-map',
        resolved_location: { label: 'Leaky Rome', latitude: 41.9, longitude: 12.5 },
        basemap_id: 'osm_default',
        overlay_ids: ['leaky_overlay'],
        viewport: { center_latitude: 41.9, center_longitude: 12.5, radius_m: 2500 },
        center: { latitude: 41.9, longitude: 12.5 },
        overlays: [{ id: 'leaky_overlay', label: 'Leaky overlay', provider: 'fixture', type: 'tile', url: 'https://tiles.example/{z}/{x}/{y}.png?api_key=forbidden-secret' }],
      },
    }));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show Rome';

    await component.sendMessage();

    expect(component.mapSession?.session_id).toBe('operation-map');
    expect(component.mapSession?.overlay_ids).toEqual(['safe_overlay']);
    expect(JSON.stringify(component.payload)).not.toContain('forbidden-secret');
    expect(JSON.stringify(component.payload)).not.toContain('api_key=');
  });

  it('operation-driven failures set Failed status even without reject plan state', async () => {
    sendChatTurnMock.and.resolveTo(makeTurnResponse({
      session_id: 42,
      assistant_message: 'Tool timed out.',
      operation: { kind: 'error', status: 'failed', message: 'Tool timed out.', warnings: [] },
      decision: { plan: { state: 'direct_response', action_id: 'weather', overlay_ids: [] } },
      map_session: null,
      tool_payload: null,
    }));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show weather';
    await component.sendMessage();
    expect(component.status).toBe('Failed');
    expect(component.messages.at(-1)?.content).toContain('Tool timed out.');
  });

  it('request nonce blocks stale response overwrite', async () => {
    let resolveTurn: (value: ChatTurnResponse) => void;
    const pending = new Promise<ChatTurnResponse>((resolve) => { resolveTurn = resolve; });
    sendChatTurnMock.and.returnValue(pending);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'first';
    const sendPromise = component.sendMessage();
    component.startNewChat();
    resolveTurn!(makeTurnResponse({ session_id: 7, assistant_message: 'late response', map_session: null }));
    await sendPromise;
    expect(component.messages.find((entry) => entry.content === 'late response')).toBeUndefined();
  });

  it('error path adds fallback assistant message and Failed status', async () => {
    sendChatTurnMock.and.rejectWith(new Error('boom'));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show map';
    await component.sendMessage();
    expect(component.status).toBe('Failed');
    expect(component.messages.at(-1)?.content).toBe('fallback error');
  });

  it('operation-aware alerts include structured failure message', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.status = 'Failed';
    component.lastOperation = {
      kind: 'error',
      status: 'failed',
      message: 'Tool timed out.',
      warnings: [],
    };
    component.messages = [{ role: 'assistant', content: 'Tool timed out.' }];

    expect(component.activeAlertItems).toContain('Tool timed out.');
  });

  it('startNewChat clears session and map/chat state', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.sessionId = 7;
    component.messages = [{ role: 'assistant', content: 'x' }];
    component.composerDraft = 'draft';
    component.payload = {
      map_session: {
        session_id: 's1',
        resolved_location: { label: 'Rome', latitude: 41.9, longitude: 12.5 },
        basemap_id: 'osm_default',
        overlay_ids: [],
        viewport: { center_latitude: 41.9, center_longitude: 12.5, radius_m: 2500 },
        overlays: [],
      },
    };
    component.contextUsage = {
      estimated_input_tokens: 50,
      selected_context_window: 2048,
      model_context_limit: 8192,
      usage_percent: 2.5,
      provider: 'ollama',
      model: 'llama3.2',
    };
    component.startNewChat();
    expect(component.sessionId).toBeUndefined();
    expect(component.messages.length).toBe(0);
    expect(component.composerDraft).toBe('');
    expect(component.payload).toBeUndefined();
    expect(component.contextUsage).toBeUndefined();
    expect(store.resetChatPage).toHaveBeenCalled();
  });

  it('overlay state updates are persisted through sync', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.onOverlayStateChange({ overlayVisibility: { overlay_a: false }, overlayOpacity: { overlay_a: 0.3 } });
    expect(component.mapState.overlayVisibility['overlay_a']).toBeFalse();
    expect(store.updateChatPage).toHaveBeenCalled();
  });

  it('handles zoom commands locally without chat API request', async () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.mapPreview = { zoomIn: jasmine.createSpy('zoomIn').and.returnValue(true) } as never;
    component.composerDraft = 'zoom in';

    await component.sendMessage();

    expect(sendChatTurnMock).not.toHaveBeenCalled();
    expect(component.messages.at(-1)?.content).toBe('Map zoomed in.');
  });

  it('answers capability questions from the catalog locally', async () => {
    fetchCatalogMock.and.resolveTo({
      capabilities: [],
      basemaps: [{ id: 'osm_default', name: 'OpenStreetMap', kind: 'basemap', provider: 'fallback', requires_credentials: false, is_available: true, supports_map: true, supports_direct_text: false, coverage: 'global', action_tags: [], task_tags: [], metadata: {} }],
      overlays: [{ id: 'rainviewer_precipitation_radar', name: 'RainViewer Precipitation Radar', kind: 'overlay', provider: 'rainviewer', requires_credentials: false, is_available: true, supports_map: true, supports_direct_text: false, coverage: 'global-partial', action_tags: [], task_tags: [], metadata: {} }],
      tools: [{ id: 'get_weather_forecast', name: 'Weather Forecast', kind: 'tool', provider: 'openmeteo', requires_credentials: false, is_available: true, supports_map: true, supports_direct_text: true, coverage: 'global', action_tags: [], task_tags: [], metadata: {} }],
    });
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'what can you do?';

    await component.sendMessage();

    expect(sendChatTurnMock).not.toHaveBeenCalled();
    expect(component.messages.at(-1)?.content).toContain('Current catalog: 1 map types, 1 layers, and 1 direct tools.');
  });

  it('navigateToSettings syncs state and routes to settings', () => {
    const navigateSpy = spyOn(router, 'navigateByUrl').and.resolveTo(true);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    fixture.componentInstance.navigateToSettings();
    expect(store.updateChatPage).toHaveBeenCalled();
    expect(navigateSpy).toHaveBeenCalledWith('/settings');
  });

  it('transcript scroll persistence updates state', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.onTranscriptScroll({ target: { scrollTop: 88 } } as unknown as Event);
    expect(component.transcriptScrollTop).toBe(88);
    expect(store.updateChatPage).toHaveBeenCalled();
  });
});
