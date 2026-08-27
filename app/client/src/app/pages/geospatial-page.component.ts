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
import { parseRunCompletionPayload, parseRunEvent } from '../core/realtime-parsers';
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
  CapabilityDescriptor,
  CatalogResponse,
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
  @ViewChild('composerInput', { static: false }) composerInputRef?: ElementRef<HTMLTextAreaElement>;
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
  catalog?: CatalogResponse;
  mapRenderState: 'preparing' | 'ready' | 'failed' = 'preparing';

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
  private cancelRequested = false;

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
    void this.loadCatalog();
    void this.loadModelContext();
  }

  ngAfterViewInit(): void {
    this.viewStateSync.restoreWindowScroll(this.chatPageState.scrollY);
    this.viewStateSync.restoreElementScroll(this.transcriptRef?.nativeElement, this.transcriptScrollTop);
    this.resizeComposer();
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
    const satellite = this.catalog?.basemaps?.find((item) => item.id === 'esri_world_imagery');
    const satelliteStatus = !this.catalog
      ? { statusLabel: 'Checking', tone: 'none' as CapabilityStatusTone, detail: 'Loading the live basemap catalog.' }
      : this.mapSession?.basemap_id === 'esri_world_imagery' && this.mapRenderState === 'ready'
        ? { statusLabel: 'Active', tone: 'ok' as CapabilityStatusTone, detail: 'Esri World Imagery is rendering on the active map.' }
        : this.mapSession?.basemap_id === 'esri_world_imagery' && this.mapRenderState === 'failed'
          ? { statusLabel: 'Unavailable', tone: 'error' as CapabilityStatusTone, detail: 'Satellite imagery was selected but the map renderer reported a failure.' }
        : satellite?.is_available && satellite.render?.status === 'available'
          ? { statusLabel: 'Available', tone: 'ok' as CapabilityStatusTone, detail: 'Select Satellite from the map basemap control.' }
          : { statusLabel: 'Unavailable', tone: 'error' as CapabilityStatusTone, detail: 'No usable public satellite render descriptor is available.' };
    const weather = this.catalog?.capabilities?.find((item) => (
      item.id.toLowerCase().includes('weather') || item.task_tags.some((tag) => tag.toLowerCase().includes('weather'))
    ));
    return [
      {
        label: 'Agent model',
        statusLabel: this.agentReadiness.label,
        tone: this.agentStatusTone,
      },
      { label: 'Satellite', ...satelliteStatus },
      {
        label: 'Weather',
        statusLabel: !this.catalog ? 'Checking' : weather?.is_available ? 'Available' : 'Unavailable',
        tone: !this.catalog ? 'none' : weather?.is_available ? 'ok' : 'warn',
        detail: weather?.description || 'Weather intelligence is derived from the live capability catalog.',
      },
      { label: 'Optional Keys', statusLabel: 'Optional', tone: 'warn', detail: 'Optional provider credentials are configured in Model Settings.' },
    ];
  }

  get contextUsagePercent(): number {
    return Math.max(0, Math.min(100, Math.round(this.contextUsage?.usage_percent ?? 0)));
  }

  get contextUsageLabel(): string {
    if (!this.contextUsage) {
      return '—';
    }
    return this.contextUsage.usage_percent === null ? 'Unknown' : `${this.contextUsagePercent}%`;
  }

  get contextUsageDetail(): string {
    if (!this.contextUsage) {
      return 'Context window awaiting first request';
    }
    const selected = this.contextUsage.selected_context_window ?? this.contextUsage.model_context_limit;
    const model = [this.contextUsage.provider, this.contextUsage.model].filter(Boolean).join(' / ');
    const limitText = selected ? `${selected.toLocaleString()} token cap` : 'provider limit not reported';
    return `${this.contextUsage.estimated_input_tokens.toLocaleString()} tokens / ${limitText}${model ? ` - ${model}` : ''}`;
  }

  get contextUsageTone(): 'neutral' | 'warning' | 'critical' {
    if (!this.contextUsage || this.contextUsage.usage_percent === null) {
      return 'neutral';
    }
    if (this.contextUsagePercent >= 95) {
      return 'critical';
    }
    if (this.contextUsagePercent >= 80) {
      return 'warning';
    }
    return 'neutral';
  }

  startNewChat(): void {
    this.realtimeService.disconnect({ discardPending: true });
    this.conversationId = undefined;
    this.contextRevision = undefined;
    this.taskSnapshot = undefined;
    this.activeRunId = undefined;
    this.activeRunVersion = undefined;
    this.pendingRun = undefined;
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
    this.cancelRequested = false;
    this.appStateStore.resetChatPage();
    this.syncState();
    this.queueTranscriptScroll();
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
    this.resizeComposer(target);
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

  onComposerAction(): void {
    if (this.isLoading) {
      void this.cancelActiveRun();
      return;
    }
    void this.sendMessage();
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
      this.queueTranscriptScroll();
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
      this.queueTranscriptScroll();
    }
  }

  async cancelActiveRun(): Promise<void> {
    this.cancelRequested = true;
    this.status = 'Stopping…';
    this.progressLabel = 'Stopping…';
    if (!this.conversationId || !this.activeRunId) {
      this.syncState();
      return;
    }
    try {
      this.realtimeService.sendRunCancel(this.activeRunId);
      this.cancelRequested = false;
    } catch (error: unknown) {
      const fallback = this.userFacingErrorService.toUserFacingError(
        error,
        'Could not cancel the active run.',
      );
      this.messages = [...this.messages, { role: 'assistant', content: fallback }];
      this.cancelRequested = false;
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
        if (this.cancelRequested) {
          this.cancelRequested = false;
          this.realtimeService.sendRunCancel(runId);
          // Test transports and some socket implementations can acknowledge
          // the cancel synchronously inside sendRunCancel. Do not let the
          // enclosing start acknowledgement put the UI back into generating.
          if (this.activeRunId !== runId) {
            this.isLoading = false;
          }
        }
      }
      if (message.payload['command'] === 'run.cancel') {
        this.status = 'Agent ready';
        this.progressLabel = undefined;
        this.isLoading = false;
        this.activeRunId = undefined;
        this.pendingRun = undefined;
        this.cancelRequested = false;
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
        this.cancelRequested = false;
        this.syncState();
        this.changeDetectorRef.detectChanges();
      }
      return;
    }
    if (message.type === 'run.event') {
      const event = parseRunEvent(message.payload, this.conversationId);
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
        this.cancelRequested = false;
        this.streamState = 'closed';
        break;
      case 'completed':
        this.isLoading = false;
        this.status = 'Agent ready';
        this.progressLabel = undefined;
        this.progressPercent = 100;
        this.activeRunId = undefined;
        this.pendingRun = undefined;
        this.cancelRequested = false;
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
        this.cancelRequested = false;
        this.streamState = 'closed';
        break;
      case 'clarification_needed':
        this.isLoading = false;
        this.status = 'Agent ready';
        this.progressStage = 'waiting_for_clarification';
        this.progressLabel = undefined;
        this.activeRunId = undefined;
        this.pendingRun = undefined;
        this.cancelRequested = false;
        this.streamState = 'closed';
        this.applyRunCompletionPayload(event.payload);
        break;
    }
    this.syncState();
    this.changeDetectorRef.detectChanges();
    this.queueTranscriptScroll();
  }

  private applyRunCompletionPayload(payload: Record<string, unknown>): void {
    const parsed = parseRunCompletionPayload(payload);
    if (
      parsed.contextRevision !== undefined &&
      this.contextRevision !== undefined &&
      parsed.contextRevision < this.contextRevision
    ) {
      return;
    }
    if (parsed.contextRevision !== undefined) {
      this.contextRevision = parsed.contextRevision;
    }
    if (parsed.taskSnapshot !== undefined) {
      this.taskSnapshot = parsed.taskSnapshot;
    }
    if (parsed.decision !== undefined) {
      this.lastDecision = parsed.decision;
    }
    if (parsed.mapSession) {
      this.handleMapSession(parsed.mapSession);
    }
    if (parsed.operation !== undefined) {
      this.lastOperation = parsed.operation;
    }
    if (parsed.memorySnapshot !== undefined) {
      this.memorySnapshot = parsed.memorySnapshot;
    }
    if (parsed.contextUsage !== undefined) {
      this.contextUsage = parsed.contextUsage ?? undefined;
    }
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
    this.queueTranscriptScroll();
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
    this.queueTranscriptScroll();
    return true;
  }

  private handleMapSession(mapSession: MapSession | undefined): void {
    if (!mapSession) {
      return;
    }
    this.pendingMapSession = mapSession;
    this.synchronizeOverlayState(mapSession);
    this.payload = {
      map_session: mapSession,
      compliance_warnings: mapSession.compliance_warnings,
    };
  }

  private synchronizeOverlayState(session: MapSession): void {
    const overlays = session.overlays || [];
    const ids = new Set(overlays.map((overlay) => overlay.id));
    const visibility = Object.fromEntries(
      Object.entries(this.mapState.overlayVisibility).filter(([id]) => ids.has(id)),
    );
    const opacity = Object.fromEntries(
      Object.entries(this.mapState.overlayOpacity).filter(([id]) => ids.has(id)),
    );
    overlays.forEach((overlay) => {
      if (typeof overlay.visible === 'boolean') {
        visibility[overlay.id] = overlay.visible;
      }
      if (typeof overlay.default_opacity === 'number') {
        opacity[overlay.id] = overlay.default_opacity;
      }
    });
    this.mapState = { overlayVisibility: visibility, overlayOpacity: opacity };
  }

  onMapRenderStateChange(change: MapRenderStateChange): void {
    this.mapRenderState = change.state;
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

  private async loadCatalog(): Promise<void> {
    try {
      const catalog = await this.apiClient.fetchCatalog();
      if (this.isDestroyed) {
        return;
      }
      this.catalog = catalog;
      const currentSession = this.pendingMapSession || this.mapSession || this.payload?.map_session;
      if (currentSession) {
        const enrichedSession = this.enrichMapSessionBasemap(currentSession);
        this.mapSession = enrichedSession;
        this.payload = {
          map_session: enrichedSession,
          compliance_warnings: enrichedSession.compliance_warnings,
        };
      }
      this.changeDetectorRef.detectChanges();
    } catch {
      if (!this.isDestroyed) {
        this.catalog = { capabilities: [], basemaps: [], overlays: [], tools: [] };
        this.changeDetectorRef.detectChanges();
      }
    }
  }

  private async loadModelContext(): Promise<void> {
    try {
      const settings = await this.apiClient.fetchChatSettings();
      if (this.isDestroyed) {
        return;
      }
      const profile = settings.selected_model_context || {};
      const contextLimit = typeof profile.context_window_tokens === 'number'
        ? profile.context_window_tokens
        : null;
      const maximumOutput = typeof profile.maximum_output_tokens === 'number'
        ? profile.maximum_output_tokens
        : null;
      this.contextUsage = {
        estimated_input_tokens: 0,
        selected_context_window: contextLimit,
        model_context_limit: contextLimit,
        usage_percent: contextLimit ? 0 : null,
        provider: settings.agent_model_provider,
        model: settings.agent_model_name,
        expected_output_tokens: maximumOutput,
        context_profile_source: typeof profile.context_profile_source === 'string'
          ? profile.context_profile_source
          : 'unknown',
      };
      this.changeDetectorRef.detectChanges();
    } catch {
      // The chat remains usable; unknown limits are shown explicitly.
    }
  }

  get availableBasemaps(): CapabilityDescriptor[] {
    return (this.catalog?.basemaps || []).filter((item) => item.is_available && item.render?.status === 'available');
  }

  private enrichMapSessionBasemap(session: MapSession): MapSession {
    const current = session.basemap;
    const descriptor = this.catalog?.basemaps?.find((item) => item.id === session.basemap_id);
    if (!descriptor && current) {
      return session;
    }
    const render = descriptor?.render;
    const available = render?.status === 'available';
    return {
      ...session,
      basemap: {
        id: session.basemap_id,
        label: descriptor?.name || current?.label || session.basemap_id,
        provider: descriptor?.provider || current?.provider || 'unknown',
        tile_url: render?.tile_url ?? current?.tile_url ?? null,
        style_url: render?.style_url ?? current?.style_url ?? null,
        attribution: render?.attribution || current?.attribution || '',
        render_status: available ? 'available' : 'unavailable',
        unavailable_reason: available ? null : (render?.reason || 'render_descriptor_missing'),
      },
    };
  }

  onBasemapChange(basemapId: string): void {
    const current = this.mapSession || this.payload?.map_session;
    const descriptor = this.catalog?.basemaps?.find((item) => item.id === basemapId);
    if (!current || !descriptor || descriptor.render?.status !== 'available') {
      this.status = 'Basemap unavailable';
      this.changeDetectorRef.detectChanges();
      return;
    }
    const render = descriptor.render;
    const next: MapSession = {
      ...current,
      basemap_id: descriptor.id,
      basemap: {
        id: descriptor.id,
        label: descriptor.name,
        provider: descriptor.provider,
        tile_url: render?.tile_url ?? null,
        style_url: render?.style_url ?? null,
        attribution: render?.attribution || '',
        render_status: 'available',
      },
    };
    this.pendingMapSession = next;
    this.payload = { map_session: next, compliance_warnings: next.compliance_warnings };
    this.mapRenderState = 'preparing';
    this.status = `Switching to ${descriptor.name}`;
    this.syncState();
    this.changeDetectorRef.detectChanges();
  }

  private resizeComposer(target?: HTMLTextAreaElement | null): void {
    const resolvedTarget: HTMLTextAreaElement | null = target ?? this.composerInputRef?.nativeElement ?? null;
    if (!resolvedTarget) {
      return;
    }
    resolvedTarget.style.height = 'auto';
    const maxHeight = 144;
    resolvedTarget.style.height = `${Math.min(resolvedTarget.scrollHeight, maxHeight)}px`;
    resolvedTarget.style.overflowY = resolvedTarget.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }

  private get agentStatusTone(): CapabilityStatusTone {
    return this.agentReadiness.status === 'active' ? 'ok' : 'warn';
  }

  private scrollTranscriptToBottom(): void {
    const container = this.transcriptRef?.nativeElement;
    if (!container) {
      return;
    }
    container.scrollTop = container.scrollHeight;
    this.transcriptScrollTop = container.scrollTop;
  }

  private queueTranscriptScroll(): void {
    queueMicrotask(() => {
      if (!this.isDestroyed) {
        this.scrollTranscriptToBottom();
      }
    });
  }

  private looksLikeRuntimeFailure(message: string): boolean {
    const normalized = message.toLowerCase();
    return normalized.includes('cannot reach')
      || normalized.includes('could not reach')
      || normalized.includes('cannot process this request')
      || normalized.includes('failed')
      || normalized.includes('error');
  }

}
