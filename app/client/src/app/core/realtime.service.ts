import { Injectable } from '@angular/core';

import {
  API_BASE_URL,
  API_CONVERSATION_REALTIME_PATH,
  REALTIME_PROTOCOL_VERSION,
  REALTIME_SUBPROTOCOL,
} from './constants';
import { isRecord } from './type-guards';
import {
  JsonObject,
  RealtimeConnectionState,
  RealtimeServerMessage,
} from './types';

type RealtimeMessageHandler = (message: RealtimeServerMessage) => void;
type RealtimeStateHandler = (state: RealtimeConnectionState) => void;

interface PendingCommand {
  type: string;
  message_id: string;
  payload: JsonObject;
  sentGeneration?: number;
  ackTimer?: number;
}

const RECONNECT_BASE_MS = 500;
const RECONNECT_CAP_MS = 30_000;
const HEARTBEAT_STALE_MS = 40_000;
const STABLE_CONNECTION_RESET_MS = 30_000;
const COMMAND_ACK_TIMEOUT_MS = 10_000;
const MAX_PENDING_COMMANDS = 128;

@Injectable({ providedIn: 'root' })
export class RealtimeService {
  private socket?: WebSocket;
  private socketGeneration = 0;
  private conversationId?: string;
  private shouldReconnect = false;
  private reconnectAttempts = 0;
  private reconnectTimer?: number;
  private stableTimer?: number;
  private staleTimer?: number;
  private lastIncomingAt = 0;
  private resumeRunId?: string;
  private resumeSequence = 0;
  private readonly pendingCommands = new Map<string, PendingCommand>();
  private readonly messageHandlers = new Set<RealtimeMessageHandler>();
  private readonly stateHandlers = new Set<RealtimeStateHandler>();
  private state: RealtimeConnectionState = 'idle';

  onMessage(handler: RealtimeMessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  onStateChange(handler: RealtimeStateHandler): () => void {
    this.stateHandlers.add(handler);
    handler(this.state);
    return () => this.stateHandlers.delete(handler);
  }

  connect(conversationId: string, options: { runId?: string; afterSequence?: number } = {}): void {
    if (!conversationId) {
      return;
    }
    if (this.conversationId && this.conversationId !== conversationId) {
      // Never carry unacknowledged commands from one conversation onto a new
      // socket.  A route change is a new ownership boundary; only a reconnect
      // for the same conversation may replay pending idempotent commands.
      this.disconnect({ discardPending: true });
    }
    this.conversationId = conversationId;
    this.resumeRunId = options.runId;
    this.resumeSequence = Math.max(0, options.afterSequence ?? 0);
    this.shouldReconnect = true;
    this.clearReconnectTimer();
    if (this.socket && this.socket.readyState !== WebSocket.CLOSED) {
      return;
    }
    this.openSocket();
  }

  disconnect(options: { discardPending?: boolean } = {}): void {
    this.shouldReconnect = false;
    this.clearReconnectTimer();
    this.clearStableTimer();
    this.clearStaleTimer();
    this.socketGeneration += 1;
    const socket = this.socket;
    this.socket = undefined;
    if (options.discardPending) {
      this.clearPendingCommandTimers();
      this.pendingCommands.clear();
    }
    if (socket && socket.readyState !== WebSocket.CLOSED) {
      socket.close(1000, 'client_closed');
    }
    this.setState('closed');
  }

  setResumeCursor(runId: string | undefined, sequence: number): void {
    this.resumeRunId = runId;
    this.resumeSequence = Math.max(0, sequence);
  }

  sendRunStart(message: string, clientRequestId: string): string {
    return this.queueCommand('run.start', {
      message,
      client_request_id: clientRequestId,
    });
  }

  sendRunSteer(runId: string, message: string, clientMutationId: string): string {
    return this.queueCommand('run.steer', {
      run_id: runId,
      message,
      client_mutation_id: clientMutationId,
    });
  }

  sendRunCancel(runId: string, reason = 'user_cancelled'): string {
    return this.queueCommand('run.cancel', { run_id: runId, reason });
  }

  get connectionState(): RealtimeConnectionState {
    return this.state;
  }

  private queueCommand(type: string, payload: JsonObject): string {
    const messageId = this.newMessageId(type.replace('.', '_'));
    if (this.pendingCommands.size >= MAX_PENDING_COMMANDS) {
      this.setState('failed');
      throw new Error('Realtime command queue is full.');
    }
    this.pendingCommands.set(messageId, { type, message_id: messageId, payload });
    this.flushPendingCommands();
    return messageId;
  }

  private openSocket(): void {
    if (!this.conversationId || typeof window === 'undefined' || typeof WebSocket === 'undefined') {
      this.setState('failed');
      return;
    }
    this.setState(this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting');
    const generation = ++this.socketGeneration;
    const socket = new WebSocket(this.buildSocketUrl(this.conversationId), REALTIME_SUBPROTOCOL);
    this.socket = socket;
    socket.onopen = () => {
      if (!this.isCurrent(socket, generation)) {
        return;
      }
      this.lastIncomingAt = Date.now();
      this.setState('open');
      this.startStableTimer();
      this.startStaleTimer();
      this.sendEnvelope('session.resume', {
        run_id: this.resumeRunId ?? null,
        after_sequence: this.resumeSequence,
      }, false);
      this.flushPendingCommands();
    };
    socket.onmessage = (event: MessageEvent<unknown>) => {
      if (!this.isCurrent(socket, generation)) {
        return;
      }
      this.lastIncomingAt = Date.now();
      const message = this.parseServerMessage(event.data);
      if (!message) {
        this.setState('failed');
        socket.close(1002, 'invalid_server_message');
        return;
      }
      if (message.correlation_id && (message.type === 'run.ack' || message.type === 'protocol.error')) {
        const pending = this.pendingCommands.get(message.correlation_id);
        if (pending?.ackTimer !== undefined) {
          window.clearTimeout(pending.ackTimer);
        }
        this.pendingCommands.delete(message.correlation_id);
      }
      if (message.type === 'heartbeat.ping') {
        const nonce = message.payload['nonce'];
        this.sendEnvelope('heartbeat.pong', { nonce: nonce ?? null }, false);
      }
      this.messageHandlers.forEach((handler) => handler(message));
    };
    socket.onerror = () => {
      if (this.isCurrent(socket, generation)) {
        this.setState('reconnecting');
      }
    };
    socket.onclose = (event: CloseEvent) => {
      if (!this.isCurrent(socket, generation)) {
        return;
      }
      this.socket = undefined;
      this.clearStableTimer();
      this.clearStaleTimer();
      if (this.shouldReconnect && this.isRetryableClose(event.code)) {
        this.scheduleReconnect();
      } else {
        this.setState('closed');
      }
    };
  }

  private flushPendingCommands(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.pendingCommands.forEach((command) => {
      // A command remains pending until its idempotent acknowledgement arrives,
      // but it must only be written once per socket generation.  Without this
      // guard every newly queued command would resend all earlier commands on
      // the same connection, creating duplicate runs/steers.
      if (command.sentGeneration === this.socketGeneration) {
        return;
      }
      this.sendEnvelope(command.type, command.payload, false, command.message_id);
      command.sentGeneration = this.socketGeneration;
      if (command.ackTimer !== undefined) {
        window.clearTimeout(command.ackTimer);
      }
      command.ackTimer = window.setTimeout(() => {
        if (this.pendingCommands.get(command.message_id) !== command
          || command.sentGeneration !== this.socketGeneration) {
          return;
        }
        this.socket?.close(1013, 'command_ack_timeout');
      }, COMMAND_ACK_TIMEOUT_MS);
    });
  }

  private sendEnvelope(
    type: string,
    payload: JsonObject,
    track = true,
    messageId = this.newMessageId(type.replace('.', '_')),
  ): string {
    const envelope = {
      protocol_version: REALTIME_PROTOCOL_VERSION,
      type,
      message_id: messageId,
      payload,
    };
    if (track) {
      this.pendingCommands.set(messageId, { type, message_id: messageId, payload });
    }
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(envelope));
    }
    return messageId;
  }

