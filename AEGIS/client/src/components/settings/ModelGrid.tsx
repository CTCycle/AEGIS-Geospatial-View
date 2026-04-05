import React from 'react';

import { ModelCardDescriptor } from '../../types';
import ModelCard from './ModelCard';

interface ModelGridProps {
    containerRef?: React.Ref<HTMLDivElement>;
    models: ModelCardDescriptor[];
    localModelIds: Set<string>;
    selectedChatModel: { provider: string; name: string };
    selectedAgentModel: { provider: string; name: string };
    onSelectChat: (model: ModelCardDescriptor) => void;
    onSelectAgent: (model: ModelCardDescriptor) => void;
    onPull: (model: ModelCardDescriptor) => void;
}

const ModelGrid: React.FC<ModelGridProps> = ({
    containerRef,
    models,
    localModelIds,
    selectedChatModel,
    selectedAgentModel,
    onSelectChat,
    onSelectAgent,
    onPull,
}) => (
    <div className="model-grid-scroll" ref={containerRef}>
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
