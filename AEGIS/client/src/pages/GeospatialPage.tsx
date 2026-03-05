import { useMemo, useState } from 'react';

import AgenticSearch from '../components/AgenticSearch';
import LocationSearch from '../components/LocationSearch';
import MapPreview from '../components/MapPreview';
import PanelHeader from '../components/PanelHeader';
import StatsPanel from '../components/StatsPanel';
import { searchLocation } from '../services/api';
import { AgenticConfig, LocationSearchRequest, RuntimeSettings, SearchResponsePayload } from '../types';
import './GeospatialPage.css';

interface SearchResultState {
    message?: string;
    json?: unknown;
    payload?: SearchResponsePayload;
}

const readErrorField = (error: unknown, field: string): unknown => {
    if (typeof error !== 'object' || error === null) {
        return undefined;
    }
    return Reflect.get(error, field);
};

function GeospatialPage() {
    const [settings, setSettings] = useState<RuntimeSettings>({
        useCloudServices: false,
        provider: 'openai',
        cloudModel: 'gpt-4o',
        agentModel: 'llama3.1:8b',
    });

    const [isLoading, setIsLoading] = useState(false);
    const [searchResult, setSearchResult] = useState<SearchResultState>({});
    const [lastRequest, setLastRequest] = useState<LocationSearchRequest | undefined>();
    const [agenticConfig, setAgenticConfig] = useState<AgenticConfig>({
        enabled: false,
        objective: '',
    });
    const [agentSummary, setAgentSummary] = useState<string | undefined>();

    const handleSearch = async (request: LocationSearchRequest) => {
        setIsLoading(true);
        setSearchResult({});
        setAgentSummary(undefined);

        try {
            const enrichedRequest: LocationSearchRequest = {
                ...request,
                agentic_enabled: agenticConfig.enabled,
                agent_prompt: agenticConfig.enabled ? agenticConfig.objective : undefined,
                llm_provider: settings.useCloudServices ? settings.provider : undefined,
                cloud_model: settings.useCloudServices ? settings.cloudModel : undefined,
                agent_model: settings.useCloudServices ? undefined : settings.agentModel,
            };

            setLastRequest(enrichedRequest);

            const response = await searchLocation(enrichedRequest);
            setSearchResult({
                message: response.status_message,
                json: response.json ?? response.payload,
                payload: response.payload,
            });
            setAgentSummary(
                typeof response.payload?.agent_summary === 'string'
                    ? response.payload.agent_summary
                    : typeof response.payload?.status_message === 'string'
                        ? response.payload.status_message
                        : response.status_message,
            );
        } catch (error: unknown) {
            const statusCandidate = readErrorField(error, 'status');
            const statusPrefix = typeof statusCandidate === 'number' ? ` ${statusCandidate}` : '';
            const messageCandidate = readErrorField(error, 'message');
            const detailCandidate = readErrorField(error, 'detail');
            const rawCandidate = readErrorField(error, 'raw');

            setSearchResult({
                message: `Error${statusPrefix}: ${typeof messageCandidate === 'string' ? messageCandidate : 'Request failed'}`,
                json: detailCandidate ?? rawCandidate ?? error,
            });
        } finally {
            setIsLoading(false);
        }
    };

    const locationSummary = useMemo(() => {
        if (!lastRequest) {
            return 'No location selected yet.';
        }
        if (lastRequest.use_coordinates && lastRequest.latitude !== undefined && lastRequest.longitude !== undefined) {
            return `Lat ${lastRequest.latitude.toFixed(4)}, Lon ${lastRequest.longitude.toFixed(4)}`;
        }
        const parts = [lastRequest.address, lastRequest.city, lastRequest.country].filter(Boolean);
        return parts.join(', ') || 'Location submitted';
    }, [lastRequest]);

    const mapToolbarSummary = useMemo(() => {
        if (!lastRequest) {
            return 'Awaiting first search.';
        }
        return lastRequest.use_coordinates ? 'Coordinate search' : 'Address search';
    }, [lastRequest]);

    const rerunLastSearch = () => {
        if (lastRequest) {
            handleSearch(lastRequest);
        }
    };

    return (
        <div className="geospatial-page">
            <header className="app-header">
                <h1 className="app-title">AEGIS Geographics</h1>
                <p className="app-subtitle">Visualize geographic data overlays in real time</p>
            </header>

            <section className="controls-row" aria-label="Search controls">
                <section className="panel" aria-label="Location search">
                    <LocationSearch onSearch={handleSearch} isLoading={isLoading} />
                </section>
                <section className="panel" aria-label="Agentic search">
                    <AgenticSearch
                        config={agenticConfig}
                        onChange={setAgenticConfig}
                        isRunning={isLoading && agenticConfig.enabled}
                        lastSummary={agentSummary}
                        settings={settings}
                        onSettingsChange={setSettings}
                    />
                </section>
            </section>

            <section className="visual-row" aria-label="Map and statistics">
                <section className="panel map-panel" aria-label="Map section">
                    <div className="panel-head">
                        <PanelHeader
                            title="Map"
                            description="Rendered view with toolbar controls."
                        />
                        <div className="map-toolbar">
                            <div className="toolbar-group">
                                <span className="toolbar-label">Location</span>
                                <span className="toolbar-value">{locationSummary}</span>
                            </div>
                            <div className="toolbar-group">
                                <span className="toolbar-label">Mode</span>
                                <span className="toolbar-value">{mapToolbarSummary}</span>
                            </div>
                            <div className="toolbar-actions" aria-label="Map controls">
                                <button type="button" className="ghost-button" onClick={rerunLastSearch}>
                                    Reset view
                                </button>
                                <button
                                    type="button"
                                    className="ghost-button"
                                    onClick={rerunLastSearch}
                                    disabled={!lastRequest || isLoading}
                                >
                                    Reload overlays
                                </button>
                            </div>
                        </div>
                    </div>
                    <MapPreview
                        payload={searchResult.payload}
                        isLoading={isLoading}
                    />
                </section>

                <section className="panel stats-panel" aria-label="Statistics and verbose information">
                    <StatsPanel
                        payload={searchResult.payload}
                        message={searchResult.message}
                        isLoading={isLoading}
                        agenticEnabled={agenticConfig.enabled}
                        locationSummary={locationSummary}
                        agentNote={agentSummary}
                    />
                </section>
            </section>
        </div>
    );
}

export default GeospatialPage;
