import React from 'react';

import { ModelCardDescriptor } from '../../types';
import ModelCard from './ModelCard';

interface ModelGridProps {
    containerRef?: React.Ref<HTMLDivElement>;
    models: ModelCardDescriptor[];
    localModelIds: Set<string>;
    selectedParserModel: { provider: string; name: string };
    selectedChatModel: { provider: string; name: string };
    selectedAgentModel: { provider: string; name: string };
    onSelectParser: (model: ModelCardDescriptor) => void;
    onSelectChat: (model: ModelCardDescriptor) => void;
    onSelectAgent: (model: ModelCardDescriptor) => void;
    onPull: (model: ModelCardDescriptor) => void;
}

const ModelGrid: React.FC<ModelGridProps> = ({
    containerRef,
    models,
    localModelIds,
    selectedParserModel,
    selectedChatModel,
    selectedAgentModel,
    onSelectParser,
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
                    isSelectedForParser={model.provider === selectedParserModel.provider && model.name === selectedParserModel.name}
                    isSelectedForChat={model.provider === selectedChatModel.provider && model.name === selectedChatModel.name}
                    isSelectedForAgent={model.provider === selectedAgentModel.provider && model.name === selectedAgentModel.name}
                    onSelectParser={onSelectParser}
                    onSelectChat={onSelectChat}
                    onSelectAgent={onSelectAgent}
                    onPull={onPull}
                />
            ))}
        </div>
    </div>
);

export default ModelGrid;
