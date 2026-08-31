import {
  API_BASE_URL,
  API_CHAT_TURN_PATH,
  API_CONVERSATION_PATH,
} from './constants';
import {
  ApiRequestError,
  buildApiError,
  fetchConversationSnapshot,
  fetchGeospatialCameras,
  fetchGeospatialLayerFeatures,
  sendChatTurn,
} from './api';
import {
  buildModelDescription,
  parseCatalogResponse,
  parseChatTurnResponse,
  parseConversationSnapshotResponse,
  parseModelSettingsResponse,
} from './api-parsers';

describe('core/api', () => {
  afterEach(() => {
    (window.fetch as unknown) = undefined;
  });

  it('parseCatalogResponse normalizes entries', () => {
    const parsed = parseCatalogResponse({
      capabilities: [
        { id: 'b1', kind: 'basemap' },
      ],
      basemaps: [
        { id: 'b1', kind: 'basemap' },
      ],
      overlays: [
        {
          id: 'o1',
          kind: 'overlay',
          capabilityKind: 'raster-overlay',
          renderingMode: 'wmts',
          reliability: {
            status: 'partial',
            lastAudited: '2026-05-11',
            knownLimitations: ['time dimension'],
          },
          auth: {
            type: 'api-key',
            required: true,
            providerKey: 'tomtom',
            accessPageProviderId: 'tomtom',
          },
        },
      ],
      providers: [],
      cameras: [],
      transit: [],
      tools: [],
    });
    expect(parsed.basemaps?.[0].id).toBe('b1');
    expect(parsed.basemaps?.[0].name).toBe('b1');
    expect(parsed.overlays?.[0].id).toBe('o1');
    expect(parsed.overlays?.[0].name).toBe('o1');
    expect(parsed.overlays?.[0].capability_kind).toBe('raster-overlay');
    expect(parsed.overlays?.[0].rendering_mode).toBe('wmts');
    expect(parsed.overlays?.[0].reliability?.status).toBe('partial');
    expect(parsed.overlays?.[0].auth?.providerKey).toBe('tomtom');
  });

  it('parseCatalogResponse does not reconstruct grouped arrays from capabilities', () => {
    const parsed = parseCatalogResponse({
      capabilities: [{ id: 'b1', kind: 'basemap' }],
    });
    expect(parsed.capabilities.length).toBe(1);
    expect(parsed.basemaps?.length ?? 0).toBe(0);
    expect(parsed.overlays?.length ?? 0).toBe(0);
  });

  it('parseModelSettingsResponse defaults correctly', () => {
    const parsed = parseModelSettingsResponse({
      credential_health: { openai: { api_key: 'unreadable' } },
    });
    expect(parsed.active_provider_mode).toBe('cloud');
    expect(parsed.agent_model_provider).toBe('');
    expect(parsed.ollama_url).toBe('http://127.0.0.1:11434');
    expect(parsed.credentials).toEqual({});
    expect(parsed.credential_health?.openai.api_key).toBe('unreadable');
    expect(parsed.deepseek_base_url).toBeNull();
  });

  it('parseChatTurnResponse accepts valid backend response', () => {
    const parsed = parseChatTurnResponse({
      conversation_id: 'conv-abc',
      request_id: 'chat-abc',
      assistant_message: 'done',
      turn_contract: {
        user_text: 'show weather',
        task_class: 'direct_query',
        location_signals: [],
        normalized_action: {
          action_id: 'weather',
          action_label: 'Weather',
          task_tags: [],
          action_tags: [],
          requires_location: false,
        },
        temporal_signal: { mode: 'none' },
        ambiguities: [],
        parser_confidence: 0.9,
      },
      decision: {
        plan: { state: 'direct_tool', mode: 'direct_text', action_id: 'weather', overlay_ids: [] },
      },
      operation: {
        kind: 'direct_answer',
        status: 'success',
        message: 'done',
        warnings: [],
      },
      context_usage: {
        estimated_input_tokens: 100,
        selected_context_window: 2048,
        model_context_limit: 8192,
        usage_percent: 4.9,
        provider: 'ollama',
        model: 'llama3.2',
      },
    });
    expect(parsed.request_id).toBe('chat-abc');
    expect(parsed.conversation_id).toBe('conv-abc');
    expect(parsed.assistant_message).toBe('done');
    expect(parsed.operation?.kind).toBe('direct_answer');
    expect(parsed.context_usage?.selected_context_window).toBe(2048);
  });

  it('parseConversationSnapshotResponse accepts the current durable contract', () => {
    const parsed = parseConversationSnapshotResponse({
      conversation_id: 'conv-abc',
      title: 'Rome map',
      context_revision: 4,
      messages: [
        { role: 'user', content: 'Show Rome', created_at: '2026-08-31T10:00:00Z' },
        { role: 'assistant', content: 'Done', created_at: '2026-08-31T10:00:01Z' },
      ],
      memory_snapshot: { location_slots: [] },
      task_snapshot: null,
      map_session: null,
      active_run: {
        run_id: 'run-1',
        run_version: 2,
        state: 'running',
      },
    });

    expect(parsed.conversation_id).toBe('conv-abc');
    expect(parsed.messages.length).toBe(2);
    expect(parsed.messages[1].kind).toBe('normal');
    expect(parsed.active_run?.run_id).toBe('run-1');
  });

  it('parseConversationSnapshotResponse rejects legacy or malformed durable state', () => {
    expect(() => parseConversationSnapshotResponse({
      conversation_id: 'conv-abc',
      context_revision: 1,
      messages: [{ role: 'assistant', content: 'missing timestamp' }],
      memory_snapshot: {},
    })).toThrow();
    expect(() => parseConversationSnapshotResponse({
      conversation_id: 'conv-abc',
      context_revision: 1,
      messages: [],
      memory_snapshot: {},
      task_snapshot: {
        schema_version: 2,
        conversation_key: 'conv-abc',
        tasks: [],
        geospatial_state: {},
        evidence_refs: [],
        assumptions: [],
        unresolved_questions: [],
      },
    })).toThrow();
  });

  it('fetchConversationSnapshot uses the encoded conversation route', async () => {
    const fetchSpy = jasmine.createSpy('fetch').and.resolveTo(
      new Response(JSON.stringify({
        conversation_id: 'conv/abc',
        title: null,
        context_revision: 0,
        messages: [],
        memory_snapshot: {},
        task_snapshot: null,
        map_session: null,
        active_run: null,
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    (window.fetch as unknown) = fetchSpy;

    await fetchConversationSnapshot('conv/abc');

    expect(fetchSpy.calls.mostRecent().args[0]).toBe(
      `${API_BASE_URL}${API_CONVERSATION_PATH('conv/abc')}`,
    );
  });

  [
    {
      label: 'request_id',
      payload: {
        conversation_id: 'conv-1',
        assistant_message: 'ok',
        turn_contract: {},
        decision: {},
      },
    },
    {
      label: 'turn_contract',
      payload: {
        request_id: 'chat-1',
        conversation_id: 'conv-1',
        assistant_message: 'ok',
        decision: {},
      },
    },
    {
      label: 'decision',
      payload: {
        request_id: 'chat-1',
        conversation_id: 'conv-1',
        assistant_message: 'ok',
        turn_contract: {},
      },
    },
  ].forEach(({ label, payload }) => {
    it(`parseChatTurnResponse rejects missing ${label}`, () => {
      expect(() => parseChatTurnResponse(payload)).toThrow();
    });
  });

  it('buildApiError builds ApiRequestError', async () => {
    const response = new Response(JSON.stringify({ detail: 'bad request' }), {
      status: 400,
      statusText: 'Bad Request',
      headers: { 'Content-Type': 'application/json' },
    });
    const err = await buildApiError(response);
    expect(err instanceof ApiRequestError).toBeTrue();
    expect(err.message).toBe('bad request');
    expect(err.status).toBe(400);
  });

  it('base URL route construction uses API_BASE_URL', async () => {
    const fetchSpy = jasmine.createSpy('fetch').and.resolveTo(
      new Response(JSON.stringify({
        request_id: 'chat-1',
        conversation_id: 'conv-1',
        assistant_message: 'ok',
        turn_contract: {},
        decision: {},
        operation: { kind: 'direct_answer', status: 'success', message: 'ok' },
        memory_snapshot: {},
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    (window.fetch as unknown) = fetchSpy;
    await sendChatTurn({ conversation_id: 'conv-1', message: 'hello' });
    expect(fetchSpy).toHaveBeenCalled();
    const calledUrl = fetchSpy.calls.mostRecent().args[0] as string;
    expect(calledUrl).toBe(`${API_BASE_URL}${API_CHAT_TURN_PATH}`);
  });

  it('fetchGeospatialLayerFeatures forwards live provider query flags', async () => {
    const fetchSpy = jasmine.createSpy('fetch').and.resolveTo(
      new Response(JSON.stringify({
        status: 'ok',
        provider: 'tomtom',
        payload: {},
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    (window.fetch as unknown) = fetchSpy;

    await fetchGeospatialLayerFeatures('tomtom_traffic_flow', {
      bbox: '12,41,13,42',
      zoom: 10,
      time: '2026-05-11T12:00:00Z',
      live: true,
      incidents: true,
    });

    const calledUrl = fetchSpy.calls.mostRecent().args[0] as string;
    expect(calledUrl).toContain('/geospatial/layers/tomtom_traffic_flow/features?');
    expect(calledUrl).toContain('bbox=12%2C41%2C13%2C42');
    expect(calledUrl).toContain('zoom=10');
    expect(calledUrl).toContain('time=2026-05-11T12%3A00%3A00Z');
    expect(calledUrl).toContain('live=true');
    expect(calledUrl).toContain('incidents=true');
  });

  it('fetchGeospatialCameras omits empty, false, and undefined query params', async () => {
    const fetchSpy = jasmine.createSpy('fetch').and.resolveTo(
      new Response(JSON.stringify({
        status: 'ok',
        provider: 'windy_webcams',
        payload: {},
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    (window.fetch as unknown) = fetchSpy;

    await fetchGeospatialCameras({
      bbox: '',
      provider: 'windy_webcams',
      camera_type: undefined,
    });

    const calledUrl = fetchSpy.calls.mostRecent().args[0] as string;
    expect(calledUrl).toBe(`${API_BASE_URL}/geospatial/cameras?provider=windy_webcams`);
  });

  [
    {
      label: 'treats placeholder local Ollama descriptions as missing',
      payload: {
        description: 'local',
        metadata: {
          family: 'qwen2',
          parameter_size: '7.6B',
          quantization_level: 'Q4_K_M',
        },
      },
      expected: 'Optimized for qwen2 7.6B Q4_K_M.',
    },
    {
      label: 'treats Ollama technical summaries as generated metadata, not authored descriptions',
      payload: {
        description: 'qwen2 | 7.6B | Q4_K_M',
        metadata: {
          family: 'qwen2',
          parameter_size: '7.6B',
          quantization_level: 'Q4_K_M',
        },
      },
      expected: 'Optimized for qwen2 7.6B Q4_K_M.',
    },
    {
      label: 'keeps provider-authored model descriptions',
      payload: {
        description: 'A provider-authored summary.',
        metadata: {},
      },
      expected: 'A provider-authored summary.',
    },
  ].forEach(({ label, payload, expected }) => {
    it(label, () => {
      expect(buildModelDescription(payload)).toBe(expected);
    });
  });
});
