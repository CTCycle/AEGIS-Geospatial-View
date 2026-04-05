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
                Send
            </button>
        </div>
    );
};

export default ChatComposer;
