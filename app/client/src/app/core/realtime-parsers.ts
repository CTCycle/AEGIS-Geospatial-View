import { REALTIME_PROTOCOL_VERSION } from './constants';
import { normalizeConversationTaskSnapshot, normalizeMapSession, parseContextUsage } from './api-parsers';
import { isFiniteNumber, isJsonObject, isRecord, isStringArray } from './type-guards';
import type {
  ChatOperationResult,
  ContextUsage,
  ConversationTaskSnapshot,
  JsonObject,
  JsonValue,
  MapSession,
  PolicyDecision,
  RealtimeServerMessage,
  RunEvent,
  RunEventType,
  RunEventVisibility,
} from './types';

const RUN_EVENT_TYPES: readonly RunEventType[] = [
  'progress',
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
];

const RUN_EVENT_VISIBILITIES: readonly RunEventVisibility[] = ['user', 'internal'];
const OPERATION_KINDS: readonly ChatOperationResult['kind'][] = [
  'map_session',
  'direct_answer',
  'capability_catalog',
  'clarification',
  'rejection',
  'error',
  'failure_diagnostic',
];
const OPERATION_STATUSES: readonly ChatOperationResult['status'][] = [
  'success',
  'partial',
  'failed',
];
const POLICY_PLAN_STATES: readonly PolicyDecision['plan']['state'][] = [
  'clarify',
  'direct_tool',
  'map_search',
  'reject',
];

export interface ParsedRunCompletionPayload {
  contextRevision?: number;
  mapSession?: MapSession | null;
  operation?: ChatOperationResult | null;
  decision?: PolicyDecision;
  memorySnapshot?: Record<string, JsonValue>;
  contextUsage?: ContextUsage | null;
  taskSnapshot?: ConversationTaskSnapshot;
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

const isOperationKind = (value: unknown): value is ChatOperationResult['kind'] =>
  typeof value === 'string' && OPERATION_KINDS.includes(value as ChatOperationResult['kind']);

const isOperationStatus = (value: unknown): value is ChatOperationResult['status'] =>
  typeof value === 'string' && OPERATION_STATUSES.includes(value as ChatOperationResult['status']);

const isPolicyPlanState = (value: unknown): value is PolicyDecision['plan']['state'] =>
  typeof value === 'string' && POLICY_PLAN_STATES.includes(value as PolicyDecision['plan']['state']);

const parseProviderError = (
  value: unknown,
): NonNullable<ChatOperationResult['provider_error']> | undefined => {
  if (!isJsonObject(value)) {
    return undefined;
  }

  const code = value['code'];
  if (!isNonEmptyString(code) && !isNonEmptyString(String(value['category'] ?? ''))) {
    return undefined;
  }
  return value as NonNullable<ChatOperationResult['provider_error']>;
};

const parseOperation = (value: unknown): ChatOperationResult | undefined => {
  if (!isJsonObject(value)) {
    return undefined;
  }

  const kind = value['kind'];
  const status = value['status'];
  const message = value['message'];
  const warnings = value['warnings'];

  if (
    !isOperationKind(kind) ||
    !isOperationStatus(status) ||
    !isNonEmptyString(message) ||
    (warnings !== undefined && !isStringArray(warnings))
  ) {
    return undefined;
  }

  const result: ChatOperationResult = {
    kind,
    status,
    message,
    direct_result: null,
    provider_error: null,
  };

  if (warnings !== undefined) {
    result.warnings = warnings;
  }

  if (hasOwn(value, 'direct_result')) {
    result.direct_result = value['direct_result'] === null || isJsonObject(value['direct_result'])
      ? value['direct_result']
      : null;
  }

  if (hasOwn(value, 'provider_error')) {
    result.provider_error = value['provider_error'] === null
      ? null
      : parseProviderError(value['provider_error']) ?? null;
  }

  const category = value['failure_category'];
  if (category === 'model_capability' || category === 'provider_api' || category === 'schema_definition'
    || category === 'response_parsing' || category === 'context_limit') {
    result.failure_category = category;
  }

  return result;
};

const parseResolvedLocation = (value: unknown): NonNullable<PolicyDecision['resolved_location']> | undefined => {
  if (!isJsonObject(value)) {
    return undefined;
  }

  const label = value['label'];
  const latitude = value['latitude'];
  const longitude = value['longitude'];
  if (!isNonEmptyString(label) || !isFiniteNumber(latitude) || !isFiniteNumber(longitude)) {
    return undefined;
  }

  return { label, latitude, longitude };
};

const parsePolicyDecision = (value: unknown): PolicyDecision | undefined => {
  if (!isJsonObject(value) || !isJsonObject(value['plan'])) {
    return undefined;
  }

  const planValue = value['plan'];
  const state = planValue['state'];
  const actionId = planValue['action_id'];
  const overlayIds = planValue['overlay_ids'];
  if (!isPolicyPlanState(state) || !isNonEmptyString(actionId) || !isStringArray(overlayIds)) {
    return undefined;
  }

  const plan: PolicyDecision['plan'] = {
    state,
    action_id: actionId,
    overlay_ids: overlayIds,
  };

  if (planValue['mode'] === null || planValue['mode'] === 'direct_text' || planValue['mode'] === 'map') {
    plan.mode = planValue['mode'];
  }
  if (planValue['basemap_id'] === null || isNonEmptyString(planValue['basemap_id'])) {
    plan.basemap_id = planValue['basemap_id'];
  }
  if (planValue['tool_id'] === null || isNonEmptyString(planValue['tool_id'])) {
    plan.tool_id = planValue['tool_id'];
  }

  const decision: PolicyDecision = { plan };

  if (value['clarification'] === null) {
    decision.clarification = null;
  } else if (isJsonObject(value['clarification'])) {
    const question = value['clarification']['question'];
    const reason = value['clarification']['reason'];
    const missingFields = value['clarification']['missing_fields'];
    if (isNonEmptyString(question) && isNonEmptyString(reason) && isStringArray(missingFields)) {
      decision.clarification = { question, reason, missing_fields: missingFields };
    }
  }

  if (value['resolved_location'] === null) {
    decision.resolved_location = null;
  } else if (hasOwn(value, 'resolved_location')) {
    const resolvedLocation = parseResolvedLocation(value['resolved_location']);
    if (resolvedLocation) {
      decision.resolved_location = resolvedLocation;
    }
  }

  if (isStringArray(value['trace'])) {
    decision.trace = { steps: value['trace'] };
  }

  return decision;
};

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
    parsed.operation = value['operation'] === null ? null : parseOperation(value['operation']);
  }

  if (hasOwn(value, 'decision')) {
    parsed.decision = parsePolicyDecision(value['decision']);
  }

  if (hasOwn(value, 'memory_snapshot') && isJsonObject(value['memory_snapshot'])) {
    parsed.memorySnapshot = value['memory_snapshot'];
  }

  if (hasOwn(value, 'context_usage')) {
    parsed.contextUsage = value['context_usage'] === null
      ? null
      : parseContextUsage(value['context_usage']) ?? undefined;
  }

  if (hasOwn(value, 'task_snapshot')) {
    parsed.taskSnapshot = normalizeConversationTaskSnapshot(value['task_snapshot']);
  }

  return parsed;
};
