import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AgentReadinessService } from '../core/agent-readiness.service';
import { ApiClientService } from '../core/api-client.service';
import { defaultAppState } from '../core/app-state';
import { AppStateStoreService } from '../core/app-state-store.service';
import { FakeRealtimeService } from '../core/realtime.test-support';
import { RealtimeService } from '../core/realtime.service';
import { ChatTurnResponse } from '../core/types';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { GeospatialPageComponent } from './geospatial-page.component';

describe('pages/geospatial-page.component', () => {
  let store: jasmine.SpyObj<AppStateStoreService>;
  let errors: jasmine.SpyObj<UserFacingErrorService>;
  let apiClient: jasmine.SpyObj<ApiClientService>;
  let realtime: FakeRealtimeService;
  let agentReadiness: jasmine.SpyObj<AgentReadinessService>;
  let sendChatTurnMock: jasmine.Spy;

  const makeTurnResponse = (overrides: Record<string, unknown> = {}): ChatTurnResponse => ({
    conversation_id: 'conv-1',
    request_id: 'chat-1',
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

    apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', ['createConversation', 'sendChatTurn']);
    apiClient.createConversation.and.resolveTo({ conversation_id: 'conv-1', title: 'test' });
    sendChatTurnMock = jasmine.createSpy('sendChatTurn').and.resolveTo(makeTurnResponse());
    apiClient.sendChatTurn.and.callFake((payload) => sendChatTurnMock(payload));
    realtime = new FakeRealtimeService((payload) => apiClient.sendChatTurn(payload));
    agentReadiness = jasmine.createSpyObj<AgentReadinessService>('AgentReadinessService', ['loadReadiness']);
    agentReadiness.loadReadiness.and.resolveTo({
      status: 'active',
      label: 'Configured',
      message: 'gpt-4.1-mini is configured through OpenAI. Live inference is verified on the first request.',
    });

    await TestBed.configureTestingModule({
      imports: [GeospatialPageComponent],
      providers: [
        provideRouter([]),
        { provide: ApiClientService, useValue: apiClient },
        { provide: RealtimeService, useValue: realtime },
        { provide: AppStateStoreService, useValue: store },
        { provide: AgentReadinessService, useValue: agentReadiness },
        { provide: UserFacingErrorService, useValue: errors },
      ],
    }).compileComponents();
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
    expect(component.status).toBe('Agent ready');
    expect(component.messages.at(-1)?.content).toContain('Search executed successfully.');
    expect(component.contextUsagePercent).toBe(6);
  });

  it('clarification responses return the persistent agent status to ready', async () => {
    sendChatTurnMock.and.resolveTo(makeTurnResponse({
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
    expect(component.status).toBe('Agent ready');
    expect(component.messages.at(-1)?.content).toContain('Which location should I use?');
  });

  it('direct tool payload responses render as assistant message without map session', async () => {
    sendChatTurnMock.and.resolveTo(makeTurnResponse({
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
    expect(component.status).toBe('Agent ready');
    expect(component.mapSession).toBeUndefined();
    expect(component.messages.at(-1)?.content).toContain('Coordinates: 41.8902, 12.4922');
  });

  it('prefers operation.map_session over the top-level response map_session', async () => {
    const mapResponse = makeTurnResponse({
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
    });
    sendChatTurnMock.and.resolveTo(mapResponse);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show Rome';

    await component.sendMessage();
    await Promise.resolve();
    // The component's eager change detection starts MapLibre in a real
    // browser; this unit spec focuses on payload precedence and sanitization.
    component['applyTurnResponse'](mapResponse, component.conversationNonce);

    expect(component['pendingMapSession']?.session_id).toBe('operation-map');
    component.onMapRenderStateChange({ sessionId: 'operation-map', state: 'ready' });
    expect(component.mapSession?.session_id).toBe('operation-map');
    expect(component.mapSession?.overlay_ids).toEqual(['safe_overlay']);
    expect(JSON.stringify(component.payload)).not.toContain('forbidden-secret');
    expect(JSON.stringify(component.payload)).not.toContain('api_key=');
  });

  it('operation-driven failures preserve the response and flag the agent model', async () => {
    sendChatTurnMock.and.resolveTo(makeTurnResponse({
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
    expect(component.status).toBe('Agent needs attention');
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
    resolveTurn!(makeTurnResponse({ assistant_message: 'late response', map_session: null }));
    await sendPromise;
    expect(component.messages.find((entry) => entry.content === 'late response')).toBeUndefined();
  });

  it('error path adds fallback assistant message and flags the agent model', async () => {
    sendChatTurnMock.and.rejectWith(new Error('boom'));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show map';
    await component.sendMessage();
    expect(component.status).toBe('Agent needs attention');
    expect(component.messages.at(-1)?.content).toBe('boom');
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

  it('loads typed agent readiness through the core service', async () => {
    agentReadiness.loadReadiness.and.resolveTo({
      status: 'needs_attention',
      label: 'Needs attention',
      message: 'Selected OpenAI credential needs attention (unreadable).',
    });
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    const component = fixture.componentInstance;

    expect(component.agentReadiness.status).toBe('needs_attention');
    expect(component.capabilityStatusItems[0]).toEqual({
      label: 'Agent model',
      statusLabel: 'Needs attention',
      tone: 'warn',
    });
    expect(component.activeAlertItems).toContain('Selected OpenAI credential needs attention (unreadable).');
  });

  it('clarification run event applies partial map update and closes the run', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.conversationId = 'conv-1';
    component.isLoading = true;
    component.activeRunId = 'run-1';
    component['handleRunEvent']({
      event_id: 'event-1',
      sequence: 1,
      conversation_id: 'conv-1',
      run_id: 'run-1',
      run_version: 1,
      type: 'clarification_needed',
      timestamp: new Date().toISOString(),
      visibility: 'user',
      payload: {
        operation: {
          kind: 'clarification',
          status: 'partial',
          message: 'Which temperature?',
        },
        map_session: {
          session_id: 'street-map',
          resolved_location: { label: 'Colosseum, Rome', latitude: 41.8902, longitude: 12.4922 },
          basemap_id: 'osm_default',
          overlay_ids: ['overpass_residential_buildings'],
          viewport: { center_latitude: 41.8902, center_longitude: 12.4922, radius_m: 2500 },
          overlays: [],
        },
      },
    });
    component.onMapRenderStateChange({ sessionId: 'street-map', state: 'ready' });
    expect(component.status).toBe('Agent ready');
    expect(component.isLoading).toBeFalse();
    expect(component.activeRunId).toBeUndefined();
    expect(component.mapSession?.basemap_id).toBe('osm_default');
    expect(component.mapSession?.resolved_location.label).toBe('Colosseum, Rome');
  });

  it('refreshes the visible progress state when a run event arrives', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.conversationId = 'conv-1';
    component.isLoading = true;
    component.progressLabel = 'Understanding the request';
    fixture.detectChanges();

    component['handleRunEvent']({
      event_id: 'event-progress',
      sequence: 1,
      conversation_id: 'conv-1',
      run_id: 'run-1',
      run_version: 1,
      type: 'progress',
      timestamp: new Date().toISOString(),
      visibility: 'user',
      payload: { stage: 'rendering_map', label: 'Rendering map...' },
    });

    expect(fixture.nativeElement.textContent).toContain('Rendering map...');
  });

  it('does not duplicate an assistant message when the matching error event arrives', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.conversationId = 'conv-1';
    component.messages = [{ role: 'assistant', content: 'Provider timed out.' }];
    component['handleRunEvent']({
      event_id: 'event-error',
      sequence: 2,
      conversation_id: 'conv-1',
      run_id: 'run-1',
      run_version: 1,
      type: 'error',
      timestamp: new Date().toISOString(),
      visibility: 'user',
      payload: { message: 'Provider timed out.' },
    });
    expect(component.messages.length).toBe(1);
    expect(component.status).toBe('Agent needs attention');
    expect(component.agentReadiness).toEqual({
      status: 'needs_attention',
      label: 'Needs attention',
      message: 'Provider timed out.',
    });
  });

  it('rejects messages beyond the realtime contract before creating a conversation', async () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'a'.repeat(component.maxChatMessageLength + 1);

    await component.sendMessage();
    fixture.detectChanges();

    expect(apiClient.createConversation).not.toHaveBeenCalled();
    expect(component.status).toBe(`Message must be ${component.maxChatMessageLength.toLocaleString()} characters or fewer.`);
    expect(component.composerDraft.length).toBe(component.maxChatMessageLength + 1);
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain(component.composerError);
  });

  it('starts each request at understanding and returns the persistent agent to ready', async () => {
    let resolveTurn: (value: ChatTurnResponse) => void;
    sendChatTurnMock.and.returnValue(
      new Promise<ChatTurnResponse>((resolve) => {
        resolveTurn = resolve;
      }),
    );
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    expect(component.status).toBe('Agent ready');

    const pending = component['startAgentRun']('show rain', component.conversationNonce);

    expect(component.status).toBe('Understanding the request');
    expect(component.progressLabel).toBe('Understanding the request');
    resolveTurn!(makeTurnResponse({
      assistant_message: 'Rain ready.',
      operation: { kind: 'direct_answer', status: 'success', message: 'Rain ready.', warnings: [] },
    }));
    await pending;
    await Promise.resolve();
    expect(component.status).toBe('Agent ready');
  });

  it('startNewChat clears conversation and map/chat state', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.conversationId = 'conv-1';
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
    expect(component.conversationId).toBeUndefined();
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

  it('routes capability questions to the agent instead of a prebuilt local response', async () => {
    sendChatTurnMock.and.resolveTo(makeTurnResponse({
      assistant_message: '**Capabilities**\n\n- Maps\n- Weather',
      operation: {
        kind: 'capability_catalog',
        status: 'success',
        message: '**Capabilities**\n\n- Maps\n- Weather',
        warnings: [],
      },
    }));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'what can you do?';

    await component.sendMessage();

    expect(sendChatTurnMock).toHaveBeenCalled();
    expect(component.messages.at(-1)?.content).toContain('**Capabilities**');
  });

});
