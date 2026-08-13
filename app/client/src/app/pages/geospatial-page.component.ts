import { CommonModule } from '@angular/common';
import { AfterViewInit, ChangeDetectionStrategy, ChangeDetectorRef, Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { Router } from '@angular/router';

import {
  CapabilityStatusItem,
  CapabilityStatusListComponent,
  CapabilityStatusTone,
} from '../components/capability-status-list.component';
import { ChatMessageComponent } from '../components/chat-message.component';
import { MapPreviewComponent, MapRenderStateChange } from '../components/map-preview.component';
import {
  AgentReadinessService,
  AgentReadinessState,
  INITIAL_AGENT_READINESS_STATE,
} from '../core/agent-readiness.service';
import { ApiClientService } from '../core/api-client.service';
import { AppStateStoreService } from '../core/app-state-store.service';
import { LocalCommandService } from '../core/local-command.service';
import { normalizeMapSession } from '../core/api-parsers';
import { PersistedChatPageState } from '../core/app-state';
import { MAX_CHAT_MESSAGE_LENGTH } from '../core/constants';
import { RealtimeService } from '../core/realtime.service';
import {
  ChatOperationResult,
  MapSession,
  OverlayStateChange,
  SearchResponsePayload,
  ChatMessage,
  ChatRole,
  ChatTurnResponse,
  ContextUsage,
  ConversationTaskSnapshot,
  RealtimeServerMessage,
  RunEvent,
} from '../core/types';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { ViewStateSyncService } from '../core/view-state-sync.service';

@Component({
  selector: 'app-geospatial-page',
  standalone: true,
  imports: [CommonModule, CapabilityStatusListComponent, ChatMessageComponent, MapPreviewComponent],
  templateUrl: './geospatial-page.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './geospatial-page.component.css',
})
export class GeospatialPageComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('transcript', { static: false }) transcriptRef?: ElementRef<HTMLDivElement>;
  @ViewChild(MapPreviewComponent) mapPreview?: MapPreviewComponent;

  readonly maxChatMessageLength = MAX_CHAT_MESSAGE_LENGTH;

  payload?: SearchResponsePayload;
  toolbarWidthState = 480;
  isToolbarCollapsed = false;
  mapState = { overlayVisibility: {}, overlayOpacity: {} } as PersistedChatPageState['mapState'];

  conversationId?: string;
  contextRevision?: number;
  taskSnapshot?: ConversationTaskSnapshot;
  activeRunId?: string;
  activeRunVersion?: number;
  lastRunEventId?: string;
  streamState: PersistedChatPageState['chatPanel']['streamState'] = 'idle';
  progressStage?: string;
  progressLabel?: string;
  conversationNonce = 1;
  messages: ChatMessage[] = [];
  lastDecision?: ChatTurnResponse['decision'];
  lastOperation?: ChatOperationResult | null;
  memorySnapshot: Record<string, unknown> = {};
  contextUsage?: ContextUsage;
  mapSession?: MapSession;
  status = 'Agent ready';
  composerError = '';
  assistantDraft = '';
  composerDraft = '';
  transcriptScrollTop = 0;
  agentReadiness = INITIAL_AGENT_READINESS_STATE;

  isLoading = false;
  progressPercent = 0;
  isResizing = false;
  isAlertsOpen = false;

  private readonly minWidth = 280;
  private readonly maxWidth = 760;
  private readonly canvasMinWidth = 320;
  private readonly maxSeenEventIds = 512;
  private readonly chatPageState: PersistedChatPageState;
  private mouseMoveHandler?: (event: MouseEvent) => void;
  private mouseUpHandler?: () => void;
  private seenEventIds = new Set<string>();
  private steeringMutationCounter = 0;
  private isDestroyed = false;
  private pendingMapSession?: MapSession;
  private lastRunSequence = 0;
  private pendingRun?: PersistedChatPageState['chatPanel']['pendingRun'];
  private removeRealtimeMessageListener?: () => void;
  private removeRealtimeStateListener?: () => void;

  constructor(
    private readonly router: Router,
    private readonly apiClient: ApiClientService,
    private readonly realtimeService: RealtimeService,
    private readonly appStateStore: AppStateStoreService,
    private readonly localCommandService: LocalCommandService,
    private readonly agentReadinessService: AgentReadinessService,
    private readonly userFacingErrorService: UserFacingErrorService,
    private readonly viewStateSync: ViewStateSyncService,
    private readonly changeDetectorRef: ChangeDetectorRef,
  ) {
    this.chatPageState = this.appStateStore.getChatPage();
    this.payload = this.chatPageState.payload;
    this.toolbarWidthState = this.chatPageState.toolbarWidth;
    this.isToolbarCollapsed = this.chatPageState.isToolbarCollapsed;
    this.mapState = this.chatPageState.mapState;

    this.conversationId = this.chatPageState.chatPanel.conversationId;
    this.contextRevision = this.chatPageState.chatPanel.contextRevision;
    this.taskSnapshot = this.chatPageState.chatPanel.taskSnapshot;
    this.activeRunId = this.chatPageState.chatPanel.activeRunId;
    this.activeRunVersion = this.chatPageState.chatPanel.activeRunVersion;
    this.pendingRun = this.chatPageState.chatPanel.pendingRun;
    this.lastRunEventId = this.chatPageState.chatPanel.lastRunEventId;
    this.lastRunSequence = this.chatPageState.chatPanel.lastRunSequence ?? 0;
    this.streamState = this.chatPageState.chatPanel.streamState ?? 'idle';
    this.progressStage = this.chatPageState.chatPanel.progressStage;
    this.progressLabel = this.chatPageState.chatPanel.progressLabel;
    this.seenEventIds = new Set(this.chatPageState.chatPanel.seenRunEventIds ?? []);
    this.conversationNonce = this.chatPageState.chatPanel.conversationNonce;
    this.messages = this.chatPageState.chatPanel.messages;
    this.lastDecision = this.chatPageState.chatPanel.lastDecision;
    this.lastOperation = this.chatPageState.chatPanel.lastOperation;
    this.memorySnapshot = this.chatPageState.chatPanel.memorySnapshot ?? {};
    this.contextUsage = this.chatPageState.chatPanel.contextUsage;
    this.mapSession = this.chatPageState.chatPanel.mapSession;
    this.status = this.chatPageState.chatPanel.status;
    this.assistantDraft = this.chatPageState.chatPanel.assistantDraft;
    this.composerDraft = this.chatPageState.chatPanel.composerDraft;
    this.transcriptScrollTop = this.chatPageState.chatPanel.transcriptScrollTop;
  }

  ngOnInit(): void {
    this.removeRealtimeMessageListener = this.realtimeService.onMessage((message) => {
      this.handleRealtimeMessage(message);
    });
    this.removeRealtimeStateListener = this.realtimeService.onStateChange((state) => {
      this.streamState = state;
      this.syncState();
      this.changeDetectorRef.detectChanges();
    });
    if (this.conversationId) {
      this.realtimeService.connect(this.conversationId, {
        runId: this.activeRunId,
        afterSequence: this.lastRunSequence,
      });
      // If a page reload happened after conversation creation but before the
      // start acknowledgement, replay the same idempotent command.  The
      // server's client_request_id prevents an orphaned run or duplicate run.
      if (!this.activeRunId && this.pendingRun) {
        this.realtimeService.sendRunStart(
          this.pendingRun.message,
          this.pendingRun.clientRequestId,
        );
      }
    }
    void this.loadAgentStatus();
  }

  ngAfterViewInit(): void {
    this.viewStateSync.restoreWindowScroll(this.chatPageState.scrollY);
    this.viewStateSync.restoreElementScroll(this.transcriptRef?.nativeElement, this.transcriptScrollTop);
  }

  ngOnDestroy(): void {
    this.isDestroyed = true;
    this.removeRealtimeMessageListener?.();
    this.removeRealtimeStateListener?.();
    this.realtimeService.disconnect({ discardPending: true });
    this.stopResize();
    this.syncState();
  }

  get toolbarWidth(): number {
    return this.toolbarWidthState;
  }

  get renderedMessages(): ChatMessage[] {
    if (!this.assistantDraft.trim()) {
      return this.messages;
    }
    return [...this.messages, { role: 'assistant' as ChatRole, content: this.assistantDraft }];
  }

  get hasMessages(): boolean {
    return this.renderedMessages.length > 0;
  }

  get activeAlertItems(): string[] {
    const alerts: string[] = [];
    const latestAssistantMessage = [...this.messages].reverse().find((entry) => entry.role === 'assistant')?.content?.trim() ?? '';
    const operationMessage = this.lastOperation?.message?.trim() ?? '';
    if (this.agentReadiness.status !== 'active' && this.agentReadiness.message.trim()) {
      alerts.push(this.agentReadiness.message.trim());
    }
    if (this.status === 'Failed') {
      alerts.push('The last request failed before the map session updated.');
    }
    if (operationMessage && (this.lastOperation?.kind === 'error' || this.lastOperation?.kind === 'rejection')) {
      alerts.push(operationMessage);
    }
    if (latestAssistantMessage && this.looksLikeRuntimeFailure(latestAssistantMessage)) {
      alerts.push(latestAssistantMessage);
    }
    if (!this.payload?.map_session) {
      alerts.push('No active map session is loaded yet.');
    }
    const warnings = this.payload?.compliance_warnings ?? this.payload?.map_session?.compliance_warnings ?? [];
    warnings.forEach((warning) => alerts.push(String(warning)));
    return alerts;
  }

  get alertsSummary(): string {
    const count = this.activeAlertItems.length;
    if (count === 0) {
      return 'No active alerts';
    }
    return `${count} alert${count === 1 ? '' : 's'} active`;
  }

  get showProgressIndicator(): boolean {
    return this.isLoading;
  }

  get capabilityStatusItems(): CapabilityStatusItem[] {
    return [
      {
        label: 'Agent model',
        statusLabel: this.agentReadiness.label,
        tone: this.agentStatusTone,
      },
      { label: 'Satellite Imagery', statusLabel: 'Active', tone: 'ok' },
      { label: 'Weather Intel', statusLabel: 'Active', tone: 'ok' },
      { label: 'Optional Keys', statusLabel: 'Disabled', tone: 'warn' },
    ];
  }

  get contextUsagePercent(): number {
    return Math.max(0, Math.min(100, Math.round(this.contextUsage?.usage_percent ?? 0)));
  }

  get contextUsageLabel(): string {
    if (!this.contextUsage) {
      return '0%';
    }
    return `${this.contextUsagePercent}%`;
  }

  get contextUsageDetail(): string {
    if (!this.contextUsage) {
      return 'Context window awaiting first request';
    }
    const selected = this.contextUsage.selected_context_window ?? this.contextUsage.model_context_limit ?? 0;
    const model = [this.contextUsage.provider, this.contextUsage.model].filter(Boolean).join(' / ');
    return `${this.contextUsage.estimated_input_tokens} / ${selected} tokens${model ? ` - ${model}` : ''}`;
  }

  get contextTrackerText(): string {
    if (!this.contextUsage) {
      return 'Context window';
    }
    const selected = this.contextUsage.selected_context_window ?? this.contextUsage.model_context_limit ?? 0;
    return `${this.contextUsage.estimated_input_tokens} / ${selected}`;
  }

  startNewChat(): void {
    this.realtimeService.disconnect({ discardPending: true });
    this.conversationId = undefined;
    this.contextRevision = undefined;
    this.taskSnapshot = undefined;
    this.activeRunId = undefined;
    this.activeRunVersion = undefined;
    this.pendingRun = undefined;
    this.lastRunEventId = undefined;
    this.lastRunSequence = 0;
    this.streamState = 'idle';
    this.progressStage = undefined;
    this.progressLabel = undefined;
    this.seenEventIds.clear();
    this.conversationNonce += 1;
    this.messages = [];
    this.lastDecision = undefined;
    this.lastOperation = undefined;
    this.memorySnapshot = {};
    this.contextUsage = undefined;
    this.mapSession = undefined;
    this.payload = undefined;
    this.status = 'Agent ready';
    this.isLoading = false;
    this.assistantDraft = '';
    this.composerDraft = '';
    this.transcriptScrollTop = 0;
    this.mapState = { overlayVisibility: {}, overlayOpacity: {} };
    this.progressPercent = 0;
    this.isAlertsOpen = false;
    this.appStateStore.resetChatPage();
    this.syncState();
    queueMicrotask(() => this.scrollTranscriptToBottom());
  }

  toggleAlerts(): void {
    this.isAlertsOpen = !this.isAlertsOpen;
  }

  navigateToSettings(): void {
    this.syncState();
    this.router.navigateByUrl('/settings');
  }

  startResize(): void {
    if (this.isToolbarCollapsed) {
      this.isToolbarCollapsed = false;
    }
    this.isResizing = true;

    this.mouseMoveHandler = (event: MouseEvent) => {
      const viewportWidth = window.innerWidth;
      const maxAllowedByViewport = viewportWidth - this.canvasMinWidth;
      const clamped = this.clampToolbarWidth(Math.min(event.clientX, maxAllowedByViewport));
      this.toolbarWidthState = clamped;
      this.syncState();
    };

    this.mouseUpHandler = () => {
      this.stopResize();
    };

    window.addEventListener('mousemove', this.mouseMoveHandler);
    window.addEventListener('mouseup', this.mouseUpHandler);
  }

  onTranscriptScroll(event: Event): void {
    this.transcriptScrollTop = (event.target as HTMLDivElement).scrollTop;
    this.syncState();
  }

  onComposerChange(value: string): void {
    this.composerDraft = value;
    this.composerError = '';
    this.syncState();
  }

  onComposerInput(event: Event): void {
    const target = event.target as HTMLTextAreaElement | null;
    this.onComposerChange(target?.value ?? '');
  }

  onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void this.sendMessage();
    }
  }

  onOverlayStateChange(state: OverlayStateChange): void {
    this.mapState = state;
    this.syncState();
  }

  async sendMessage(): Promise<void> {
    const trimmed = this.composerDraft.trim();
    if (!trimmed) {
      return;
    }
    if (trimmed.length > MAX_CHAT_MESSAGE_LENGTH) {
      this.composerError = `Message must be ${MAX_CHAT_MESSAGE_LENGTH.toLocaleString()} characters or fewer.`;
      this.status = this.composerError;
      this.syncState();
      this.changeDetectorRef.detectChanges();
      return;
    }

    this.composerError = '';
    const message = trimmed;
    const requestNonce = this.conversationNonce;
    if (await this.tryHandleLocalCommand(message)) {
      return;
    }
    this.composerDraft = '';
    if (this.isLoading && this.conversationId) {
      if (this.activeRunId) {
        await this.sendSteeringMessage(message);
      } else {
        this.composerDraft = message;
        this.syncState();
      }
      return;
    }
    await this.startAgentRun(message, requestNonce);
  }

  private async startAgentRun(message: string, requestNonce: number): Promise<void> {
    this.isLoading = true;
    this.status = 'Understanding the request';
    this.progressStage = 'understanding_request';
    this.progressLabel = 'Understanding the request';
    this.progressPercent = 18;
    this.messages = [...this.messages, { role: 'user', content: message, kind: 'normal' }];
    this.assistantDraft = '';
    this.syncState();

    try {
      const conversation = this.conversationId
        ? { conversation_id: this.conversationId }
        : await this.apiClient.createConversation({ title: message.slice(0, 120) });
      if (requestNonce !== this.conversationNonce) {
        return;
      }
      this.conversationId = conversation.conversation_id;
      this.activeRunId = undefined;
      this.activeRunVersion = undefined;
      const pendingRun = {
        clientRequestId: this.newClientRequestId(),
        message,
      };
      this.pendingRun = pendingRun;
      this.lastRunSequence = 0;
      this.lastRunEventId = undefined;
      this.syncState();
      this.realtimeService.setResumeCursor(undefined, 0);
      this.realtimeService.connect(conversation.conversation_id);
      this.realtimeService.sendRunStart(
        message,
        pendingRun.clientRequestId,
      );
    } catch (error: unknown) {
      const fallback = this.userFacingErrorService.toUserFacingError(
        error,
        'Could not start this request right now.',
      );
      this.status = 'Agent ready';
      this.progressLabel = undefined;
      this.assistantDraft = '';
      this.messages = [...this.messages, { role: 'assistant', content: fallback }];
      this.progressPercent = 0;
      this.isLoading = false;
    } finally {
      this.syncState();
      queueMicrotask(() => this.scrollTranscriptToBottom());
    }
  }

  private async sendSteeringMessage(message: string): Promise<void> {
    if (!this.conversationId || !this.activeRunId) {
      return;
    }
    const clientMutationId = `client_steer_${Date.now()}_${++this.steeringMutationCounter}`;
    this.messages = [
      ...this.messages,
      { role: 'user', content: message, kind: 'steering', runVersion: this.activeRunVersion },
    ];
    this.status = 'Request updated';
    this.progressLabel = 'Request updated';
    this.syncState();
    try {
      this.realtimeService.sendRunSteer(this.activeRunId, message, clientMutationId);
    } catch (error: unknown) {
      const fallback = this.userFacingErrorService.toUserFacingError(
        error,
        'Could not apply that refinement.',
      );
      this.messages = [...this.messages, { role: 'assistant', content: fallback }];
    } finally {
      this.syncState();
      queueMicrotask(() => this.scrollTranscriptToBottom());
    }
  }

  async cancelActiveRun(): Promise<void> {
    if (!this.conversationId || !this.activeRunId) {
      return;
    }
    try {
      this.realtimeService.sendRunCancel(this.activeRunId);
    } catch (error: unknown) {
      const fallback = this.userFacingErrorService.toUserFacingError(
        error,
        'Could not cancel the active run.',
      );
      this.messages = [...this.messages, { role: 'assistant', content: fallback }];
    } finally {
      this.syncState();
    }
  }

  private handleRealtimeMessage(message: RealtimeServerMessage): void {
    if (!this.conversationId || message.conversation_id !== this.conversationId) {
      return;
    }
    if (message.type === 'run.ack') {
      const runId = this.readString(message.payload['run_id']);
      if (runId && message.payload['command'] === 'run.start') {
        this.activeRunId = runId;
        this.activeRunVersion = this.readNumber(message.payload['run_version']);
        this.isLoading = true;
        this.realtimeService.setResumeCursor(runId, this.lastRunSequence);
      }
      if (message.payload['command'] === 'run.cancel') {
        this.status = 'Agent ready';
        this.progressLabel = undefined;
        this.isLoading = false;
        this.activeRunId = undefined;
        this.pendingRun = undefined;
      }
      this.syncState();
      this.changeDetectorRef.detectChanges();
      return;
    }
    if (message.type === 'session.resumed') {
      const state = this.readString(message.payload['state']);
      if (state === 'completed' || state === 'failed' || state === 'cancelled') {
        this.isLoading = false;
        this.activeRunId = undefined;
        this.status = 'Agent ready';
        this.progressLabel = undefined;
        this.pendingRun = undefined;
        this.syncState();
        this.changeDetectorRef.detectChanges();
      }
      return;
    }
    if (message.type === 'run.event') {
      const event = this.parseRunEvent(message.payload);
      if (event) {
        this.handleRunEvent(event);
      }
      return;
    }
    if (message.type === 'protocol.error') {
      const code = this.readString(message.payload['code']) ?? 'connection_error';
      const command = this.readString(message.payload['command']);
      if (command === 'run.start' || code === 'run_not_found' || code === 'access_denied') {
        this.isLoading = false;
        this.activeRunId = undefined;
        this.pendingRun = undefined;
      }
      this.status = 'Agent ready';
      this.progressLabel = undefined;
      const messageText = 'The real-time connection could not apply that request.';
      if (this.messages.at(-1)?.content !== messageText) {
        this.messages = [...this.messages, { role: 'assistant', content: messageText }];
      }
      this.syncState();
      this.changeDetectorRef.detectChanges();
    }
  }

  private handleRunEvent(event: RunEvent): void {
    if (event.conversation_id !== this.conversationId
      || (this.activeRunId && event.run_id !== this.activeRunId)) {
      return;
    }
    if (this.seenEventIds.has(event.event_id) || event.sequence <= this.lastRunSequence) {
      return;
    }
    this.seenEventIds.add(event.event_id);
    while (this.seenEventIds.size > this.maxSeenEventIds) {
      const oldest = this.seenEventIds.values().next().value as string | undefined;
      if (oldest === undefined) {
        break;
      }
      this.seenEventIds.delete(oldest);
    }
    this.lastRunEventId = event.event_id;
    this.lastRunSequence = event.sequence;
    this.realtimeService.setResumeCursor(event.run_id, event.sequence);
    this.activeRunVersion = event.run_version;
    switch (event.type) {
      case 'progress':
      case 'tool_started':
      case 'tool_completed':
        this.progressStage = String(event.payload['stage'] ?? event.type);
        this.progressLabel = String(event.payload['label'] ?? this.progressLabel ?? this.status);
        this.status = this.progressLabel;
        break;
      case 'assistant_text_delta':
        this.assistantDraft += String(event.payload['delta'] ?? '');
        break;
      case 'assistant_text_completed':
        this.assistantDraft = '';
        this.messages = [...this.messages, { role: 'assistant', content: String(event.payload['content'] ?? '') }];
        break;
      case 'request_updated':
        this.progressStage = 'request_updated';
        this.progressLabel = String(event.payload['label'] ?? 'Request updated');
        this.status = 'Request updated';
        break;
      case 'error':
        this.status = 'Agent needs attention';
        this.progressLabel = undefined;
        {
          const message = String(event.payload['message'] ?? 'Failed');
          this.agentReadiness = {
            status: 'needs_attention',
            label: 'Needs attention',
            message,
          };
          if (this.messages.at(-1)?.content !== message) {
            this.messages = [...this.messages, { role: 'assistant', content: message }];
          }
        }
        this.isLoading = false;
        this.activeRunId = undefined;
        this.pendingRun = undefined;
        this.streamState = 'closed';
        break;
      case 'completed':
        this.isLoading = false;
        this.status = 'Agent ready';
        this.progressLabel = undefined;
        this.progressPercent = 100;
        this.activeRunId = undefined;
        this.pendingRun = undefined;
        this.streamState = 'closed';
        this.applyRunCompletionPayload(event.payload);
        this.agentReadiness = {
          status: 'active',
          label: 'Verified',
          message: 'The selected agent model completed the latest request.',
        };
        break;
      case 'cancelled':
        this.isLoading = false;
        this.status = 'Agent ready';
        this.progressLabel = undefined;
        this.activeRunId = undefined;
        this.pendingRun = undefined;
        this.streamState = 'closed';
        break;
      case 'clarification_needed':
        this.isLoading = false;
        this.status = 'Agent ready';
        this.progressStage = 'waiting_for_clarification';
        this.progressLabel = undefined;
        this.activeRunId = undefined;
        this.pendingRun = undefined;
        this.streamState = 'closed';
        this.applyRunCompletionPayload(event.payload);
        break;
    }
    this.syncState();
    this.changeDetectorRef.detectChanges();
    queueMicrotask(() => this.scrollTranscriptToBottom());
  }

  private applyRunCompletionPayload(payload: Record<string, unknown>): void {
    const revision = typeof payload['context_revision'] === 'number'
      ? payload['context_revision']
      : undefined;
    if (revision !== undefined && this.contextRevision !== undefined && revision < this.contextRevision) {
      return;
    }
    this.contextRevision = revision ?? this.contextRevision;
    this.taskSnapshot = (payload['task_snapshot'] as ConversationTaskSnapshot | undefined)
      ?? this.taskSnapshot;
    this.lastDecision = payload['decision'] as ChatTurnResponse['decision'] | undefined
      ?? this.lastDecision;
    const mapSession = normalizeMapSession(payload['map_session']);
    if (mapSession) {
      this.handleMapSession(mapSession);
    }
    this.lastOperation = payload['operation'] as ChatOperationResult | null | undefined;
    this.memorySnapshot = (payload['memory_snapshot'] as Record<string, unknown> | undefined) ?? this.memorySnapshot;
    this.contextUsage = payload['context_usage'] as ContextUsage | undefined;
  }

  private parseRunEvent(value: Record<string, unknown>): RunEvent | undefined {
    const eventType = this.readString(value['type']);
    const eventId = this.readString(value['event_id']);
    const conversationId = this.readString(value['conversation_id']);
    const runId = this.readString(value['run_id']);
    const sequence = this.readNumber(value['sequence']);
    const runVersion = this.readNumber(value['run_version']);
    const timestamp = this.readString(value['timestamp']);
    const payload = value['payload'];
    if (!eventType || !eventId || !conversationId || !runId || sequence === undefined
      || runVersion === undefined || !timestamp || !payload || typeof payload !== 'object') {
      return undefined;
    }
    return value as unknown as RunEvent;
  }

  private readString(value: unknown): string | undefined {
    return typeof value === 'string' && value.trim() ? value : undefined;
  }

  private readNumber(value: unknown): number | undefined {
    return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
  }

  private newClientRequestId(): string {
    const random = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
    return `client_req_${random}`;
  }

  private applyTurnResponse(result: ChatTurnResponse, requestNonce: number): void {
    if (requestNonce !== this.conversationNonce) {
      return;
    }
    this.contextRevision = result.context_revision ?? this.contextRevision;
    this.taskSnapshot = result.task_snapshot ?? this.taskSnapshot;
    this.messages = [...this.messages, { role: 'assistant', content: result.assistant_message }];

    const operation = result.operation;
    const mapSession = normalizeMapSession(operation?.map_session ?? result.map_session);
    if (mapSession) {
      this.handleMapSession(mapSession);
    }
    this.lastDecision = result.decision;
    this.lastOperation = operation;
    this.memorySnapshot = result.memory_snapshot ?? {};
    this.contextUsage = result.context_usage ?? undefined;
    this.assistantDraft = '';
    this.status = 'Agent ready';
    this.progressPercent = 100;
    this.syncState();
    queueMicrotask(() => this.scrollTranscriptToBottom());
  }

  private async tryHandleLocalCommand(message: string): Promise<boolean> {
    const result = await this.localCommandService.resolve(message, {
      zoomIn: () => this.mapPreview?.zoomIn() ?? false,
      zoomOut: () => this.mapPreview?.zoomOut() ?? false,
    });
    if (!result.handled) {
      return false;
    }

    this.messages = [...this.messages, { role: 'user', content: message }];
    if (result.assistantMessage) {
      this.messages = [...this.messages, { role: 'assistant', content: result.assistantMessage }];
    }
    this.composerDraft = '';
    this.status = 'Agent ready';
    this.syncState();
    queueMicrotask(() => this.scrollTranscriptToBottom());
    return true;
  }

  private handleMapSession(mapSession: MapSession | undefined): void {
    if (!mapSession) {
      return;
    }
    this.pendingMapSession = mapSession;
    this.payload = {
      map_session: mapSession,
      compliance_warnings: mapSession.compliance_warnings,
    };
  }

  onMapRenderStateChange(change: MapRenderStateChange): void {
    if (this.pendingMapSession?.session_id !== change.sessionId) {
      return;
    }
    if (change.state === 'ready') {
      this.mapSession = this.pendingMapSession;
      this.pendingMapSession = undefined;
      this.syncState();
      this.changeDetectorRef.detectChanges();
      return;
    }
    if (change.state === 'failed') {
      this.pendingMapSession = undefined;
      if (this.mapSession) {
        this.payload = {
          map_session: this.mapSession,
          compliance_warnings: this.mapSession.compliance_warnings,
        };
      } else {
        this.payload = undefined;
      }
      const message = change.message || 'The map update could not be rendered; the previous map remains available.';
      if (this.messages.at(-1)?.content !== message) {
        this.messages = [...this.messages, { role: 'assistant', content: message }];
      }
      this.lastOperation = this.lastOperation
        ? { ...this.lastOperation, status: 'partial', message }
        : this.lastOperation;
      this.status = 'Map update failed';
      this.syncState();
      this.changeDetectorRef.detectChanges();
    }
  }

  private syncState(): void {
    const next: PersistedChatPageState = {
      toolbarWidth: this.toolbarWidthState,
      isToolbarCollapsed: this.isToolbarCollapsed,
      payload: this.payload,
      chatPanel: {
        conversationId: this.conversationId,
        contextRevision: this.contextRevision,
        taskSnapshot: this.taskSnapshot,
        activeRunId: this.activeRunId,
        activeRunVersion: this.activeRunVersion,
        pendingRun: this.pendingRun,
        lastRunEventId: this.lastRunEventId,
        lastRunSequence: this.lastRunSequence,
        streamState: this.streamState,
        progressStage: this.progressStage,
        progressLabel: this.progressLabel,
        seenRunEventIds: [...this.seenEventIds].slice(-100),
        conversationNonce: this.conversationNonce,
        messages: this.messages,
        lastDecision: this.lastDecision,
        lastOperation: this.lastOperation ?? undefined,
        memorySnapshot: this.memorySnapshot,
        contextUsage: this.contextUsage,
        mapSession: this.mapSession,
        status: this.status,
        assistantDraft: this.assistantDraft,
        composerDraft: this.composerDraft,
        transcriptScrollTop: this.viewStateSync.captureElementScroll(
          this.transcriptRef?.nativeElement,
          this.transcriptScrollTop,
        ),
      },
      mapState: this.mapState,
      scrollY: this.viewStateSync.captureWindowScroll(),
    };
    this.appStateStore.updateChatPage(next);
  }

  private clampToolbarWidth(value: number): number {
    return Math.max(this.minWidth, Math.min(this.maxWidth, value));
  }

  private stopResize(): void {
    this.isResizing = false;
    if (this.mouseMoveHandler) {
      window.removeEventListener('mousemove', this.mouseMoveHandler);
      this.mouseMoveHandler = undefined;
    }
    if (this.mouseUpHandler) {
      window.removeEventListener('mouseup', this.mouseUpHandler);
      this.mouseUpHandler = undefined;
    }
  }

  private async loadAgentStatus(): Promise<void> {
    const readiness = await this.agentReadinessService.loadReadiness();
    if (this.isDestroyed) {
      return;
    }
    this.agentReadiness = readiness;
    this.syncState();
    this.changeDetectorRef.detectChanges();
  }

  private get agentStatusTone(): CapabilityStatusTone {
    return this.agentReadiness.status === 'active' ? 'none' : 'warn';
  }

  private scrollTranscriptToBottom(): void {
    const container = this.transcriptRef?.nativeElement;
    if (!container) {
      return;
    }
    container.scrollTop = container.scrollHeight;
    this.transcriptScrollTop = container.scrollTop;
  }

  private looksLikeRuntimeFailure(message: string): boolean {
    const normalized = message.toLowerCase();
    return normalized.includes('cannot reach')
      || normalized.includes('could not reach')
      || normalized.includes('cannot process this request')
      || normalized.includes('failed')
      || normalized.includes('error');
  }

  private deriveStatusLabel(result: ChatTurnResponse): string {
    const operation = result.operation;
    if (operation) {
      if (operation.kind === 'clarification' || operation.status === 'partial') {
        return 'Need more detail';
      }
      if (operation.kind === 'error' || operation.kind === 'rejection' || operation.status === 'failed') {
        return 'Failed';
      }
      return 'Complete';
    }

    const planState = result.decision?.plan?.state;
    if (planState === 'clarify') {
      return 'Need more detail';
    }
    if (planState === 'reject') {
      return 'Failed';
    }
    return 'Complete';
  }
}
