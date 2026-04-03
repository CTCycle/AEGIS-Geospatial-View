import React, { useState } from 'react';

interface ChatComposerProps {
    disabled: boolean;
    onSend: (message: string) => void;
}

const ChatComposer: React.FC<ChatComposerProps> = ({ disabled, onSend }) => {
    const [message, setMessage] = useState('');

    const submit = () => {
        const trimmed = message.trim();
        if (!trimmed) {
            return;
        }
        onSend(trimmed);
        setMessage('');
    };

    return (
        <div className="chat-composer">
            <textarea
                aria-label="Chat message"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        submit();
                    }
                }}
                disabled={disabled}
                placeholder="Ask for a place, coordinates, or environmental overlay."
            />
            <button type="button" className="primary-button" onClick={submit} disabled={disabled || !message.trim()}>
                Send
            </button>
        </div>
    );
};

export default ChatComposer;
