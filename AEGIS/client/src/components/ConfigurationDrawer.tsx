import React, { useEffect } from 'react';
import { CLOUD_PROVIDERS, CLOUD_MODEL_CHOICES, AGENT_MODEL_CHOICES } from '../constants';
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

    const handleTemperatureChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        onSettingsChange({ ...settings, temperature: parseFloat(e.target.value) });
    };

    const handleReasoningChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        onSettingsChange({ ...settings, reasoning: e.target.checked });
    };

    const handleUseCloudServicesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        onSettingsChange({ ...settings, useCloudServices: e.target.checked });
    };

    // Ensure valid model selection when provider changes or on init
    useEffect(() => {
        const models = CLOUD_MODEL_CHOICES[settings.provider] || [];
        if (!models.includes(settings.cloudModel) && models.length > 0) {
            onSettingsChange({ ...settings, cloudModel: models[0] });
        }
    }, [settings.provider, settings.cloudModel, settings, onSettingsChange]);

    return (
        <>
            <div className={`drawer-overlay ${isOpen ? 'open' : ''}`} onClick={onClose} />
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
                            Use Cloud Services
                        </label>
                    </div>

                    <div className="grid-cols-1 lg:grid-cols-2 gap-5">
                        <div className="column gap-3">
                            <h3 className="aegis-subtitle">Cloud Configuration</h3>
                            <div className="form-group">
                                <label>Cloud Service</label>
                                <select
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
                                <label>Cloud Model</label>
                                <select
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
                                <label>Parsing Model</label>
                                <select
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
                            <div className="form-group">
                                <label>Temperature</label>
                                <input
                                    type="number"
                                    value={settings.temperature}
                                    onChange={handleTemperatureChange}
                                    min={0.0}
                                    max={5.0}
                                    step={0.1}
                                    disabled={settings.useCloudServices}
                                    className="w-full"
                                />
                            </div>
                            <div className="form-group checkbox-group">
                                <label>
                                    <input
                                        type="checkbox"
                                        checked={settings.reasoning}
                                        onChange={handleReasoningChange}
                                        disabled={settings.useCloudServices}
                                    />
                                    Enable reasoning (think)
                                </label>
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
