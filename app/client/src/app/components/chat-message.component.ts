import { Component, Input } from '@angular/core';

import { ChatMessage } from '../core/types';

@Component({
  selector: 'article[appChatMessage]',
  standalone: true,
  templateUrl: './chat-message.component.html',
  host: {
    class: 'chat-message',
    '[class]': "'chat-message chat-message--' + message.role",
  },
})
export class ChatMessageComponent {
  @Input({ required: true }) message!: ChatMessage;
}
