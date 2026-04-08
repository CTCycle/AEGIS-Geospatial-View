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
}) => {
    const grouped = models.reduce<Record<string, ModelCardDescriptor[]>>((acc, model) => {
        const key = model.provider.toLowerCase();
        if (!acc[key]) {
            acc[key] = [];
        }
        acc[key].push(model);
        return acc;
    }, {});

    const providers = Object.keys(grouped);
    const showSeparators = providers.length > 1;

    return (
        <div className="model-grid-scroll" ref={containerRef}>
            {providers.map((provider) => (
                <section key={provider} className="model-grid-provider">
                    {showSeparators && (
                        <header className="model-grid-provider__separator">
                            <span />
                            <p>{provider}</p>
                        </header>
                    )}
                    <div className="model-grid">
                        {grouped[provider].map((model) => (
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
                </section>
            ))}
        </div>
    );
};

export default ModelGrid;
