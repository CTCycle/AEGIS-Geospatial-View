import React from 'react';
import './AgenticSearch.css';
import { AgenticConfig } from '../types';

interface AgenticSearchProps {
    config: AgenticConfig;
    onChange: (next: AgenticConfig) => void;
    isRunning: boolean;
    lastSummary?: string;
}

const AgenticSearch: React.FC<AgenticSearchProps> = ({
    config,
    onChange,
    isRunning,
    lastSummary,
}) => {
    const handleToggle = (enabled: boolean) => {
        onChange({ ...config, enabled });
    };

    const handleObjectiveChange = (value: string) => {
        onChange({ ...config, objective: value });
    };

    const handleStrategyChange = (value: AgenticConfig['strategy']) => {
        onChange({ ...config, strategy: value });
    };

    const handleMaxStepsChange = (value: number) => {
        onChange({ ...config, maxSteps: Math.max(1, value) });
    };

    const handleMaxIterationsChange = (value: number) => {
        onChange({ ...config, maxIterations: Math.max(1, value) });
    };

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

                <div className="field-grid">
                    <div className="form-group">
                        <label htmlFor="agent-strategy">Agent strategy</label>
                        <select
                            id="agent-strategy"
                            value={config.strategy}
                            onChange={(e) => handleStrategyChange(e.target.value as AgenticConfig['strategy'])}
                            disabled={!config.enabled}
                        >
                            <option value="single_pass">Single pass</option>
                            <option value="iterative_refinement">Iterative refinement</option>
                            <option value="exploratory">Exploratory</option>
                        </select>
                        <p className="helper-text">Choose how aggressively the agent explores the map.</p>
                    </div>

                    <div className="form-group inline-inputs">
                        <div>
                            <label htmlFor="max-steps">Maximum steps</label>
                            <input
                                id="max-steps"
                                type="number"
                                min={1}
                                max={50}
                                value={config.maxSteps}
                                onChange={(e) => handleMaxStepsChange(Number(e.target.value))}
                                disabled={!config.enabled}
                            />
                        </div>
                        <div>
                            <label htmlFor="max-iterations">Maximum iterations</label>
                            <input
                                id="max-iterations"
                                type="number"
                                min={1}
                                max={50}
                                value={config.maxIterations}
                                onChange={(e) => handleMaxIterationsChange(Number(e.target.value))}
                                disabled={!config.enabled}
                            />
                        </div>
                        <p className="helper-text stacked">Higher values may increase latency and cost.</p>
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
