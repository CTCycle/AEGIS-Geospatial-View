import React from 'react';

import { ModelCardDescriptor } from '../../types';
import ModelCard from './ModelCard';

interface ModelGridProps {
    models: ModelCardDescriptor[];
    localModelIds: Set<string>;
    selectedChatModel: { provider: string; name: string };
    selectedAgentModel: { provider: string; name: string };
    onSelectChat: (model: ModelCardDescriptor) => void;
    onSelectAgent: (model: ModelCardDescriptor) => void;
    onPull: (model: ModelCardDescriptor) => void;
}

const ModelGrid: React.FC<ModelGridProps> = ({
    models,
    localModelIds,
    selectedChatModel,
    selectedAgentModel,
    onSelectChat,
    onSelectAgent,
    onPull,
}) => (
    <div className="model-grid-scroll">
        <div className="model-grid">
            {models.map((model) => (
                <ModelCard
                    key={`${model.provider}:${model.id}`}
                    model={model}
                    isLocalAvailable={localModelIds.has(model.id)}
                    isSelectedForChat={model.provider === selectedChatModel.provider && model.name === selectedChatModel.name}
                    isSelectedForAgent={model.provider === selectedAgentModel.provider && model.name === selectedAgentModel.name}
                    onSelectChat={onSelectChat}
                    onSelectAgent={onSelectAgent}
                    onPull={onPull}
                />
            ))}
        </div>
    </div>
);

export default ModelGrid;
