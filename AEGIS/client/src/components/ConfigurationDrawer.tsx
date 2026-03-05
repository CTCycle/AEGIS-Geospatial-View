import React from 'react';

import { CLOUD_PROVIDERS, CLOUD_MODEL_CHOICES, AGENT_MODEL_CHOICES } from '../constants';
import useCloudModelSync from '../hooks/useCloudModelSync';
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

    const handleProviderChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
        const newProvider = e.target.value;
        const availableModels = CLOUD_MODEL_CHOICES[newProvider] || [];
        onSettingsChange({
            ...settings,
            provider: newProvider,
            cloudModel: availableModels[0] || '',
        });
    };

    const handleCloudModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
        onSettingsChange({ ...settings, cloudModel: e.target.value });
    };

    const handleAgentModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
        onSettingsChange({ ...settings, agentModel: e.target.value });
    };

    const handleUseCloudServicesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        onSettingsChange({ ...settings, useCloudServices: e.target.checked });
    };

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
                                onChange={handleUseCloudServicesChange}
                            />
                            {' '}
                            Use Cloud Services
                        </label>
                    </div>

                    <div className="grid-cols-1 lg:grid-cols-2 gap-5">
                        <div className="column gap-3">
                            <h3 className="aegis-subtitle">Cloud Configuration</h3>
                            <div className="form-group">
                                <label htmlFor="cloud-provider-select">Cloud Service</label>
                                <select
                                    id="cloud-provider-select"
                                    value={settings.provider}
                                    onChange={handleProviderChange}
                                    disabled={!settings.useCloudServices}
                                    className="w-full"
                                >
                                    {CLOUD_PROVIDERS.map((p) => (
                                        <option key={p} value={p}>{p}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="form-group">
                                <label htmlFor="cloud-model-select">Cloud Model</label>
                                <select
                                    id="cloud-model-select"
                                    value={settings.cloudModel}
                                    onChange={handleCloudModelChange}
                                    disabled={!settings.useCloudServices}
                                    className="w-full"
                                >
                                    {(CLOUD_MODEL_CHOICES[settings.provider] || []).map((m) => (
                                        <option key={m} value={m}>{m}</option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        <div className="column gap-3">
                            <h3 className="aegis-subtitle">Ollama Configuration</h3>
                            <div className="form-group">
                                <label htmlFor="agent-model-select">Agent model</label>
                                <select
                                    id="agent-model-select"
                                    value={settings.agentModel}
                                    onChange={handleAgentModelChange}
                                    disabled={settings.useCloudServices}
                                    className="w-full"
                                >
                                    {AGENT_MODEL_CHOICES.map((m) => (
                                        <option key={m} value={m}>{m}</option>
                                    ))}
                                </select>
                            </div>
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
