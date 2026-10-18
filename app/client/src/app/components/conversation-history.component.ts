import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';

import { ConversationSummary } from '../core/types';

@Component({
  selector: 'app-conversation-history',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './conversation-history.component.html',
  styleUrl: './conversation-history.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class ConversationHistoryComponent {
  @Input() conversations: ConversationSummary[] = [];
  @Input() query = '';
  @Input() selectedConversationId?: string;
  @Input() loading = false;
  @Input() error = '';
  @Input() nextCursor?: string | null;

  @Output() readonly queryChange = new EventEmitter<string>();
  @Output() readonly selectConversation = new EventEmitter<ConversationSummary>();
  @Output() readonly loadMore = new EventEmitter<void>();
  @Output() readonly close = new EventEmitter<void>();
  @Output() readonly newConversation = new EventEmitter<void>();

  trackConversation(_: number, conversation: ConversationSummary): string {
    return conversation.conversation_id;
  }

  titleFor(conversation: ConversationSummary): string {
    return conversation.title?.trim()
      || conversation.last_message_preview?.trim()
      || 'Untitled conversation';
  }

  previewFor(conversation: ConversationSummary): string {
    const preview = conversation.last_message_preview?.trim();
    if (preview && preview !== this.titleFor(conversation)) {
      return preview;
    }
    const count = conversation.message_count;
    return typeof count === 'number' ? `${count} message${count === 1 ? '' : 's'}` : 'Conversation';
  }

  updatedLabelFor(conversation: ConversationSummary): string {
    const raw = conversation.updated_at || conversation.created_at;
    if (!raw) {
      return 'Date unavailable';
    }
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) {
      return raw;
    }
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date);
  }

  onSearchInput(event: Event): void {
    this.queryChange.emit((event.target as HTMLInputElement | null)?.value ?? '');
  }
}
