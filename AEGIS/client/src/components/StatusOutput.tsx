import React, { useState } from 'react';

import './StatusOutput.css';

interface StatusOutputProps {
    message?: string;
    json?: unknown;
}

const StatusOutput: React.FC<StatusOutputProps> = ({ message, json }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    const toggleExpansion = () => {
        setIsExpanded(!isExpanded);
    };

    const renderContent = () => {
        if (!message && !json) {
            return <div className="status-placeholder">Waiting for response...</div>;
        }

        return (
            <div className="status-content">
                {message && <div className="status-message">{message}</div>}
                {json !== undefined && json !== null && (
                    <pre className="json-output">
                        <code>{JSON.stringify(json, null, 2)}</code>
                    </pre>
                )}
            </div>
        );
    };

    return (
        <div className="card status-card">
            <div className="card-content">
                <button
                    type="button"
                    className="accordion-header"
                    onClick={toggleExpansion}
                    aria-expanded={isExpanded}
                    aria-controls="status-output-content"
                >
                    <span className="accordion-title">Endpoint Output</span>
                    <span className="material-icons accordion-icon">
                        {isExpanded ? 'expand_less' : 'expand_more'}
                    </span>
                </button>

                <div
                    id="status-output-content"
                    className={`accordion-content ${isExpanded ? 'expanded' : ''}`}
                >
                    <div className="scroll-area">
                        {renderContent()}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default StatusOutput;

