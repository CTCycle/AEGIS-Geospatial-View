import React from 'react';

interface ChatStatusPillProps {
    status: string;
}

const ChatStatusPill: React.FC<ChatStatusPillProps> = ({ status }) => (
    <span className="chat-status-pill">{status}</span>
);

export default ChatStatusPill;
