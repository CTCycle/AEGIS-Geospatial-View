import {
  ChatTurnResponse,
  JsonObject,
  RealtimeConnectionState,
  RealtimeServerMessage,
} from './types';

type ResponseProvider = (request: { conversation_id: string; message: string }) => Promise<ChatTurnResponse>;

/**
 * Deterministic in-process transport used by component/browser specs.  It
 * drives the same acknowledgement and ordered event envelopes as the real
 * WebSocket without opening a network connection in Karma.
 */
export class FakeRealtimeService {
  private readonly messageHandlers = new Set<(message: RealtimeServerMessage) => void>();
  private readonly stateHandlers = new Set<(state: RealtimeConnectionState) => void>();
  private conversationId?: string;
  private runCounter = 0;
  private commandCounter = 0;
  private state: RealtimeConnectionState = 'idle';

  constructor(private readonly responseProvider: ResponseProvider) {}

  onMessage(handler: (message: RealtimeServerMessage) => void): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  onStateChange(handler: (state: RealtimeConnectionState) => void): () => void {
    this.stateHandlers.add(handler);
    handler(this.state);
    return () => this.stateHandlers.delete(handler);
  }

  connect(conversationId: string): void {
    this.conversationId = conversationId;
    this.setState('open');
  }

  disconnect(): void {
    this.setState('closed');
  }

  setResumeCursor(_runId: string | undefined, _sequence: number): void {}

  sendRunStart(message: string, _clientRequestId: string): string {
    const conversationId = this.conversationId;
    if (!conversationId) {
      throw new Error('Conversation is not connected.');
    }
    const commandId = `fake_start_${++this.commandCounter}`;
    const runId = `run-${++this.runCounter}`;
    this.emit({
      protocol_version: 1,
      type: 'run.ack',
      message_id: `server_ack_${commandId}`,
      correlation_id: commandId,
      conversation_id: conversationId,
      payload: { command: 'run.start', run_id: runId, run_version: 1, duplicate: false },
    });
    void this.responseProvider({ conversation_id: conversationId, message }).then(
      (response) => this.emitResponse(conversationId, runId, response),
      (error: unknown) => this.emitEvent(conversationId, runId, 1, 'error', {
        code: 'agent_operation_failed',
        message: error instanceof Error ? error.message : 'Request failed.',
      }),
    );
    return commandId;
  }

  sendRunSteer(_runId: string, _message: string, _clientMutationId: string): string {
    return `fake_steer_${++this.commandCounter}`;
  }

  sendRunCancel(runId: string): string {
    const commandId = `fake_cancel_${++this.commandCounter}`;
    this.emit({
      protocol_version: 1,
      type: 'run.ack',
      message_id: `server_ack_${commandId}`,
      correlation_id: commandId,
      conversation_id: this.conversationId ?? '',
      payload: { command: 'run.cancel', run_id: runId, run_version: 1, duplicate: false },
    });
    return commandId;
  }

  private emitResponse(conversationId: string, runId: string, response: ChatTurnResponse): void {
    this.emitEvent(conversationId, runId, 1, 'assistant_text_completed', {
      content: response.assistant_message,
    });
    const failed = response.operation?.status === 'failed';
    const partial = response.operation?.status === 'partial';
    if (failed) {
      this.emitEvent(conversationId, runId, 2, 'error', {
        code: 'agent_operation_failed',
        message: response.operation?.message ?? response.assistant_message,
      });
    } else if (partial) {
      this.emitEvent(conversationId, runId, 2, 'clarification_needed', this.completionPayload(response));
    } else {
      this.emitEvent(conversationId, runId, 2, 'completed', this.completionPayload(response));
    }
  }

  private completionPayload(response: ChatTurnResponse): JsonObject {
    return {
      map_session: response.map_session ?? null,
      operation: response.operation ?? null,
      memory_snapshot: response.memory_snapshot ?? {},
      context_usage: response.context_usage ?? null,
      task_snapshot: response.task_snapshot ?? null,
      context_revision: response.context_revision ?? null,
    } as unknown as JsonObject;
  }

  private emitEvent(
    conversationId: string,
    runId: string,
    sequence: number,
    type: string,
    payload: JsonObject,
  ): void {
    this.emit({
      protocol_version: 1,
      type: 'run.event',
      message_id: `server_event_${runId}_${sequence}`,
      conversation_id: conversationId,
      payload: {
        event_id: `event_${runId}_${sequence}`,
        sequence,
        conversation_id: conversationId,
        run_id: runId,
        run_version: 1,
        type,
        timestamp: new Date().toISOString(),
        visibility: 'user',
        payload,
      },
    });
  }

  private emit(message: RealtimeServerMessage): void {
    this.messageHandlers.forEach((handler) => handler(message));
  }

  private setState(state: RealtimeConnectionState): void {
    this.state = state;
    this.stateHandlers.forEach((handler) => handler(state));
  }
}
