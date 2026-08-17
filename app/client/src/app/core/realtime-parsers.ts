import { REALTIME_PROTOCOL_VERSION } from './constants';
import { normalizeMapSession, parseContextUsage } from './api-parsers';
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
const TASK_STATUSES: readonly ConversationTaskSnapshot['tasks'][number]['status'][] = [
  'pending',
  'needs_clarification',
  'routed',
  'in_progress',
  'completed',
  'failed',
  'skipped',
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

const isTaskStatus = (
  value: unknown,
): value is ConversationTaskSnapshot['tasks'][number]['status'] =>
  typeof value === 'string' && TASK_STATUSES.includes(value as ConversationTaskSnapshot['tasks'][number]['status']);

const parseProviderError = (
  value: unknown,
): NonNullable<ChatOperationResult['provider_error']> | undefined => {
  if (!isJsonObject(value)) {
    return undefined;
  }

  const code = value['code'];
  const provider = value['provider'];
  const model = value['model'];
  const stage = value['stage'];
  const retryable = value['retryable'];
  const httpStatus = value['http_status'];

  if (
    !isNonEmptyString(code) ||
    !isNonEmptyString(provider) ||
    !isNonEmptyString(model) ||
    !isNonEmptyString(stage) ||
    typeof retryable !== 'boolean' ||
    (httpStatus !== undefined && httpStatus !== null && !isFiniteNumber(httpStatus))
  ) {
    return undefined;
  }

  return {
    code,
    provider,
    model,
    stage,
    retryable,
    http_status: httpStatus,
  };
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
    map_session: null,
    direct_result: null,
    provider_error: null,
  };

  if (warnings !== undefined) {
    result.warnings = warnings;
  }

  if (hasOwn(value, 'map_session')) {
    result.map_session = value['map_session'] === null ? null : normalizeMapSession(value['map_session']);
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

const parseTaskFailure = (value: unknown): NonNullable<ConversationTaskSnapshot['tasks'][number]['failure']> | undefined => {
  if (!isJsonObject(value)) {
    return undefined;
  }

  const stage = value['stage'];
  const sanitizedError = value['sanitized_error'];
  const missingInput = value['missing_input'];
  const partialResultsAvailable = value['partial_results_available'];
  const userExplanation = value['user_explanation'];
  if (
    !isNonEmptyString(stage) ||
    !isNonEmptyString(sanitizedError) ||
    !isStringArray(missingInput) ||
    typeof partialResultsAvailable !== 'boolean' ||
    !isNonEmptyString(userExplanation)
  ) {
    return undefined;
  }

  const failure: NonNullable<ConversationTaskSnapshot['tasks'][number]['failure']> = {
    stage,
    sanitized_error: sanitizedError,
    missing_input: missingInput,
    partial_results_available: partialResultsAvailable,
    user_explanation: userExplanation,
  };

  if (value['component'] === null || isNonEmptyString(value['component'])) {
    failure.component = value['component'];
  }
  if (value['tool_name'] === null || isNonEmptyString(value['tool_name'])) {
    failure.tool_name = value['tool_name'];
  }
  if (value['unsupported_capability'] === null || isNonEmptyString(value['unsupported_capability'])) {
    failure.unsupported_capability = value['unsupported_capability'];
  }
  if (value['recovery_suggestion'] === null || isNonEmptyString(value['recovery_suggestion'])) {
    failure.recovery_suggestion = value['recovery_suggestion'];
  }
  if (value['provider_error'] === null) {
    failure.provider_error = null;
  } else if (hasOwn(value, 'provider_error')) {
    const providerError = parseProviderError(value['provider_error']);
    if (!providerError) {
      return undefined;
    }
    failure.provider_error = providerError;
  }

  return failure;
};

const parseTaskSnapshot = (value: unknown): ConversationTaskSnapshot | undefined => {
  if (!isJsonObject(value) || !isNonEmptyString(value['conversation_key']) || !Array.isArray(value['tasks'])) {
    return undefined;
  }

  const tasks: ConversationTaskSnapshot['tasks'] = [];
  for (const item of value['tasks']) {
    if (!isJsonObject(item)) {
      return undefined;
    }

    const requiredEntities = item['required_entities'];
    const requiredDataLayers = item['required_data_layers'];
    const visualizationChanges = item['visualization_changes'];
    if (
      !isNonEmptyString(item['task_id']) ||
      !isNonEmptyString(item['raw_user_text']) ||
      !isNonEmptyString(item['prompt_summary']) ||
      !isNonEmptyString(item['normalized_description']) ||
      !isNonEmptyString(item['task_type']) ||
      !isNonEmptyString(item['intent']) ||
      !isNonEmptyString(item['relationship']) ||
      !isStringArray(requiredEntities) ||
      !isStringArray(requiredDataLayers) ||
      !isJsonObject(visualizationChanges) ||
      !isNonEmptyString(item['specialist']) ||
      !isTaskStatus(item['status']) ||
      typeof item['is_current'] !== 'boolean'
    ) {
      return undefined;
    }

    const task: ConversationTaskSnapshot['tasks'][number] = {
      task_id: item['task_id'],
      raw_user_text: item['raw_user_text'],
      prompt_summary: item['prompt_summary'],
      normalized_description: item['normalized_description'],
      task_type: item['task_type'],
      intent: item['intent'],
      relationship: item['relationship'],
      required_entities: requiredEntities,
      required_data_layers: requiredDataLayers,
      visualization_changes: visualizationChanges,
      specialist: item['specialist'],
      status: item['status'],
      is_current: item['is_current'],
    };

    if (item['parent_task_id'] === null || isNonEmptyString(item['parent_task_id'])) {
      task.parent_task_id = item['parent_task_id'];
    }
    if (item['blocking_ambiguity'] === null || isNonEmptyString(item['blocking_ambiguity'])) {
      task.blocking_ambiguity = item['blocking_ambiguity'];
    }
    if (item['progress_summary'] === null || isNonEmptyString(item['progress_summary'])) {
      task.progress_summary = item['progress_summary'];
    }
    if (item['failure'] === null) {
      task.failure = null;
    } else if (hasOwn(item, 'failure')) {
      const failure = parseTaskFailure(item['failure']);
      if (!failure) {
        return undefined;
      }
      task.failure = failure;
    }

    tasks.push(task);
  }

  const snapshot: ConversationTaskSnapshot = {
    conversation_key: value['conversation_key'],
    tasks,
  };

  if (value['current_task_id'] === null || isNonEmptyString(value['current_task_id'])) {
    snapshot.current_task_id = value['current_task_id'];
  }

  if (value['active_visualization'] === null || isJsonObject(value['active_visualization'])) {
    snapshot.active_visualization = value['active_visualization'];
  }

  return snapshot;
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
    parsed.taskSnapshot = parseTaskSnapshot(value['task_snapshot']);
  }

  return parsed;
};
