import { useMemo, useState } from 'react';

import LocationSearch from '../components/LocationSearch';
import MapPreview from '../components/MapPreview';
import PanelHeader from '../components/PanelHeader';
import StatsPanel from '../components/StatsPanel';
import { searchLocation } from '../services/api';
import { LocationSearchRequest, SearchResponsePayload } from '../types';
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
    const [isLoading, setIsLoading] = useState(false);
    const [searchResult, setSearchResult] = useState<SearchResultState>({});
    const [lastRequest, setLastRequest] = useState<LocationSearchRequest | undefined>();

    const handleSearch = async (request: LocationSearchRequest) => {
        setIsLoading(true);
        setSearchResult({});
        setLastRequest(request);

        try {
            const response = await searchLocation(request);
            setSearchResult({
                message: response.status_message,
                json: response.json ?? response.payload,
                payload: response.payload,
            });
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

    const searchModeSummary = useMemo(() => {
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
            <header className="geospatial-page__header">
                <h1 className="geospatial-page__title">AEGIS Geospatial View</h1>
                <p className="geospatial-page__subtitle">Search locations and render map overlays in real time.</p>
            </header>

            <div className="geospatial-workspace">
                <aside className="panel toolbar-panel" aria-label="Search toolbar">
                    <PanelHeader
                        title="Search Commands"
                        description="Use address or coordinates, then select map layers."
                        headingLevel={2}
                    />
                    <div className="toolbar-summary" aria-live="polite">
                        <div className="toolbar-summary__item">
                            <span className="toolbar-summary__label">Location</span>
                            <span className="toolbar-summary__value">{locationSummary}</span>
                        </div>
                        <div className="toolbar-summary__item">
                            <span className="toolbar-summary__label">Mode</span>
                            <span className="toolbar-summary__value">{searchModeSummary}</span>
                        </div>
                    </div>
                    <div className="toolbar-actions" aria-label="Search actions">
                        <button
                            type="button"
                            className="secondary-button"
                            onClick={rerunLastSearch}
                            disabled={!lastRequest || isLoading}
                        >
                            Re-run last search
                        </button>
                    </div>
                    <LocationSearch onSearch={handleSearch} isLoading={isLoading} />
                </aside>

                <section className="panel canvas-panel" aria-label="Map canvas and statistics">
                    <PanelHeader
                        title="Map Canvas"
                        description="Rendered map output and metadata for the current search."
                        headingLevel={2}
                    />
                    <MapPreview payload={searchResult.payload} isLoading={isLoading} />
                    <StatsPanel
                        payload={searchResult.payload}
                        message={searchResult.message}
                        isLoading={isLoading}
                        locationSummary={locationSummary}
                    />
                </section>
            </div>
        </div>
    );
}

export default GeospatialPage;
