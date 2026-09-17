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
  parseAgentTaskState,
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
  RenderObservation,
  RunEvent,
  RunEventType,
  RunEventVisibility,
  ToolProgressItem,
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
  'render_observed',
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
  taskState?: import('./types').AgentTaskState | null;
}

const optionalText = (value: unknown, maxLength = 800): string | undefined => (
  typeof value === 'string' && value.trim() ? value.trim().slice(0, maxLength) : undefined
);

const optionalNumber = (value: unknown): number | undefined => (
  isFiniteNumber(value) && value >= 0 ? value : undefined
);

/**
 * Normalize user-visible tool progress without passing arbitrary provider
 * payloads to the template.  Full observations remain server-owned.
 */
export const parseToolProgressPayload = (
  value: unknown,
  eventType: 'tool_started' | 'tool_completed' = 'tool_completed',
): ToolProgressItem | undefined => {
  if (!isJsonObject(value)) {
    return undefined;
  }
  const callId = optionalText(value['call_id'] ?? value['tool_call_id'], 160);
  const toolName = optionalText(value['tool_name'] ?? value['tool'], 160);
  if (!callId || !toolName) {
    return undefined;
  }
  const rawStatus = optionalText(value['status'], 64);
  const allowedStatuses = ['running', 'success', 'valid_empty', 'partial', 'failed'] as const;
  const status = eventType === 'tool_started'
    ? 'running'
    : allowedStatuses.includes(rawStatus as typeof allowedStatuses[number])
      ? rawStatus as ToolProgressItem['status']
      : 'success';
  const refs = value['evidence_refs'];
  const evidenceRefs = Array.isArray(refs)
    ? refs.filter((item): item is string => typeof item === 'string').slice(0, 32)
    : undefined;
  const rawError = value['error'];
  const error = typeof rawError === 'string'
    ? optionalText(rawError)
    : isJsonObject(rawError) ? optionalText(rawError['message'] ?? rawError['detail']) : undefined;
  const iteration = optionalNumber(value['iteration'] ?? value['current_iteration']);
  return {
    call_id: callId,
    tool_name: toolName,
    status,
    label: optionalText(value['label'], 240),
    task_id: optionalText(value['task_id'] ?? value['active_task_id'], 160) ?? null,
    iteration: iteration ?? null,
    summary: optionalText(value['summary'] ?? value['message']),
    duration_ms: optionalNumber(value['duration_ms'] ?? value['duration']) ?? null,
    evidence_refs: evidenceRefs,
    error: error ?? null,
    started_at: optionalText(value['started_at'] ?? value['timestamp'], 80),
    completed_at: eventType === 'tool_completed'
      ? optionalText(value['completed_at'] ?? value['timestamp'], 80)
      : undefined,
  };
};

/** Normalize bounded browser evidence without exposing arbitrary payloads. */
export const parseRenderObservationPayload = (
  value: unknown,
): RenderObservation | undefined => {
  if (!isJsonObject(value)) {
    return undefined;
  }
  const mapSessionId = optionalText(value['map_session_id'], 160);
  const collectionRevision = value['collection_revision'];
  const attempt = value['attempt'];
  const status = value['status'];
  const recovery = value['recovery'];
  if (!mapSessionId
    || !isFiniteNumber(collectionRevision)
    || !Number.isInteger(collectionRevision)
    || collectionRevision < 0
    || !isFiniteNumber(attempt)
    || !Number.isInteger(attempt)
    || attempt < 1
    || (status !== 'ready' && status !== 'failed')
    || !['continue', 'revise_map', 'alternate_source', 'terminal'].includes(String(recovery))) {
    return undefined;
  }

  const rawChecks = value['checks'];
  if (!isJsonObject(rawChecks)) {
    return undefined;
  }
  const checks: Record<string, boolean> = {};
  for (const [key, item] of Object.entries(rawChecks).slice(0, 32)) {
    if (typeof item !== 'boolean') {
      return undefined;
    }
    checks[key.slice(0, 160)] = item;
  }

  const rawOverlayResults = value['overlay_results'];
  if (!Array.isArray(rawOverlayResults)) {
    return undefined;
  }
  const overlayResults = rawOverlayResults
    .filter(isJsonObject)
    .slice(0, 64);
  if (overlayResults.length !== Math.min(rawOverlayResults.length, 64)) {
    return undefined;
  }

  const rawViewport = value['viewport_bounds'];
  let viewportBounds: [number, number, number, number] | null | undefined;
  if (rawViewport === null) {
    viewportBounds = null;
  } else if (rawViewport === undefined) {
    viewportBounds = undefined;
  } else if (Array.isArray(rawViewport)
    && rawViewport.length === 4
    && rawViewport.every(isFiniteNumber)) {
    viewportBounds = rawViewport as [number, number, number, number];
  } else {
    return undefined;
  }

  return {
    map_session_id: mapSessionId,
    collection_revision: collectionRevision,
    attempt,
    status,
    viewport_bounds: viewportBounds,
    checks,
    overlay_results: overlayResults,
    failure_code: optionalText(value['failure_code'], 120) ?? null,
    failure_stage: optionalText(value['failure_stage'], 120) ?? null,
    failure_summary: optionalText(value['failure_summary'], 500) ?? null,
    fingerprint: optionalText(value['fingerprint'], 64) ?? null,
    action_fingerprint: optionalText(value['action_fingerprint'], 64) ?? null,
    recovery: recovery as RenderObservation['recovery'],
    observed_at: optionalText(value['observed_at'], 64) ?? null,
  };
};

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
  'not_required',
  'not_requested',
  'pending',
  'prepared',
  'prepared_unverified',
  'ready',
  'failed',
  'render_timeout',
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

  if (hasOwn(value, 'task_state')) {
    parsed.taskState = value['task_state'] === null
      ? null
      : parseAgentTaskState(value['task_state'], 'realtime completion') ?? undefined;
  }

  return parsed;
};
