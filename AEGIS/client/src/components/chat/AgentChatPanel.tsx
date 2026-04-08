import React, { useMemo, useState } from 'react';

import { streamChatTurn } from '../../services/api';
import { ChatMessage, ChatRole, ChatStreamEvent, MapSession } from '../../types';
import ChatComposer from './ChatComposer';
import ChatTranscript from './ChatTranscript';

interface AgentChatPanelProps {
    onMapSession: (mapSession: MapSession | undefined) => void;
    initialState: {
        sessionId?: number;
        messages: ChatMessage[];
        status: string;
        assistantDraft: string;
        composerDraft: string;
        transcriptScrollTop: number;
    };
    onStateChange: (state: {
        sessionId?: number;
        messages: ChatMessage[];
        status: string;
        assistantDraft: string;
        composerDraft: string;
        transcriptScrollTop: number;
    }) => void;
    onProgressChange?: (state: { isLoading: boolean; progressPercent: number }) => void;
}

const AgentChatPanel: React.FC<AgentChatPanelProps> = ({
    onMapSession,
    initialState,
    onStateChange,
    onProgressChange,
}) => {
    const [sessionId, setSessionId] = useState<number | undefined>(initialState.sessionId);
    const [messages, setMessages] = useState<ChatMessage[]>(initialState.messages);
    const [status, setStatus] = useState(initialState.status);
    const [isLoading, setIsLoading] = useState(false);
    const [progressPercent, setProgressPercent] = useState(0);
    const [assistantDraft, setAssistantDraft] = useState(initialState.assistantDraft);
    const [composerDraft, setComposerDraft] = useState(initialState.composerDraft);
    const [transcriptScrollTop, setTranscriptScrollTop] = useState(initialState.transcriptScrollTop);

    const renderedMessages = useMemo(() => {
        if (!assistantDraft.trim()) {
            return messages;
        }
        return [...messages, { role: 'assistant' as ChatRole, content: assistantDraft }];
    }, [assistantDraft, messages]);

    const pushEvent = (event: ChatStreamEvent) => {
        if (event.event === 'status') {
            setStatus(String(event.data.message ?? 'Running'));
            setProgressPercent((current) => Math.max(current, 14));
            return;
        }
        if (event.event === 'assistant_delta') {
            const delta = String(event.data.delta ?? '');
            setAssistantDraft((current) => current + delta);
            setProgressPercent((current) => Math.min(92, Math.max(current, 20 + Math.round((assistantDraft.length + delta.length) / 7))));
            return;
        }
        if (event.event === 'tool_status') {
            setStatus('Executing tools');
            setProgressPercent((current) => Math.max(current, 68));
            return;
        }
        if (event.event === 'error') {
            setStatus('Failed');
            setAssistantDraft('');
            setProgressPercent(0);
            return;
        }
        if (event.event === 'final') {
            const finalMessage = String(event.data.assistant_message ?? assistantDraft ?? '');
            const nextSessionId = Number(event.data.session_id ?? sessionId ?? 0);
            const followUpRequired = Boolean(event.data.follow_up_required);
            if (nextSessionId > 0) {
                setSessionId(nextSessionId);
            }
            setMessages((current) => [...current, { role: 'assistant' as ChatRole, content: finalMessage }]);
            const mapSession = event.data.map_session;
            if (typeof mapSession === 'object' && mapSession !== null) {
                onMapSession(mapSession as MapSession);
            }
            setAssistantDraft('');
            setStatus(followUpRequired ? 'Need more detail' : 'Complete');
            setProgressPercent(100);
        }
    };

    const sendMessage = async (message: string) => {
        setIsLoading(true);
        setStatus('Submitting');
        setProgressPercent(8);
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

    React.useEffect(() => {
        onProgressChange?.({
            isLoading,
            progressPercent: isLoading ? Math.max(4, Math.min(100, progressPercent)) : progressPercent,
        });
    }, [isLoading, progressPercent, onProgressChange]);

    React.useEffect(() => {
        onStateChange({
            sessionId,
            messages,
            status,
            assistantDraft,
            composerDraft,
            transcriptScrollTop,
        });
    }, [sessionId, messages, status, assistantDraft, composerDraft, transcriptScrollTop, onStateChange]);

    return (
        <div className="agent-chat-panel">
            <ChatTranscript
                messages={renderedMessages}
                initialScrollTop={initialState.transcriptScrollTop}
                onScrollTopChange={setTranscriptScrollTop}
            />
            <ChatComposer disabled={isLoading} onSend={sendMessage} value={composerDraft} onChange={setComposerDraft} />
        </div>
    );
};

export default AgentChatPanel;
