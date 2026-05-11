import {
  API_BASE_URL,
  API_CHAT_TURN_PATH,
} from './constants';
import {
  ApiRequestError,
  buildApiError,
  parseCatalogResponse,
  parseChatTurnResponse,
  parseModelSettingsResponse,
  parseSearchResponse,
  fetchGeospatialLayerFeatures,
  sendChatTurn,
  streamChatTurn,
} from './api';

describe('core/api', () => {
  afterEach(() => {
    (window.fetch as unknown) = undefined;
  });

  it('parseSearchResponse happy path and missing-field failure', () => {
    const parsed = parseSearchResponse({
      status_message: 'ok',
      map_session: { session_id: 'map-1' },
    });
    expect(parsed.status_message).toBe('ok');
    expect(parsed.map_session.session_id).toBe('map-1');
    expect(() => parseSearchResponse({ payload: {} })).toThrowError('Search response is missing status_message');
  });

  it('parseCatalogResponse normalizes entries', () => {
    const parsed = parseCatalogResponse({
      capabilities: [
        { id: 'b1', kind: 'basemap' },
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

  it('parseModelSettingsResponse defaults correctly', () => {
    const parsed = parseModelSettingsResponse({
      credential_health: { openai: { api_key: 'unreadable' } },
    });
    expect(parsed.active_provider_mode).toBe('local');
    expect(parsed.chat_model_provider).toBe('ollama');
    expect(parsed.ollama_url).toBe('http://localhost:11434');
    expect(parsed.credentials).toEqual({});
    expect(parsed.credential_health?.openai.api_key).toBe('unreadable');
  });

  it('parseChatTurnResponse accepts valid backend response', () => {
    const parsed = parseChatTurnResponse({
      request_id: 'chat-abc',
      session_id: 12,
      assistant_message: 'done',
      turn_contract: {
        user_text: 'show weather',
        task_class: 'direct_query',
        location_signals: [],
        normalized_intent: {
          intent_id: 'weather',
          intent_label: 'Weather',
          task_tags: [],
          intent_tags: [],
          requires_location: false,
        },
        temporal_signal: { mode: 'none' },
        ambiguities: [],
        parser_confidence: 0.9,
      },
      decision: {
        plan: { state: 'direct_tool', mode: 'direct_text', intent_id: 'weather', overlay_ids: [] },
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
    expect(parsed.session_id).toBe(12);
    expect(parsed.assistant_message).toBe('done');
    expect(parsed.context_usage?.selected_context_window).toBe(2048);
  });

  it('parseChatTurnResponse rejects missing request_id', () => {
    expect(() => parseChatTurnResponse({
      session_id: 1,
      assistant_message: 'ok',
      turn_contract: {},
      decision: {},
    })).toThrow();
  });

  it('parseChatTurnResponse rejects missing turn_contract', () => {
    expect(() => parseChatTurnResponse({
      request_id: 'chat-1',
      session_id: 1,
      assistant_message: 'ok',
      decision: {},
    })).toThrow();
  });

  it('parseChatTurnResponse rejects missing decision', () => {
    expect(() => parseChatTurnResponse({
      request_id: 'chat-1',
      session_id: 1,
      assistant_message: 'ok',
      turn_contract: {},
    })).toThrow();
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

  it('streamChatTurn parses events and ignores malformed trailing chunk', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('{"event":"status","data":{"message":"received"}}\n'));
        controller.enqueue(new TextEncoder().encode('{"event":"assistant_delta","data":{"delta":"hi "}}\n{"event":"final","data":{}}\n{bad'));
        controller.close();
      },
    });
    const fetchSpy = jasmine.createSpy('fetch').and.resolveTo(
      new Response(stream, { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } }),
    );
    (window.fetch as unknown) = fetchSpy;
    const events: string[] = [];
    await streamChatTurn({ message: 'x' }, (event) => events.push(event.event));
    expect(events).toEqual(['status', 'assistant_delta', 'final']);
  });

  it('streamChatTurn emits error event behavior as ApiRequestError', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('{"event":"error","data":{"message":"stream failed","status":503}}\n'));
        controller.close();
      },
    });
    (window.fetch as unknown) = jasmine.createSpy('fetch').and.resolveTo(
      new Response(stream, { status: 200 }),
    );
    let thrown: unknown;
    try {
      await streamChatTurn({ message: 'x' }, () => undefined);
    } catch (error) {
      thrown = error;
    }
    expect(thrown instanceof ApiRequestError).toBeTrue();
    expect((thrown as ApiRequestError).status).toBe(503);
  });

  it('streamChatTurn timeout path rejects with timeout message', async () => {
    jasmine.clock().install();
    const fetchSpy = jasmine.createSpy('fetch').and.callFake((_: unknown, init?: RequestInit) => (
      new Promise((_, reject) => {
        const signal = init?.signal;
        if (signal) {
          signal.addEventListener('abort', () => reject({ name: 'AbortError' }));
        }
      })
    ));
    (window.fetch as unknown) = fetchSpy;
    const promise = streamChatTurn({ message: 'x' }, () => undefined);
    jasmine.clock().tick(120_100);
    await expectAsync(promise).toBeRejectedWith(jasmine.any(ApiRequestError));
    jasmine.clock().uninstall();
  });

  it('base URL route construction uses API_BASE_URL', async () => {
    const fetchSpy = jasmine.createSpy('fetch').and.resolveTo(
      new Response(JSON.stringify({
        request_id: 'chat-1',
        session_id: 1,
        assistant_message: 'ok',
        turn_contract: {},
        decision: {},
        memory_snapshot: {},
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    (window.fetch as unknown) = fetchSpy;
    await sendChatTurn({ message: 'hello' });
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
});
