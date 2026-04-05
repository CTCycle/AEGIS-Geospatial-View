import React, { useEffect, useRef } from 'react';

import { ChatMessage as ChatMessageType } from '../../types';
import ChatMessage from './ChatMessage';

interface ChatTranscriptProps {
    messages: ChatMessageType[];
    initialScrollTop: number;
    onScrollTopChange: (value: number) => void;
}

const ChatTranscript: React.FC<ChatTranscriptProps> = ({ messages, initialScrollTop, onScrollTopChange }) => {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const endRef = useRef<HTMLDivElement | null>(null);
    const hasRestoredScrollRef = useRef(false);
    const previousLengthRef = useRef(messages.length);

    useEffect(() => {
        const container = containerRef.current;
        if (!container || hasRestoredScrollRef.current) {
            return;
        }
        container.scrollTop = initialScrollTop;
        hasRestoredScrollRef.current = true;
    }, [initialScrollTop]);

    useEffect(() => {
        const container = containerRef.current;
        if (!container) {
            return;
        }
        const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 24;
        const hasNewMessage = messages.length > previousLengthRef.current;
        previousLengthRef.current = messages.length;
        if (nearBottom && hasNewMessage) {
            endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
        }
    }, [messages]);

    return (
        <div
            ref={containerRef}
            className="chat-transcript"
            aria-live="polite"
            onScroll={(event) => onScrollTopChange(event.currentTarget.scrollTop)}
        >
            {messages.map((message, index) => (
                <ChatMessage key={`${message.role}-${index}`} message={message} />
            ))}
            <div ref={endRef} />
        </div>
    );
};

export default ChatTranscript;
