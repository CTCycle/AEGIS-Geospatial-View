import { useMemo, useState } from 'react';
import './App.css';
import LocationSearch from './components/LocationSearch';
import MapPreview from './components/MapPreview';
import StatsPanel from './components/StatsPanel';
import AgenticSearch from './components/AgenticSearch';
import { AgenticConfig, LocationSearchRequest, RuntimeSettings, SearchResponsePayload } from './types';
import { searchLocation } from './services/api';

function App() {
    const [settings, setSettings] = useState<RuntimeSettings>({
        useCloudServices: false,
        provider: 'openai',
        cloudModel: 'gpt-4o',
        agentModel: 'llama3.1:8b',
    });

    const [isLoading, setIsLoading] = useState(false);
    const [searchResult, setSearchResult] = useState<{
        message?: string;
        json?: any;
        payload?: SearchResponsePayload;
    }>({});
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
                json: response.json || response.payload,
                payload: response.payload,
            });
            setAgentSummary(
                response.payload?.agent_summary ||
                response.payload?.status_message ||
                response.status_message,
            );
        } catch (error: any) {
            setSearchResult({
                message: `Error${error.status ? ` ${error.status}` : ''}: ${error.message || 'Request failed'}`,
                json: error.detail || error.raw || error,
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

    const handleResetView = () => {
        if (lastRequest) {
            handleSearch(lastRequest);
        }
    };

    const handleReload = () => {
        if (lastRequest) {
            handleSearch(lastRequest);
        }
    };

    return (
        <div className="app-container">
            <main className="main-content" role="main">
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
                            <div>
                                <h3 className="panel-title">Map</h3>
                                <p className="panel-description">Rendered view with toolbar controls.</p>
                            </div>
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
                                    <button type="button" className="ghost-button" onClick={handleResetView}>
                                        Reset view
                                    </button>
                                    <button
                                        type="button"
                                        className="ghost-button"
                                        onClick={handleReload}
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
            </main>
        </div>
    );
}

export default App;
