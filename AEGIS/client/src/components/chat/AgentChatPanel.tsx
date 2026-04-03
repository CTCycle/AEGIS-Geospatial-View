import React, { useMemo, useState } from 'react';

import { streamChatTurn } from '../../services/api';
import { ChatMessage, ChatRole, ChatStreamEvent, MapSession } from '../../types';
import ChatComposer from './ChatComposer';
import ChatStatusPill from './ChatStatusPill';
import ChatTranscript from './ChatTranscript';

interface AgentChatPanelProps {
    onMapSession: (mapSession: MapSession | undefined) => void;
}

const AgentChatPanel: React.FC<AgentChatPanelProps> = ({ onMapSession }) => {
    const [sessionId, setSessionId] = useState<number | undefined>();
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [status, setStatus] = useState('Idle');
    const [isLoading, setIsLoading] = useState(false);
    const [assistantDraft, setAssistantDraft] = useState('');

    const renderedMessages = useMemo(() => {
        if (!assistantDraft.trim()) {
            return messages;
        }
        return [...messages, { role: 'assistant' as ChatRole, content: assistantDraft }];
    }, [assistantDraft, messages]);

    const pushEvent = (event: ChatStreamEvent) => {
        if (event.event === 'status') {
            setStatus(String(event.data.message ?? 'Running'));
            return;
        }
        if (event.event === 'assistant_delta') {
            const delta = String(event.data.delta ?? '');
            setAssistantDraft((current) => current + delta);
            return;
        }
        if (event.event === 'tool_status') {
            setStatus('Executing tools');
            return;
        }
        if (event.event === 'error') {
            setStatus('Failed');
            setAssistantDraft('');
            return;
        }
        if (event.event === 'final') {
            const finalMessage = String(event.data.assistant_message ?? assistantDraft ?? '');
            const nextSessionId = Number(event.data.session_id ?? sessionId ?? 0);
            if (nextSessionId > 0) {
                setSessionId(nextSessionId);
            }
            setMessages((current) => [...current, { role: 'assistant' as ChatRole, content: finalMessage }]);
            const mapSession = event.data.map_session;
            if (typeof mapSession === 'object' && mapSession !== null) {
                onMapSession(mapSession as MapSession);
            }
            setAssistantDraft('');
            setStatus('Complete');
        }
    };

    const sendMessage = async (message: string) => {
        setIsLoading(true);
        setStatus('Submitting');
        setMessages((current) => [...current, { role: 'user' as ChatRole, content: message }]);
        setAssistantDraft('');
        try {
            await streamChatTurn(
                {
                    session_id: sessionId,
                    message,
                },
                pushEvent,
            );
        } catch (error: unknown) {
            const fallback = String((error as { message?: string })?.message ?? error);
            setStatus('Failed');
            setAssistantDraft('');
            setMessages((current) => [...current, { role: 'assistant' as ChatRole, content: fallback }]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="agent-chat-panel">
            <div className="agent-chat-panel__header">
                <h2 className="panel-title">Agent Chat</h2>
                <ChatStatusPill status={status} />
            </div>
            <ChatTranscript messages={renderedMessages} />
            <ChatComposer disabled={isLoading} onSend={sendMessage} />
        </div>
    );
};

export default AgentChatPanel;
