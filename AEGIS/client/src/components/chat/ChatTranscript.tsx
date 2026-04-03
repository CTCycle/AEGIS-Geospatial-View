import React, { useEffect, useRef } from 'react';

import { ChatMessage as ChatMessageType } from '../../types';
import ChatMessage from './ChatMessage';

interface ChatTranscriptProps {
    messages: ChatMessageType[];
}

const ChatTranscript: React.FC<ChatTranscriptProps> = ({ messages }) => {
    const endRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [messages]);

    return (
        <div className="chat-transcript" aria-live="polite">
            {messages.map((message, index) => (
                <ChatMessage key={`${message.role}-${index}`} message={message} />
            ))}
            <div ref={endRef} />
        </div>
    );
};

export default ChatTranscript;
