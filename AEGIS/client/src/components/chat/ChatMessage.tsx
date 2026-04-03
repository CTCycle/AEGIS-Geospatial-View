import React from 'react';

import { ChatMessage as ChatMessageType } from '../../types';

interface ChatMessageProps {
    message: ChatMessageType;
}

const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
    return (
        <article className={`chat-message chat-message--${message.role}`}>
            <header className="chat-message__role">{message.role}</header>
            <p className="chat-message__content">{message.content}</p>
        </article>
    );
};

export default ChatMessage;
