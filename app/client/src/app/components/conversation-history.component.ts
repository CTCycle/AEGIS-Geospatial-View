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
  @Input() selectedConversationId?: string;
  @Input() loading = false;
  @Input() error = '';

  @Output() readonly selectConversation = new EventEmitter<ConversationSummary>();
  @Output() readonly collapse = new EventEmitter<void>();

  trackConversation(_: number, conversation: ConversationSummary): string {
    return conversation.conversation_id;
  }

  titleFor(conversation: ConversationSummary): string {
    return conversation.title?.trim()
      || conversation.last_message_preview?.trim()
      || 'Untitled conversation';
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
}
