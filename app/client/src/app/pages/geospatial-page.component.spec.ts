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

    apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', [
      'createConversation',
      'fetchConversationSnapshot',
      'sendChatTurn',
      'fetchCatalog',
      'fetchChatSettings',
    ]);
    apiClient.createConversation.and.resolveTo({ conversation_id: 'conv-1', title: 'test' });
    sendChatTurnMock = jasmine.createSpy('sendChatTurn').and.resolveTo(makeTurnResponse());
    apiClient.sendChatTurn.and.callFake((payload) => sendChatTurnMock(payload));
    apiClient.fetchCatalog.and.resolveTo({ capabilities: [], basemaps: [], overlays: [], tools: [] });
    apiClient.fetchChatSettings.and.resolveTo({
      active_provider_mode: 'cloud',
      agent_model_provider: 'openai',
      agent_model_name: 'gpt-4.1',
      ollama_url: 'http://127.0.0.1:11434',
      credentials: {},
      selected_model_context: {
        provider: 'openai',
        model: 'gpt-4.1',
        context_window_tokens: 1_047_576,
        maximum_output_tokens: 32_768,
        context_profile_source: 'openai_model_catalog',
      },
    });
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
    seeded.chatPanel.conversationId = undefined;
    store.getChatPage.and.returnValue(seeded);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.composerDraft).toBe('seed draft');
    expect(fixture.componentInstance.messages.length).toBe(0);
  });

  it('hydrates durable conversation state before connecting realtime', async () => {
    const seeded = defaultAppState().chatPage;
    seeded.chatPanel.conversationId = 'conv-restore';
    seeded.chatPanel.lastRunSequence = 7;
    store.getChatPage.and.returnValue(seeded);
    apiClient.fetchConversationSnapshot.and.resolveTo({
      conversation_id: 'conv-restore',
      title: 'Restored conversation',
      context_revision: 3,
      messages: [
        { role: 'user', content: 'Show Rome', created_at: '2026-08-31T10:00:00Z' },
        { role: 'assistant', content: 'Restored', created_at: '2026-08-31T10:00:01Z' },
      ],
      task_snapshot: null,
      memory_snapshot: { location_slots: [] },
      map_session: null,
      active_run: { run_id: 'run-restore', run_version: 2, state: 'running' },
    });
    const connectSpy = spyOn(realtime, 'connect').and.callThrough();

    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(apiClient.fetchConversationSnapshot).toHaveBeenCalledWith('conv-restore');
    expect(fixture.componentInstance.contextRevision).toBe(3);
    expect(fixture.componentInstance.messages.map((message) => message.content)).toEqual(['Show Rome', 'Restored']);
    expect(fixture.componentInstance.activeRunId).toBe('run-restore');
    expect(fixture.componentInstance.isLoading).toBeTrue();
    expect(connectSpy.calls.mostRecent().args[0]).toBe('conv-restore');
    expect(connectSpy.calls.mostRecent().args[1]).toEqual({
      runId: 'run-restore',
      afterSequence: 7,
    });
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

  it('uses the top-level response map_session as the single map result', async () => {
    const mapResponse = makeTurnResponse({
      assistant_message: 'Map ready.',
      operation: {
        kind: 'map_session',
        status: 'success',
        message: 'Map ready.',
        warnings: [],
      },
      map_session: {
        session_id: 'canonical-map',
        resolved_location: { label: 'Rome', latitude: 41.9, longitude: 12.5 },
        basemap_id: 'osm_default',
        basemap: {
          id: 'osm_default',
          label: 'OpenStreetMap',
          provider: 'openstreetmap',
          tile_url: '/api/geospatial/tiles/osm_default/{z}/{x}/{y}.png',
          render_status: 'available',
        },
        viewport: { center_latitude: 41.9, center_longitude: 12.5, radius_m: 2500 },
        center: { latitude: 41.9, longitude: 12.5 },
        overlay_collection: {
          collection_id: 'active-map',
          revision: 0,
          instances: [{
            instance_id: 'safe_overlay',
            capability_id: 'safe_overlay',
            label: 'Safe overlay',
            provider: 'fixture',
            overlay_type: 'geojson',
            rendering_mode: 'geojson',
            scope_key: 'global',
            scope: { kind: 'global' },
            visible: true,
            opacity: 1,
            render_variant: {},
            descriptor: {
              id: 'safe_overlay',
              url: '/api/geospatial/layers/safe_overlay/features',
            },
            inspections: [],
          }],
        },
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
    // browser; this unit spec focuses on the single map result path.
    component['applyTurnResponse'](mapResponse, component.conversationNonce);

    expect(component['pendingMapSession']?.session_id).toBe('canonical-map');
    component.onMapRenderStateChange({ sessionId: 'canonical-map', state: 'ready' });
    expect(component.mapSession?.session_id).toBe('canonical-map');
    expect(component.mapSession?.overlay_collection.instances.map((instance) => instance.capability_id))
      .toEqual(['safe_overlay']);
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
          basemap: {
            id: 'osm_default',
            label: 'OpenStreetMap',
            provider: 'openstreetmap',
            tile_url: '/api/geospatial/tiles/osm_default/{z}/{x}/{y}.png',
            render_status: 'available',
          },
          viewport: { center_latitude: 41.8902, center_longitude: 12.4922, radius_m: 2500 },
          overlay_collection: { collection_id: 'active-map', revision: 0, instances: [] },
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
      payload: {
        message: 'Provider timed out.',
        context_usage: {
          estimated_input_tokens: 321,
          selected_context_window: null,
          model_context_limit: null,
          usage_percent: null,
          provider: 'opencode-go',
          model: 'deepseek-v4-flash',
          usage_source: 'estimated',
        },
      },
    });
    expect(component.messages.length).toBe(1);
    expect(component.status).toBe('Agent needs attention');
    expect(component.contextUsage?.estimated_input_tokens).toBe(321);
    expect(component.contextUsageLabel).toBe('Context limit unavailable');
    expect(component.contextUsageDetail).toContain('max context unavailable');
    expect(component.contextUsageDetail.toLowerCase()).not.toContain('token');
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
        basemap: {
          id: 'osm_default',
          label: 'OpenStreetMap',
          provider: 'openstreetmap',
          tile_url: '/api/geospatial/tiles/osm_default/{z}/{x}/{y}.png',
          render_status: 'available',
        },
        viewport: { center_latitude: 41.9, center_longitude: 12.5, radius_m: 2500 },
        overlay_collection: { collection_id: 'active-map', revision: 0, instances: [] },
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

  it('keeps send and stop in one composer action cell', async () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const sendMessage = spyOn(component, 'sendMessage').and.resolveTo();
    const cancelActiveRun = spyOn(component, 'cancelActiveRun').and.resolveTo();
    const button = (): HTMLButtonElement => fixture.nativeElement.querySelector('.chat-composer .primary-button');

    component.composerDraft = 'show Rome';
    fixture.detectChanges();
    expect(button().getAttribute('aria-label')).toBe('Send message');
    expect(fixture.nativeElement.querySelector('[aria-label="Cancel active run"]')).toBeNull();
    button().click();
    expect(sendMessage).toHaveBeenCalled();

    component.isLoading = true;
    fixture.detectChanges();
    expect(button().getAttribute('aria-label')).toBe('Stop generating');
    expect(button().querySelector('.composer-stop-icon')).not.toBeNull();
    button().click();
    expect(cancelActiveRun).toHaveBeenCalled();
  });

  it('honors a stop request made before the run acknowledgement arrives', async () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.conversationId = 'conv-1';
    component.isLoading = true;

    await component.cancelActiveRun();
    expect(component['cancelRequested']).toBeTrue();
    realtime.connect('conv-1');

    component['handleRealtimeMessage']({
      protocol_version: 1,
      type: 'run.ack',
      message_id: 'ack-start',
      conversation_id: 'conv-1',
      payload: { command: 'run.start', run_id: 'run-1', run_version: 1, duplicate: false },
    } as never);

    expect(component['cancelRequested']).toBeFalse();
    expect(component.isLoading).toBeFalse();
    expect(component.status).toBe('Agent ready');
  });

  it('shows the selected model context cap and exposes the compact workspace footer', async () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;

    expect(component.contextUsage?.selected_context_window).toBe(1_047_576);
    expect(component.contextUsageDetail).toMatch(/max context 1[,.]047[,.]576/);
    const footer = fixture.nativeElement.querySelector('.workspace-status-bar') as HTMLElement | null;
    expect(footer).not.toBeNull();
    expect(footer?.textContent).toContain('Agent model');
    expect(footer?.textContent).toContain('Satellite');
    expect(footer?.textContent).toContain('Weather');
    expect(footer?.textContent).toContain('Optional Keys');
    expect(fixture.nativeElement.querySelector('.context-window-row')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.context-window-row progress')).toBeNull();
    expect(fixture.nativeElement.querySelector('.chat-status-strip')).toBeNull();
    expect(fixture.nativeElement.querySelector('.rail-capability-card')).toBeNull();
    expect(fixture.nativeElement.querySelector('.rail-context-strip')).toBeNull();
  });

  it('loads the context indicator from current backend model settings', async () => {
    apiClient.fetchChatSettings.and.resolveTo({
      active_provider_mode: 'local',
      agent_model_provider: 'ollama',
      agent_model_name: 'qwen3.5:2b',
      ollama_url: 'http://127.0.0.1:11434',
      credentials: {},
      selected_model_context: {
        provider: 'ollama',
        model: 'qwen3.5:2b',
        context_window_tokens: 40_960,
        maximum_output_tokens: null,
        context_profile_source: 'provider_metadata',
      },
    });

    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.componentInstance.contextUsage?.selected_context_window).toBe(40_960);
    expect(fixture.componentInstance.contextUsage?.provider).toBe('ollama');
    expect(fixture.componentInstance.contextUsage?.model).toBe('qwen3.5:2b');
  });

  it('distinguishes estimated, provider-reported, unknown-cap, and unmeasured states', async () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;

    component.contextUsage = {
      estimated_input_tokens: 300,
      selected_context_window: 4096,
      model_context_limit: 4096,
      usage_percent: 10.4,
      provider: 'test',
      model: 'runtime-model',
      usage_source: 'estimated',
    };
    expect(component.contextUsageLabel).toBe('~10%');

    component.contextUsage = {
      estimated_input_tokens: 300,
      reported_input_tokens: 280,
      selected_context_window: 4096,
      model_context_limit: 4096,
      usage_percent: 9.1,
      provider: 'test',
      model: 'runtime-model',
      usage_source: 'provider_reported',
    };
    expect(component.contextUsageLabel).toBe('9%');

    component.contextUsage = {
      estimated_input_tokens: 321,
      selected_context_window: null,
      model_context_limit: null,
      usage_percent: null,
      provider: 'test',
      model: 'runtime-model',
      usage_source: 'estimated',
    };
    fixture.detectChanges();
    expect(component.contextUsageLabel).toBe('Context limit unavailable');
    expect(component.contextUsageDetail).toContain('max context unavailable');
    expect(component.contextUsageDetail.toLowerCase()).not.toContain('token');
    expect(fixture.nativeElement.querySelector('.context-window-row progress')).toBeNull();

    component.contextUsage = {
      estimated_input_tokens: 0,
      selected_context_window: 4096,
      model_context_limit: 4096,
      usage_percent: null,
      provider: 'test',
      model: 'runtime-model',
      usage_source: 'not_measured',
    };
    expect(component.contextUsageLabel).toBe('No request measured');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.context-window-row progress')).toBeNull();
  });

  it('uses peak request telemetry for the visible context status', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    component.contextUsage = {
      estimated_input_tokens: 300,
      reported_input_tokens: 280,
      peak_request_tokens: 900,
      total_input_tokens: 1180,
      selected_context_window: 4096,
      model_context_limit: 4096,
      usage_percent: 22,
      provider: 'test',
      model: 'runtime-model',
      usage_source: 'provider_reported',
    };
    fixture.detectChanges();

    expect(component.contextUsageLabel).toBe('22%');
    expect(component.contextUsageDetail).toContain('900 peak');
    expect(component.contextUsageDetail).toMatch(/remaining 3[,.]?196/);
    expect((fixture.nativeElement.querySelector('.context-window-row progress') as HTMLProgressElement).getAttribute('value')).toBe('22');
  });

  it('shows raw over-cap context percentage while clamping only the progress bar', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    component.contextUsage = {
      estimated_input_tokens: 5000,
      selected_context_window: 4096,
      model_context_limit: 4096,
      usage_percent: 122.1,
      provider: 'test',
      model: 'runtime-model',
      usage_source: 'estimated',
    };
    fixture.detectChanges();

    expect(component.contextUsageLabel).toBe('~122%');
    expect(component.contextUsagePercent).toBe(100);
    expect(component.contextUsageDetail).toContain('(122.1%)');
    expect((fixture.nativeElement.querySelector('.context-window-row progress') as HTMLProgressElement).getAttribute('value')).toBe('100');
  });

  it('applies live context events without changing progress status', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.conversationId = 'conv-1';
    component.activeRunId = 'run-1';
    component.status = 'Calling a relevant tool';
    component.progressStage = 'calling_tool';
    component.progressLabel = 'Calling a relevant tool';

    component['handleRunEvent']({
      event_id: 'context-1',
      sequence: 1,
      conversation_id: 'conv-1',
      run_id: 'run-1',
      run_version: 1,
      type: 'context_usage',
      timestamp: new Date().toISOString(),
      visibility: 'user',
      payload: {
        phase: 'parser',
        context_usage: {
          estimated_input_tokens: 700,
          selected_context_window: 4096,
          model_context_limit: 4096,
          usage_percent: 17.1,
          provider: 'test',
          model: 'runtime-model',
          usage_source: 'estimated',
        },
      },
    });

    expect(component.contextUsageLabel).toBe('~17%');
    expect(component.status).toBe('Calling a relevant tool');
    expect(component.progressStage).toBe('calling_tool');
    expect(component.progressLabel).toBe('Calling a relevant tool');
  });

  it('retains the last measured context sample after failed or partial turns', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const previous = {
      estimated_input_tokens: 240,
      reported_input_tokens: 220,
      selected_context_window: 4096,
      model_context_limit: 4096,
      usage_percent: 7.8,
      provider: 'test',
      model: 'runtime-model',
      usage_source: 'provider_reported' as const,
    };
    component.contextUsage = previous;

    component['applyTurnResponse'](makeTurnResponse({
      operation: { kind: 'error', status: 'failed', message: 'Provider failed.', warnings: [] },
      context_usage: {
        estimated_input_tokens: 900,
        selected_context_window: null,
        model_context_limit: null,
        usage_percent: null,
        provider: 'test',
        model: 'runtime-model',
        usage_source: 'not_measured',
      },
    }), component.conversationNonce);
    expect(component.contextUsage).toEqual(previous);

    component['applyTurnResponse'](makeTurnResponse({
      operation: { kind: 'clarification', status: 'partial', message: 'Need clarification.', warnings: [] },
      context_usage: {
        estimated_input_tokens: 901,
        selected_context_window: null,
        model_context_limit: null,
        usage_percent: null,
        provider: 'test',
        model: 'runtime-model',
        usage_source: 'not_measured',
      },
    }), component.conversationNonce);
    expect(component.contextUsage).toEqual(previous);

    component['applyTurnResponse'](makeTurnResponse({
      operation: { kind: 'error', status: 'failed', message: 'Measured failure.', warnings: [] },
      context_usage: {
        estimated_input_tokens: 900,
        peak_request_tokens: 640,
        selected_context_window: 4096,
        model_context_limit: 4096,
        usage_percent: 15.6,
        provider: 'test',
        model: 'runtime-model',
        usage_source: 'provider_reported',
      },
    }), component.conversationNonce);
    expect(component.contextUsage?.peak_request_tokens).toBe(640);
  });

  it('switches the active session to a catalog-provided satellite descriptor', async () => {
    apiClient.fetchCatalog.and.resolveTo({
      capabilities: [],
      basemaps: [
        {
          id: 'esri_world_imagery',
          name: 'Satellite Imagery Basemap',
          provider: 'arcgis',
          kind: 'basemap',
          type: 'tile',
          description: 'Public satellite imagery',
          requires_credentials: false,
          is_available: true,
          supports_map: true,
          supports_direct_text: false,
          coverage: 'global',
          render: {
            status: 'available',
            tile_url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attribution: 'Esri',
          },
          action_tags: [],
          task_tags: [],
          metadata: {},
        },
      ],
    });
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    component.mapSession = {
      session_id: 'map-1',
      resolved_location: { label: 'Rome', latitude: 41.9, longitude: 12.5 },
      basemap_id: 'osm_default',
      overlay_ids: [],
      viewport: { center_latitude: 41.9, center_longitude: 12.5, radius_m: 2500 },
      overlays: [],
    } as never;
    component.onBasemapChange('esri_world_imagery');

    expect(component.payload?.map_session?.basemap_id).toBe('esri_world_imagery');
    expect(component.payload?.map_session?.basemap?.tile_url).toContain('World_Imagery');
    expect(component.availableBasemaps.map((item) => item.id)).toEqual(['esri_world_imagery']);
  });

});
