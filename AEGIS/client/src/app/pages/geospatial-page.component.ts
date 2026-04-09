import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import { Router } from '@angular/router';

import { MapPreviewComponent } from '../components/map-preview.component';
import { AppStateStoreService } from '../core/app-state-store.service';
import { PersistedChatPageState } from '../core/app-state';
import { MapSession, SearchResponsePayload, ChatMessage, ChatRole, ChatStreamEvent } from '../core/types';
import { streamChatTurn } from '../core/api';

@Component({
  selector: 'app-geospatial-page',
  standalone: true,
  imports: [CommonModule, MapPreviewComponent],
  templateUrl: './geospatial-page.component.html',
  styleUrl: './geospatial-page.component.css',
})
export class GeospatialPageComponent implements AfterViewInit, OnDestroy {
  @ViewChild('transcript', { static: false }) transcriptRef?: ElementRef<HTMLDivElement>;

  payload?: SearchResponsePayload;
  toolbarWidthState = 480;
  isToolbarCollapsed = false;
  mapState = { overlayVisibility: {}, overlayOpacity: {} } as PersistedChatPageState['mapState'];

  sessionId?: number;
  messages: ChatMessage[] = [];
  status = 'Idle';
  assistantDraft = '';
  composerDraft = '';
  transcriptScrollTop = 0;

  isLoading = false;
  progressPercent = 0;
  isResizing = false;

  private readonly minWidth = 280;
  private readonly maxWidth = 760;
  private readonly canvasMinWidth = 320;
  private readonly chatPageState: PersistedChatPageState;
  private mouseMoveHandler?: (event: MouseEvent) => void;
  private mouseUpHandler?: () => void;

  constructor(
    private readonly router: Router,
    private readonly appStateStore: AppStateStoreService,
  ) {
    this.chatPageState = this.appStateStore.getChatPage();
    this.payload = this.chatPageState.payload;
    this.toolbarWidthState = this.chatPageState.toolbarWidth;
    this.isToolbarCollapsed = this.chatPageState.isToolbarCollapsed;
    this.mapState = this.chatPageState.mapState;

    this.sessionId = this.chatPageState.chatPanel.sessionId;
    this.messages = this.chatPageState.chatPanel.messages;
    this.status = this.chatPageState.chatPanel.status;
    this.assistantDraft = this.chatPageState.chatPanel.assistantDraft;
    this.composerDraft = this.chatPageState.chatPanel.composerDraft;
    this.transcriptScrollTop = this.chatPageState.chatPanel.transcriptScrollTop;
  }

  ngAfterViewInit(): void {
    window.scrollTo({ top: this.chatPageState.scrollY, behavior: 'auto' });
    if (this.transcriptRef?.nativeElement) {
      this.transcriptRef.nativeElement.scrollTop = this.transcriptScrollTop;
    }
  }

  ngOnDestroy(): void {
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
    this.syncState();
  }

  onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void this.sendMessage();
    }
  }

  onOverlayStateChange(state: { overlayVisibility: Record<string, boolean>; overlayOpacity: Record<string, number> }): void {
    this.mapState = state;
    this.syncState();
  }

  async sendMessage(): Promise<void> {
    const trimmed = this.composerDraft.trim();
    if (!trimmed || this.isLoading) {
      return;
    }

    const message = trimmed;
    this.composerDraft = '';
    this.isLoading = true;
    this.status = 'Submitting';
    this.progressPercent = 8;
    this.messages = [...this.messages, { role: 'user', content: message }];
    this.assistantDraft = '';
    this.syncState();

    try {
      await streamChatTurn(
        {
          session_id: this.sessionId,
          message,
        },
        (event) => this.pushEvent(event),
      );
    } catch (error: unknown) {
      const fallback = String((error as { message?: string })?.message ?? error);
      this.status = 'Failed';
      this.assistantDraft = '';
      this.messages = [...this.messages, { role: 'assistant', content: fallback }];
      this.progressPercent = 0;
    } finally {
      this.isLoading = false;
      this.syncState();
      queueMicrotask(() => this.scrollTranscriptToBottom());
    }
  }

  private pushEvent(event: ChatStreamEvent): void {
    if (event.event === 'status') {
      this.status = String(event.data.message ?? 'Running');
      this.progressPercent = Math.max(this.progressPercent, 14);
      this.syncState();
      return;
    }

    if (event.event === 'assistant_delta') {
      const delta = String(event.data.delta ?? '');
      this.assistantDraft = `${this.assistantDraft}${delta}`;
      this.progressPercent = Math.min(92, Math.max(this.progressPercent, 20 + Math.round(this.assistantDraft.length / 7)));
      this.syncState();
      return;
    }

    if (event.event === 'tool_status') {
      this.status = 'Executing tools';
      this.progressPercent = Math.max(this.progressPercent, 68);
      this.syncState();
      return;
    }

    if (event.event === 'error') {
      this.status = 'Failed';
      this.assistantDraft = '';
      this.progressPercent = 0;
      this.syncState();
      return;
    }

    if (event.event === 'final') {
      const finalMessage = String(event.data.assistant_message ?? this.assistantDraft ?? '');
      const nextSessionId = Number(event.data.session_id ?? this.sessionId ?? 0);
      const followUpRequired = Boolean(event.data.follow_up_required);
      if (nextSessionId > 0) {
        this.sessionId = nextSessionId;
      }
      this.messages = [...this.messages, { role: 'assistant', content: finalMessage }];

      const mapSession = event.data.map_session;
      if (typeof mapSession === 'object' && mapSession !== null) {
        this.handleMapSession(mapSession as MapSession);
      }
      this.assistantDraft = '';
      this.status = followUpRequired ? 'Need more detail' : 'Complete';
      this.progressPercent = 100;
      this.syncState();
      queueMicrotask(() => this.scrollTranscriptToBottom());
    }
  }

  private handleMapSession(mapSession: MapSession | undefined): void {
    if (!mapSession) {
      return;
    }
    this.payload = {
      satellite_imagery: this.payload?.satellite_imagery,
      map_session: mapSession,
      compliance_warnings: mapSession.compliance_warnings,
    };
  }

  private syncState(): void {
    const next: PersistedChatPageState = {
      toolbarWidth: this.toolbarWidthState,
      isToolbarCollapsed: this.isToolbarCollapsed,
      payload: this.payload,
      chatPanel: {
        sessionId: this.sessionId,
        messages: this.messages,
        status: this.status,
        assistantDraft: this.assistantDraft,
        composerDraft: this.composerDraft,
        transcriptScrollTop: this.transcriptRef?.nativeElement.scrollTop ?? this.transcriptScrollTop,
      },
      mapState: this.mapState,
      scrollY: window.scrollY,
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

  private scrollTranscriptToBottom(): void {
    const container = this.transcriptRef?.nativeElement;
    if (!container) {
      return;
    }
    container.scrollTop = container.scrollHeight;
    this.transcriptScrollTop = container.scrollTop;
  }
}
