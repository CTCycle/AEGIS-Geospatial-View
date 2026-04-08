import React from 'react';

import { ModelCardDescriptor } from '../../types';

interface ModelCardProps {
    model: ModelCardDescriptor;
    isLocalAvailable: boolean;
    isSelectedForParser: boolean;
    isSelectedForChat: boolean;
    isSelectedForAgent: boolean;
    onSelectParser: (model: ModelCardDescriptor) => void;
    onSelectChat: (model: ModelCardDescriptor) => void;
    onSelectAgent: (model: ModelCardDescriptor) => void;
    onPull: (model: ModelCardDescriptor) => void;
}

const ModelCard: React.FC<ModelCardProps> = ({
    model,
    isLocalAvailable,
    isSelectedForParser,
    isSelectedForChat,
    isSelectedForAgent,
    onSelectParser,
    onSelectChat,
    onSelectAgent,
    onPull,
}) => (
    <article className={`model-card${isLocalAvailable ? ' model-card--local' : ''}`}>
        <header>
            <h3>{model.name}</h3>
            {model.provider === 'ollama' && !isLocalAvailable && (
                <button type="button" className="model-card__pull" onClick={() => onPull(model)} aria-label={`Pull ${model.name}`} title="Pull model">
                    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" focusable="false">
                        <path
                            d="M12 3.5a1 1 0 0 1 1 1v8l2.7-2.7a1 1 0 1 1 1.4 1.4l-4.4 4.4a1 1 0 0 1-1.4 0l-4.4-4.4a1 1 0 0 1 1.4-1.4L11 12.5v-8a1 1 0 0 1 1-1zm-6 14h12a1 1 0 1 1 0 2H6a1 1 0 1 1 0-2z"
                            fill="currentColor"
                        />
                    </svg>
                </button>
            )}
        </header>
        <p>{model.description}</p>
        <div className="model-card__actions">
            <button type="button" className={isSelectedForParser ? 'active' : ''} onClick={() => onSelectParser(model)}>
                {isSelectedForParser ? 'Parser model' : 'Use for parser'}
            </button>
            <button type="button" className={isSelectedForChat ? 'active' : ''} onClick={() => onSelectChat(model)}>
                {isSelectedForChat ? 'Chat model' : 'Use for chat'}
            </button>
            <button type="button" className={isSelectedForAgent ? 'active' : ''} onClick={() => onSelectAgent(model)}>
                {isSelectedForAgent ? 'Agent model' : 'Use for agent'}
            </button>
        </div>
    </article>
);

export default ModelCard;
