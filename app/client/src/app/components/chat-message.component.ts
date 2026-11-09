import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { marked } from 'marked';

import { ChatMessage } from '../core/types';

@Component({
  selector: 'article[appChatMessage]',
  standalone: true,
  templateUrl: './chat-message.component.html',
  styleUrl: './chat-message.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
  host: {
    class: 'chat-message',
    '[class]': "'chat-message chat-message--' + message.role + (message.kind ? ' chat-message--' + message.kind : '')",
  },
})
export class ChatMessageComponent {
  @Input({ required: true }) message!: ChatMessage;

  private renderedContent?: string;
  private renderedHtml = '';

  /** Parsed once per content change, not on every change-detection pass. */
  get assistantHtml(): string {
    if (this.message.role !== 'assistant') {
      return '';
    }
    if (this.message.content !== this.renderedContent) {
      this.renderedContent = this.message.content;
      this.renderedHtml = marked.parse(this.message.content, {
        async: false,
        breaks: true,
        gfm: true,
      }) as string;
    }
    return this.renderedHtml;
  }
}
