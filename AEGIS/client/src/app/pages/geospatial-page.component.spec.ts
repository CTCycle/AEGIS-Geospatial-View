import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import * as Api from '../core/api';
import { AppStateStoreService } from '../core/app-state-store.service';
import { defaultAppState } from '../core/app-state';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { GeospatialPageComponent } from './geospatial-page.component';

describe('pages/geospatial-page.component', () => {
  let router: Router;
  let store: jasmine.SpyObj<AppStateStoreService>;
  let errors: jasmine.SpyObj<UserFacingErrorService>;

  beforeEach(async () => {
    store = jasmine.createSpyObj<AppStateStoreService>('AppStateStoreService', [
      'getChatPage',
      'updateChatPage',
      'resetChatPage',
    ]);
    store.getChatPage.and.returnValue(defaultAppState().chatPage);
    errors = jasmine.createSpyObj<UserFacingErrorService>('UserFacingErrorService', [
      'toUserFacingError',
    ]);
    errors.toUserFacingError.and.returnValue('fallback error');

    await TestBed.configureTestingModule({
      imports: [GeospatialPageComponent],
      providers: [
        provideRouter([]),
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
    spyOn(Api, 'sendChatTurn').and.resolveTo({
      session_id: 42,
      assistant_message: 'Search executed successfully.',
      map_session: null,
      context_usage: {
        estimated_input_tokens: 120,
        selected_context_window: 2048,
        model_context_limit: 8192,
        usage_percent: 5.9,
        provider: 'ollama',
        model: 'llama3.2',
      },
      follow_up_required: false,
    });
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
    spyOn(Api, 'sendChatTurn').and.resolveTo({
      session_id: 42,
      assistant_message: 'Which location should I use?',
      decision: {
        plan: {
          state: 'clarify',
          intent_id: 'weather',
          overlay_ids: [],
        },
      },
      map_session: null,
      tool_payload: null,
    } as never);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show weather';
    await component.sendMessage();
    expect(component.status).toBe('Need more detail');
    expect(component.messages.at(-1)?.content).toContain('Which location should I use?');
  });

  it('direct tool payload responses render as assistant message without map session', async () => {
    spyOn(Api, 'sendChatTurn').and.resolveTo({
      session_id: 42,
      assistant_message: 'Coordinates: 41.8902, 12.4922',
      decision: {
        plan: {
          state: 'direct_tool',
          intent_id: 'location_lookup',
          overlay_ids: [],
          tool_id: 'location_to_coordinates',
        },
      },
      tool_payload: {
        tool_id: 'location_to_coordinates',
        result: {
          latitude: 41.8902,
          longitude: 12.4922,
        },
      },
      map_session: null,
    } as never);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'what are the coordinates of the colosseum';
    await component.sendMessage();
    expect(component.status).toBe('Complete');
    expect(component.mapSession).toBeUndefined();
    expect(component.messages.at(-1)?.content).toContain('Coordinates: 41.8902, 12.4922');
  });

  it('request nonce blocks stale response overwrite', async () => {
    let resolveTurn: (value: unknown) => void;
    const pending = new Promise((resolve) => { resolveTurn = resolve as (value: unknown) => void; });
    spyOn(Api, 'sendChatTurn').and.returnValue(pending as Promise<unknown>);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'first';
    const sendPromise = component.sendMessage();
    component.startNewChat();
    resolveTurn!({
      session_id: 7,
      assistant_message: 'late response',
      map_session: null,
      follow_up_required: false,
    } as unknown as never);
    await sendPromise;
    expect(component.messages.find((entry) => entry.content === 'late response')).toBeUndefined();
  });

  it('error path adds fallback assistant message and Failed status', async () => {
    spyOn(Api, 'sendChatTurn').and.rejectWith(new Error('boom'));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show map';
    await component.sendMessage();
    expect(component.status).toBe('Failed');
    expect(component.messages.at(-1)?.content).toBe('fallback error');
  });

  it('startNewChat clears session and map/chat state', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.sessionId = 7;
    component.messages = [{ role: 'assistant', content: 'x' }];
    component.composerDraft = 'draft';
    component.payload = { map_session: { overlays: [] } };
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
    component.onOverlayStateChange({
      overlayVisibility: { overlay_a: false },
      overlayOpacity: { overlay_a: 0.3 },
    });
    expect(component.mapState.overlayVisibility['overlay_a']).toBeFalse();
    expect(store.updateChatPage).toHaveBeenCalled();
  });

  it('handles zoom commands locally without chat API request', async () => {
    const sendSpy = spyOn(Api, 'sendChatTurn').and.resolveTo({} as never);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.mapPreview = { zoomIn: jasmine.createSpy('zoomIn').and.returnValue(true) } as never;
    component.composerDraft = 'zoom in';

    await component.sendMessage();

    expect(sendSpy).not.toHaveBeenCalled();
    expect(component.messages.at(-1)?.content).toBe('Map zoomed in.');
  });

  it('answers capability questions from the catalog locally', async () => {
    const sendSpy = spyOn(Api, 'sendChatTurn').and.resolveTo({} as never);
    spyOn(Api, 'fetchCatalog').and.resolveTo({
      capabilities: [],
      basemaps: [{ id: 'osm_default', name: 'OpenStreetMap', kind: 'basemap', provider: 'fallback', requires_credentials: false, is_available: true, supports_map: true, supports_direct_text: false, coverage: 'global', intent_tags: [], task_tags: [], metadata: {} }],
      overlays: [{ id: 'rainviewer_precipitation_radar', name: 'RainViewer Precipitation Radar', kind: 'overlay', provider: 'rainviewer', requires_credentials: false, is_available: true, supports_map: true, supports_direct_text: false, coverage: 'global-partial', intent_tags: [], task_tags: [], metadata: {} }],
      tools: [{ id: 'get_weather_forecast', name: 'Weather Forecast', kind: 'tool', provider: 'openmeteo', requires_credentials: false, is_available: true, supports_map: true, supports_direct_text: true, coverage: 'global', intent_tags: [], task_tags: [], metadata: {} }],
    });
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'what can you do?';

    await component.sendMessage();

    expect(sendSpy).not.toHaveBeenCalled();
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
