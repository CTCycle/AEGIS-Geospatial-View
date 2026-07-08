import { Component, Input } from '@angular/core';
import { marked } from 'marked';

import { ChatMessage } from '../core/types';

@Component({
  selector: 'article[appChatMessage]',
  standalone: true,
  templateUrl: './chat-message.component.html',
  styleUrl: './chat-message.component.css',
  host: {
    class: 'chat-message',
    '[class]': "'chat-message chat-message--' + message.role + (message.kind ? ' chat-message--' + message.kind : '')",
  },
})
export class ChatMessageComponent {
  @Input({ required: true }) message!: ChatMessage;

  get assistantHtml(): string {
    if (this.message.role !== 'assistant') {
      return '';
    }
    return marked.parse(this.message.content, {
      async: false,
      breaks: true,
      gfm: true,
    }) as string;
  }
}
