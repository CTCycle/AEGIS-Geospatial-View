import React from 'react';

import './AgenticSearch.css';

import PanelHeader from './PanelHeader';
import LabeledSelect from './LabeledSelect';
import { CLOUD_MODEL_CHOICES, CLOUD_PROVIDERS, AGENT_MODEL_CHOICES } from '../constants';
import useCloudModelSync from '../hooks/useCloudModelSync';
import useRuntimeSettingsHandlers from '../hooks/useRuntimeSettingsHandlers';
import { AgenticConfig, RuntimeSettings } from '../types';

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
    useCloudModelSync({ settings, onSettingsChange });

    const {
        handleUseCloudServicesChange,
        handleProviderChange,
        handleCloudModelChange,
        handleAgentModelChange,
    } = useRuntimeSettingsHandlers({ settings, onSettingsChange });

    const handleToggle = (enabled: boolean) => {
        onChange({ ...config, enabled });
    };

    const handleObjectiveChange = (value: string) => {
        onChange({ ...config, objective: value });
    };

    const cloudProviderOptions = CLOUD_PROVIDERS.map((provider) => ({ value: provider, label: provider }));
    const cloudModelOptions = (CLOUD_MODEL_CHOICES[settings.provider] || []).map((model) => ({ value: model, label: model }));
    const agentModelOptions = AGENT_MODEL_CHOICES.map((model) => ({ value: model, label: model }));

    return (
        <div className="agentic-container">
            <div className="agentic-header">
                <PanelHeader
                    title="Agentic search"
                    description="Optional automation that explores and refines results."
                />
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
                                <span>Use cloud services</span>
                            </label>
                            <p className="helper-text">Toggle to route agent calls through a cloud provider.</p>
                        </div>

                        <LabeledSelect
                            id="cloud-provider"
                            label="Cloud provider"
                            value={settings.provider}
                            options={cloudProviderOptions}
                            onChange={handleProviderChange}
                            disabled={!settings.useCloudServices}
                        />

                        <LabeledSelect
                            id="cloud-model"
                            label="Cloud model"
                            value={settings.cloudModel}
                            options={cloudModelOptions}
                            onChange={handleCloudModelChange}
                            disabled={!settings.useCloudServices}
                        />
                    </div>

                    <div className="config-group">
                        <p className="config-title">Local agent model</p>
                        <LabeledSelect
                            id="agent-model"
                            label="Local agent model"
                            value={settings.agentModel}
                            options={agentModelOptions}
                            onChange={handleAgentModelChange}
                            disabled={settings.useCloudServices}
                            helperText="Used when cloud services are disabled."
                        />
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
