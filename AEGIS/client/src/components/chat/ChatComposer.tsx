import React from 'react';

interface ChatComposerProps {
    disabled: boolean;
    onSend: (message: string) => void;
    value: string;
    onChange: (value: string) => void;
}

const ChatComposer: React.FC<ChatComposerProps> = ({ disabled, onSend, value, onChange }) => {
    const submit = () => {
        const trimmed = value.trim();
        if (!trimmed) {
            return;
        }
        onSend(trimmed);
        onChange('');
    };

    return (
        <div className="chat-composer">
            <textarea
                aria-label="Chat message"
                value={value}
                onChange={(event) => onChange(event.target.value)}
                onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        submit();
                    }
                }}
                disabled={disabled}
                placeholder="Ask for a place, coordinates, or environmental overlay."
            />
            <button type="button" className="primary-button" onClick={submit} disabled={disabled || !value.trim()}>
                <span className="sr-only">Send message</span>
                <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
                    <path
                        d="M21.7 3.3a1 1 0 0 0-1-.2L3.6 9.7a1 1 0 0 0 0 1.9l7.8 2.6 2.6 7.8a1 1 0 0 0 .9.7h.1a1 1 0 0 0 .9-.6l6.8-17.8a1 1 0 0 0-.2-1zM15 18.8l-1.8-5.5 4.6-4.6-5.9 3.6-5.5-1.8L19.2 5 15 18.8z"
                        fill="currentColor"
                    />
                </svg>
            </button>
        </div>
    );
};

export default ChatComposer;
