import React from 'react';

interface ModelProviderToggleProps {
    value: 'all' | 'ollama' | 'openai' | 'google';
    onChange: (mode: 'all' | 'ollama' | 'openai' | 'google') => void;
}

const ModelProviderToggle: React.FC<ModelProviderToggleProps> = ({ value, onChange }) => (
    <div className="provider-toggle" role="group" aria-label="Model provider filter">
        <button
            type="button"
            className={value === 'all' ? 'active' : ''}
            onClick={() => onChange('all')}
        >
            All
        </button>
        <button
            type="button"
            className={value === 'ollama' ? 'active' : ''}
            onClick={() => onChange('ollama')}
        >
            Ollama
        </button>
        <button
            type="button"
            className={value === 'openai' ? 'active' : ''}
            onClick={() => onChange('openai')}
        >
            OpenAI
        </button>
        <button
            type="button"
            className={value === 'google' ? 'active' : ''}
            onClick={() => onChange('google')}
        >
            Google
        </button>
    </div>
);

export default ModelProviderToggle;
