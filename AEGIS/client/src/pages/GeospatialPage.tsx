import { useState } from 'react';

import LocationSearch from '../components/LocationSearch';
import MapPreview from '../components/MapPreview';
import PanelHeader from '../components/PanelHeader';
import { searchLocation } from '../services/api';
import { LocationSearchRequest, SearchResponsePayload } from '../types';
import './GeospatialPage.css';

interface SearchResultState {
    message?: string;
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
                payload: response.payload,
            });
        } catch (error: unknown) {
            const statusCandidate = readErrorField(error, 'status');
            const statusPrefix = typeof statusCandidate === 'number' ? ` ${statusCandidate}` : '';
            const messageCandidate = readErrorField(error, 'message');

            setSearchResult({
                message: `Error${statusPrefix}: ${typeof messageCandidate === 'string' ? messageCandidate : 'Request failed'}`,
                payload: undefined,
            });
        } finally {
            setIsLoading(false);
        }
    };

    const rerunLastSearch = () => {
        if (lastRequest) {
            handleSearch(lastRequest);
        }
    };

    return (
        <div className="geospatial-page">
            <div className="geospatial-workspace">
                <aside className="toolbar-panel" aria-label="Search toolbar">
                    <header className="toolbar-brand" aria-label="Application identity">
                        <span className="toolbar-brand__logo">AEGIS</span>
                        <p className="toolbar-brand__meta">Operations Console</p>
                    </header>

                    <div className="toolbar-panel__content">
                        <PanelHeader
                            title="Search Commands"
                            description="Use address or coordinates, then select map layers."
                            headingLevel={2}
                        />
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
                    </div>
                </aside>

                <section className="canvas-panel" aria-label="Map canvas">
                    <MapPreview
                        payload={searchResult.payload}
                        isLoading={isLoading}
                        emptyMessage={searchResult.message ?? 'Run a search to display the map.'}
                    />
                </section>
            </div>
        </div>
    );
}

export default GeospatialPage;
