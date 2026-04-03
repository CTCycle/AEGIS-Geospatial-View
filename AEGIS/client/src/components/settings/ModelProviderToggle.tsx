import React from 'react';

import { ModelProviderMode } from '../../types';

interface ModelProviderToggleProps {
    value: ModelProviderMode;
    onChange: (mode: ModelProviderMode) => void;
}

const ModelProviderToggle: React.FC<ModelProviderToggleProps> = ({ value, onChange }) => (
    <div className="provider-toggle" role="group" aria-label="Provider mode">
        <button
            type="button"
            className={value === 'local' ? 'active' : ''}
            onClick={() => onChange('local')}
        >
            Ollama
        </button>
        <button
            type="button"
            className={value === 'cloud' ? 'active' : ''}
            onClick={() => onChange('cloud')}
        >
            Cloud
        </button>
    </div>
);

export default ModelProviderToggle;
