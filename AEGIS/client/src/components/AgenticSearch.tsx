import React, { useEffect } from 'react';
import './AgenticSearch.css';
import { AgenticConfig, RuntimeSettings } from '../types';
import { CLOUD_MODEL_CHOICES, CLOUD_PROVIDERS, AGENT_MODEL_CHOICES } from '../constants';

interface AgenticSearchProps {
    config: AgenticConfig;
    onChange: (next: AgenticConfig) => void;
    isRunning: boolean;
    lastSummary?: string;
    settings: RuntimeSettings;
    onSettingsChange: (next: RuntimeSettings) => void;
}

const AgenticSearch: React.FC<AgenticSearchProps> = ({
    config,
    onChange,
    isRunning,
    lastSummary,
    settings,
    onSettingsChange,
}) => {
    const handleToggle = (enabled: boolean) => {
        onChange({ ...config, enabled });
    };

    const handleObjectiveChange = (value: string) => {
        onChange({ ...config, objective: value });
    };

    const handleUseCloudServicesChange = (value: boolean) => {
        onSettingsChange({ ...settings, useCloudServices: value });
    };

    const handleProviderChange = (value: string) => {
        const availableModels = CLOUD_MODEL_CHOICES[value] || [];
        onSettingsChange({
            ...settings,
            provider: value,
            cloudModel: availableModels[0] || '',
        });
    };

    const handleCloudModelChange = (value: string) => {
        onSettingsChange({ ...settings, cloudModel: value });
    };

    const handleAgentModelChange = (value: string) => {
        onSettingsChange({ ...settings, agentModel: value });
    };

    useEffect(() => {
        const models = CLOUD_MODEL_CHOICES[settings.provider] || [];
        if (!models.includes(settings.cloudModel) && models.length > 0) {
            onSettingsChange({ ...settings, cloudModel: models[0] });
        }
    }, [settings.provider, settings.cloudModel, settings, onSettingsChange]);

    return (
        <div className="agentic-container">
            <div className="agentic-header">
                <div>
                    <h3 className="panel-title">Agentic search</h3>
                    <p className="panel-description">Optional automation that explores and refines results.</p>
                </div>
                <label className="toggle-control">
                    <input
                        type="checkbox"
                        checked={config.enabled}
                        onChange={(e) => handleToggle(e.target.checked)}
                        aria-label="Enable agentic search"
                    />
                    <span className="toggle-slider" aria-hidden="true" />
                    <span className="toggle-label">{config.enabled ? 'Enabled' : 'Disabled'}</span>
                </label>
            </div>

            <div className="agentic-fields" aria-disabled={!config.enabled}>
                <div className="form-group">
                    <label htmlFor="agent-objective">Agent objective</label>
                    <textarea
                        id="agent-objective"
                        placeholder="Describe the goal or instructions for the agent"
                        value={config.objective}
                        onChange={(e) => handleObjectiveChange(e.target.value)}
                        disabled={!config.enabled}
                        rows={3}
                    />
                </div>

                <div className="config-grid">
                    <div className="config-group">
                        <p className="config-title">Cloud agent (optional)</p>
                        <div className="form-group checkbox-row">
                            <label htmlFor="use-cloud" className="inline-label">
                                <input
                                    id="use-cloud"
                                    type="checkbox"
                                    checked={settings.useCloudServices}
                                    onChange={(e) => handleUseCloudServicesChange(e.target.checked)}
                                />
                                Use cloud services
                            </label>
                            <p className="helper-text">Toggle to route agent calls through a cloud provider.</p>
                        </div>

                        <div className="form-group">
                            <label htmlFor="cloud-provider">Cloud provider</label>
                            <select
                                id="cloud-provider"
                                value={settings.provider}
                                onChange={(e) => handleProviderChange(e.target.value)}
                                disabled={!settings.useCloudServices}
                            >
                                {CLOUD_PROVIDERS.map((provider) => (
                                    <option key={provider} value={provider}>{provider}</option>
                                ))}
                            </select>
                        </div>

                        <div className="form-group">
                            <label htmlFor="cloud-model">Cloud model</label>
                            <select
                                id="cloud-model"
                                value={settings.cloudModel}
                                onChange={(e) => handleCloudModelChange(e.target.value)}
                                disabled={!settings.useCloudServices}
                            >
                                {(CLOUD_MODEL_CHOICES[settings.provider] || []).map((model) => (
                                    <option key={model} value={model}>{model}</option>
                                ))}
                            </select>
                        </div>
                    </div>

                    <div className="config-group">
                        <p className="config-title">Local agent model</p>
                        <div className="form-group">
                            <label htmlFor="agent-model">Local agent model</label>
                            <select
                                id="agent-model"
                                value={settings.agentModel}
                                onChange={(e) => handleAgentModelChange(e.target.value)}
                                disabled={settings.useCloudServices}
                            >
                                {AGENT_MODEL_CHOICES.map((model) => (
                                    <option key={model} value={model}>{model}</option>
                                ))}
                            </select>
                            <p className="helper-text">Used when cloud services are disabled.</p>
                        </div>
                    </div>
                </div>
            </div>

            <div className="agentic-status" aria-live="polite">
                {config.enabled && isRunning && <span className="status-pill running">Agentic search in progress</span>}
                {config.enabled && !isRunning && (
                    <span className="status-pill ready">Agentic settings will apply to the next search</span>
                )}
                {!config.enabled && <span className="status-pill muted">Agentic search is off</span>}
                {config.enabled && lastSummary && <p className="summary-text">{lastSummary}</p>}
            </div>
        </div>
    );
};

export default AgenticSearch;
