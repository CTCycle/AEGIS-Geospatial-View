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
    <article className="model-card">
        <header>
            <h3>{model.name}</h3>
            <span className="model-card__provider">{model.provider}</span>
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
            {model.provider === 'ollama' && !isLocalAvailable && (
                <button type="button" onClick={() => onPull(model)}>Pull</button>
            )}
        </div>
    </article>
);

export default ModelCard;
