import React from 'react';

import { CLOUD_PROVIDERS, CLOUD_MODEL_CHOICES, AGENT_MODEL_CHOICES } from '../constants';
import useCloudModelSync from '../hooks/useCloudModelSync';
import useRuntimeSettingsHandlers from '../hooks/useRuntimeSettingsHandlers';
import LabeledSelect from './LabeledSelect';
import { RuntimeSettings } from '../types';
import './ConfigurationDrawer.css';

interface ConfigurationDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    settings: RuntimeSettings;
    onSettingsChange: (newSettings: RuntimeSettings) => void;
}

const ConfigurationDrawer: React.FC<ConfigurationDrawerProps> = ({
    isOpen,
    onClose,
    settings,
    onSettingsChange,
}) => {
    useCloudModelSync({ settings, onSettingsChange });

    const {
        handleUseCloudServicesChange,
        handleProviderChange,
        handleCloudModelChange,
        handleAgentModelChange,
    } = useRuntimeSettingsHandlers({ settings, onSettingsChange });

    const cloudProviderOptions = CLOUD_PROVIDERS.map((provider) => ({ value: provider, label: provider }));
    const cloudModelOptions = (CLOUD_MODEL_CHOICES[settings.provider] || []).map((model) => ({ value: model, label: model }));
    const agentModelOptions = AGENT_MODEL_CHOICES.map((model) => ({ value: model, label: model }));

    return (
        <>
            <button
                type="button"
                className={`drawer-overlay ${isOpen ? 'open' : ''}`}
                onClick={onClose}
                aria-label="Close configuration drawer"
            />
            <div className={`drawer ${isOpen ? 'open' : ''}`}>
                <div className="drawer-content">
                    <h2 className="aegis-card-title">Models Configuration</h2>
                    <h3 className="aegis-subtitle">Configuration</h3>

                    <div className="form-group checkbox-group">
                        <label>
                            <input
                                type="checkbox"
                                checked={settings.useCloudServices}
                                onChange={(e) => handleUseCloudServicesChange(e.target.checked)}
                            />
                            {' '}
                            Use Cloud Services
                        </label>
                    </div>

                    <div className="grid-cols-1 lg:grid-cols-2 gap-5">
                        <div className="column gap-3">
                            <h3 className="aegis-subtitle">Cloud Configuration</h3>
                            <LabeledSelect
                                id="cloud-provider-select"
                                label="Cloud Service"
                                value={settings.provider}
                                options={cloudProviderOptions}
                                onChange={handleProviderChange}
                                disabled={!settings.useCloudServices}
                                selectClassName="w-full"
                            />
                            <LabeledSelect
                                id="cloud-model-select"
                                label="Cloud Model"
                                value={settings.cloudModel}
                                options={cloudModelOptions}
                                onChange={handleCloudModelChange}
                                disabled={!settings.useCloudServices}
                                selectClassName="w-full"
                            />
                        </div>

                        <div className="column gap-3">
                            <h3 className="aegis-subtitle">Ollama Configuration</h3>
                            <LabeledSelect
                                id="agent-model-select"
                                label="Agent model"
                                value={settings.agentModel}
                                options={agentModelOptions}
                                onChange={handleAgentModelChange}
                                disabled={settings.useCloudServices}
                                selectClassName="w-full"
                            />
                        </div>
                    </div>

                    <button className="close-button" onClick={onClose}>
                        <span className="material-icons">chevron_left</span> Close
                    </button>
                </div>
            </div>
        </>
    );
};

export default ConfigurationDrawer;
