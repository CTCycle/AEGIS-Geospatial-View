import {
  parseRealtimeServerMessage,
  parseRunCompletionPayload,
  parseRunEvent,
} from './realtime-parsers';

describe('realtime parsers', () => {
  it('parses JSON envelopes and enforces protocol and conversation boundaries', () => {
    const message = parseRealtimeServerMessage(JSON.stringify({
      protocol_version: 1,
      type: 'run.event',
      message_id: 'message-1',
      correlation_id: null,
      conversation_id: 'conversation-1',
      payload: { event_id: 'event-1' },
    }), 'conversation-1');

    expect(message).toEqual(jasmine.objectContaining({
      protocol_version: 1,
      type: 'run.event',
      conversation_id: 'conversation-1',
      payload: { event_id: 'event-1' },
    }));
    expect(parseRealtimeServerMessage({
      protocol_version: 1,
      type: 'run.event',
      conversation_id: 'conversation-2',
      payload: {},
    }, 'conversation-1')).toBeNull();
    expect(parseRealtimeServerMessage({
      protocol_version: 1,
      type: 'run.event',
      conversation_id: 'conversation-1',
      payload: [],
    }, 'conversation-1')).toBeNull();
  });

  it('accepts only discriminated, sequenced run events', () => {
    const event = parseRunEvent({
      event_id: 'event-1',
      sequence: 4,
      conversation_id: 'conversation-1',
      run_id: 'run-1',
      run_version: 2,
      type: 'assistant_text_delta',
      timestamp: '2026-08-17T08:00:00Z',
      visibility: 'user',
      payload: { delta: 'hello' },
    }, 'conversation-1');

    expect(event?.sequence).toBe(4);
    const delta: unknown = event?.payload['delta'];
    expect(delta).toBe('hello');
    expect(parseRunEvent({
      event_id: 'event-2',
      sequence: 4.5,
      conversation_id: 'conversation-1',
      run_id: 'run-1',
      run_version: 2,
      type: 'unknown',
      timestamp: '2026-08-17T08:00:00Z',
      visibility: 'user',
      payload: {},
    }, 'conversation-1')).toBeUndefined();
  });

  it('accepts context usage as a sequenced non-progress run event', () => {
    const event = parseRunEvent({
      event_id: 'context-1',
      sequence: 5,
      conversation_id: 'conversation-1',
      run_id: 'run-1',
      run_version: 2,
      type: 'context_usage',
      timestamp: '2026-08-17T08:00:00Z',
      visibility: 'user',
      payload: {
        phase: 'parser',
        context_usage: {
          estimated_input_tokens: 700,
          model_context_limit: 4096,
          usage_percent: 17.1,
          provider: 'test',
          model: 'runtime-model',
        },
      },
    }, 'conversation-1');

    expect(event?.type).toBe('context_usage');
    const phase: unknown = event?.payload['phase'];
    expect(phase).toBe('parser');
  });

  it('normalizes valid terminal fields and ignores malformed optional fields', () => {
    const parsed = parseRunCompletionPayload({
      context_revision: 3,
      operation: {
        kind: 'direct_answer',
        status: 'success',
        message: 'Completed',
      },
      memory_snapshot: { topic: 'maps' },
      context_usage: {
        estimated_input_tokens: 120,
        usage_percent: 4.5,
        provider: 'ollama',
        model: 'llama3.2',
      },
      decision: {
        plan: {
          state: 'direct_tool',
          action_id: 'location_lookup',
          overlay_ids: [],
        },
      },
      map_session: { session_id: 42 },
      task_snapshot: { conversation_key: 'conversation-1', tasks: [{ malformed: true }] },
    });

    expect(parsed.contextRevision).toBe(3);
    expect(parsed.operation?.kind).toBe('direct_answer');
    const memorySnapshot: unknown = parsed.memorySnapshot;
    expect(memorySnapshot).toEqual({ topic: 'maps' });
    expect(parsed.contextUsage?.estimated_input_tokens).toBe(120);
    expect(parsed.decision?.plan.action_id).toBe('location_lookup');
    expect(parsed.mapSession).toBeUndefined();
    expect(parsed.taskSnapshot).toBeUndefined();
  });
});
