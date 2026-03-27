import React from 'react';

import PanelHeader from './PanelHeader';
import './StatsPanel.css';
import { SearchResponsePayload } from '../types';

interface StatsPanelProps {
    payload?: SearchResponsePayload;
    message?: string;
    isLoading: boolean;
    locationSummary: string;
}

const StatsPanel: React.FC<StatsPanelProps> = ({
    payload,
    message,
    isLoading,
    locationSummary,
}) => {
    const featureCount =
        typeof payload?.feature_count === 'number'
            ? payload.feature_count
            : Array.isArray(payload?.features)
                ? payload.features.length
                : Array.isArray(payload?.satellite_imagery?.features)
                    ? payload.satellite_imagery.features.length
                    : undefined;
    const datasetName =
        payload?.dataset_name ??
        payload?.data_source ??
        payload?.satellite_imagery?.source ??
        'Not specified';
    const coverage =
        payload?.coverage_area ??
        payload?.coverage_km2 ??
        payload?.satellite_imagery?.area_km2 ??
        payload?.satellite_imagery?.coverage_km2;
    const timeRange =
        payload?.time_range ??
        payload?.satellite_imagery?.time_range ??
        payload?.satellite_imagery?.date ??
        'Not provided';
    const formatName =
        payload?.satellite_imagery?.format ??
        payload?.satellite_imagery?.mime ??
        payload?.satellite_imagery?.image_format ??
        'Image';

    const formatMetricValue = (value: unknown) => {
        if (value === undefined || value === null) {
            return '—';
        }
        if (typeof value === 'number') {
            return value.toLocaleString();
        }
        return String(value);
    };

    const verboseText = () => {
        if (isLoading) {
            return 'Processing search and rendering map...';
        }
        if (!payload && !message) {
            return 'Run a search to see statistics, summaries, and agent insights.';
        }
        const lines = [
            locationSummary,
            'Standard search executed.',
        ];
        if (message) {
            lines.push(message);
        }
        return lines.filter(Boolean).join('\n\n');
    };

    return (
        <div className="stats-container">
            <div className="stats-header">
                <PanelHeader
                    title="Map statistics"
                    description="Metrics and narrative tied to the current map view."
                    headingLevel={3}
                />
            </div>

            <div className="metrics-grid" aria-live="polite">
                <div className="metric-card">
                    <p className="metric-label">Features rendered</p>
                    <p className="metric-value">{formatMetricValue(featureCount)}</p>
                </div>
                <div className="metric-card">
                    <p className="metric-label">Dataset</p>
                    <p className="metric-value">{formatMetricValue(datasetName)}</p>
                </div>
                <div className="metric-card">
                    <p className="metric-label">Coverage</p>
                    <p className="metric-value">
                        {coverage !== undefined && coverage !== null
                            ? `${formatMetricValue(coverage)} km²`
                            : '—'}
                    </p>
                </div>
                <div className="metric-card">
                    <p className="metric-label">Time range</p>
                    <p className="metric-value">{formatMetricValue(timeRange)}</p>
                </div>
                <div className="metric-card">
                    <p className="metric-label">Format</p>
                    <p className="metric-value">{formatMetricValue(formatName)}</p>
                </div>
            </div>

            <section className="verbose-box" aria-label="Verbose map information">
                <p className="verbose-title">Verbose info</p>
                <div className="verbose-content">
                    <pre>{verboseText()}</pre>
                </div>
            </section>
        </div>
    );
};

export default StatsPanel;
