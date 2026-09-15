import { REALTIME_PROTOCOL_VERSION } from './constants';
import {
  normalizeMapSession,
  parseChatOperation,
  parseCompletionContract,
  parseContextUsage,
  parseConversationState,
  parseNativeGoal,
  parseNativeRoute,
  parseNativeToolResult,
} from './api-parsers';
import { isFiniteNumber, isJsonObject } from './type-guards';
import type {
  ChatOperationResult,
  AgentGoal,
  CompletionContract,
  ContextUsage,
  ConversationState,
  JsonObject,
  JsonValue,
  MapSession,
  NativeCapabilityRoute,
  NativeToolResultSummary,
  PresentationStatus,
  RealtimeServerMessage,
  RunEvent,
  RunEventType,
  RunEventVisibility,
} from './types';

const RUN_EVENT_TYPES: readonly RunEventType[] = [
  'progress',
  'context_usage',
  'assistant_text_delta',
  'assistant_text_completed',
  'tool_started',
  'tool_completed',
  'request_updated',
  'error',
  'completed',
  'cancelled',
  'clarification_needed',
  'trace',
  'checkpoint',
  'map_prepared',
];

const RUN_EVENT_VISIBILITIES: readonly RunEventVisibility[] = ['user', 'internal'];
export interface ParsedRunCompletionPayload {
  contextRevision?: number;
  mapSession?: MapSession | null;
  operation?: ChatOperationResult | null;
  goal?: AgentGoal | null;
  completionContract?: CompletionContract | null;
  conversationState?: ConversationState | null;
  memorySnapshot?: Record<string, JsonValue>;
  contextUsage?: ContextUsage | null;
  route?: NativeCapabilityRoute | null;
  presentationStatus?: PresentationStatus;
  toolResults?: NativeToolResultSummary[];
  executionTrace?: Record<string, JsonValue> | null;
}

const hasOwn = (value: JsonObject, key: string): boolean =>
  Object.prototype.hasOwnProperty.call(value, key);

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0;

const isFiniteInteger = (value: unknown): value is number =>
  isFiniteNumber(value) && Number.isInteger(value) && value >= 0;

const isRunEventType = (value: unknown): value is RunEventType =>
  typeof value === 'string' && RUN_EVENT_TYPES.includes(value as RunEventType);

const isRunEventVisibility = (value: unknown): value is RunEventVisibility =>
  typeof value === 'string' && RUN_EVENT_VISIBILITIES.includes(value as RunEventVisibility);

const NATIVE_PRESENTATION_STATUSES: readonly PresentationStatus[] = [
  'not_requested',
  'prepared',
  'prepared_unverified',
  'ready',
  'failed',
];

export const parseRealtimeServerMessage = (
  data: unknown,
  expectedConversationId?: string,
): RealtimeServerMessage | null => {
  let value: unknown = data;
  if (typeof data === 'string') {
    try {
      value = JSON.parse(data) as unknown;
    } catch {
      return null;
    }
  }

  if (
    !isJsonObject(value) ||
    value['protocol_version'] !== REALTIME_PROTOCOL_VERSION ||
    !isNonEmptyString(value['type']) ||
    !isNonEmptyString(value['conversation_id']) ||
    !isJsonObject(value['payload']) ||
    (value['message_id'] !== undefined && value['message_id'] !== null && !isNonEmptyString(value['message_id'])) ||
    (value['correlation_id'] !== undefined && value['correlation_id'] !== null && !isNonEmptyString(value['correlation_id']))
  ) {
    return null;
  }

  if (expectedConversationId && value['conversation_id'] !== expectedConversationId) {
    return null;
  }

  return {
    protocol_version: REALTIME_PROTOCOL_VERSION,
    type: value['type'],
    message_id: value['message_id'] === null ? null : value['message_id'],
    correlation_id: value['correlation_id'] === null ? null : value['correlation_id'],
    conversation_id: value['conversation_id'],
    payload: value['payload'],
  };
};