  private parseServerMessage(data: unknown): RealtimeServerMessage | null {
    let value: unknown = data;
    if (typeof data === 'string') {
      try {
        value = JSON.parse(data);
      } catch {
        return null;
      }
    }
    if (!isRecord(value)
      || value.protocol_version !== REALTIME_PROTOCOL_VERSION
      || typeof value.type !== 'string'
      || typeof value.conversation_id !== 'string'
      || !isRecord(value.payload)
      || (value.message_id !== undefined && value.message_id !== null && typeof value.message_id !== 'string')
      || (value.correlation_id !== undefined && value.correlation_id !== null && typeof value.correlation_id !== 'string')) {
      return null;
    }
    if (this.conversationId && value.conversation_id !== this.conversationId) {
      return null;
    }
    return value as unknown as RealtimeServerMessage;
  }

  private buildSocketUrl(conversationId: string): string {
    const base = new URL(API_BASE_URL, window.location.href);
    base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
    base.pathname = `${base.pathname.replace(/\/$/, '')}${API_CONVERSATION_REALTIME_PATH(conversationId)}`;
    base.search = '';
    return base.toString();
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect || this.reconnectTimer !== undefined) {
      return;
    }
    const ceiling = Math.min(
      RECONNECT_CAP_MS,
      RECONNECT_BASE_MS * (2 ** Math.min(this.reconnectAttempts, 10)),
    );
    const delay = Math.floor(Math.random() * (ceiling + 1));
    this.reconnectAttempts += 1;
    this.setState('reconnecting');
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = undefined;
      if (this.shouldReconnect) {
        this.openSocket();
      }
    }, delay);
  }

  private startStableTimer(): void {
    this.clearStableTimer();
    this.stableTimer = window.setTimeout(() => {
      this.reconnectAttempts = 0;
      this.stableTimer = undefined;
    }, STABLE_CONNECTION_RESET_MS);
  }

  private startStaleTimer(): void {
    this.clearStaleTimer();
    this.staleTimer = window.setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN && Date.now() - this.lastIncomingAt > HEARTBEAT_STALE_MS) {
        this.socket.close(4408, 'heartbeat_timeout');
      }
    }, 5_000);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== undefined) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }
  }

  private clearStableTimer(): void {
    if (this.stableTimer !== undefined) {
      window.clearTimeout(this.stableTimer);
      this.stableTimer = undefined;
    }
  }

  private clearStaleTimer(): void {
    if (this.staleTimer !== undefined) {
      window.clearInterval(this.staleTimer);
      this.staleTimer = undefined;
    }
  }

  private clearPendingCommandTimers(): void {
    this.pendingCommands.forEach((command) => {
      if (command.ackTimer !== undefined) {
        window.clearTimeout(command.ackTimer);
      }
    });
  }

  private isCurrent(socket: WebSocket, generation: number): boolean {
    return this.socket === socket && this.socketGeneration === generation;
  }

  private isRetryableClose(code: number): boolean {
    return ![1000, 1002, 1008, 1009, 4404].includes(code);
  }

  private setState(state: RealtimeConnectionState): void {
    if (this.state === state) {
      return;
    }
    this.state = state;
    this.stateHandlers.forEach((handler) => handler(state));
  }

  private newMessageId(prefix: string): string {
    const random = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
    return `client_${prefix}_${random}`;
  }
}