export const parseRunEvent = (
  value: unknown,
  expectedConversationId?: string,
): RunEvent | undefined => {
  if (
    !isJsonObject(value) ||
    !isNonEmptyString(value['event_id']) ||
    !isFiniteInteger(value['sequence']) ||
    !isNonEmptyString(value['conversation_id']) ||
    !isNonEmptyString(value['run_id']) ||
    !isFiniteInteger(value['run_version']) ||
    !isRunEventType(value['type']) ||
    !isNonEmptyString(value['timestamp']) ||
    !isRunEventVisibility(value['visibility']) ||
    !isJsonObject(value['payload'])
  ) {
    return undefined;
  }

  if (expectedConversationId && value['conversation_id'] !== expectedConversationId) {
    return undefined;
  }

  return {
    event_id: value['event_id'],
    sequence: value['sequence'],
    conversation_id: value['conversation_id'],
    run_id: value['run_id'],
    run_version: value['run_version'],
    type: value['type'],
    timestamp: value['timestamp'],
    visibility: value['visibility'],
    payload: value['payload'],
  };
};

export const parseRunCompletionPayload = (value: unknown): ParsedRunCompletionPayload => {
  if (!isJsonObject(value)) {
    return {};
  }

  const parsed: ParsedRunCompletionPayload = {};

  if (isFiniteNumber(value['context_revision'])) {
    parsed.contextRevision = value['context_revision'];
  }

  if (hasOwn(value, 'map_session')) {
    parsed.mapSession = value['map_session'] === null ? null : normalizeMapSession(value['map_session']) ?? undefined;
  }

  if (hasOwn(value, 'operation')) {
    parsed.operation = value['operation'] === null
      ? null
      : parseChatOperation(value['operation'], 'realtime completion');
  }

  if (hasOwn(value, 'goal')) {
    parsed.goal = value['goal'] === null
      ? null
      : parseNativeGoal(value['goal'], 'realtime completion');
  }

  if (hasOwn(value, 'completion_contract')) {
    parsed.completionContract = value['completion_contract'] === null
      ? null
      : parseCompletionContract(value['completion_contract'], 'realtime completion');
  }

  if (hasOwn(value, 'conversation_state')) {
    parsed.conversationState = value['conversation_state'] === null
      ? null
      : parseConversationState(value['conversation_state'], 'realtime completion');
  }

  if (hasOwn(value, 'memory_snapshot') && isJsonObject(value['memory_snapshot'])) {
    parsed.memorySnapshot = value['memory_snapshot'];
  }

  if (hasOwn(value, 'context_usage')) {
    parsed.contextUsage = value['context_usage'] === null
      ? null
      : parseContextUsage(value['context_usage']) ?? undefined;
  }

  if (hasOwn(value, 'route')) {
    if (value['route'] === null) {
      parsed.route = null;
    } else {
      try {
        parsed.route = parseNativeRoute(value['route'], 'realtime completion');
      } catch {
        parsed.route = undefined;
      }
    }
  }

  const presentationStatus = value['presentation_status'];
  if (typeof presentationStatus === 'string'
    && NATIVE_PRESENTATION_STATUSES.includes(presentationStatus as PresentationStatus)) {
    parsed.presentationStatus = presentationStatus as PresentationStatus;
  }

  if (Array.isArray(value['tool_results'])) {
    const results: NativeToolResultSummary[] = [];
    try {
      value['tool_results'].forEach((item, index) => {
        results.push(parseNativeToolResult(item, 'realtime completion', index));
      });
      parsed.toolResults = results;
    } catch {
      parsed.toolResults = undefined;
    }
  }

  if (value['execution_trace'] === null) {
    parsed.executionTrace = null;
  } else if (isJsonObject(value['execution_trace'])) {
    parsed.executionTrace = value['execution_trace'];
  }

  return parsed;
};
