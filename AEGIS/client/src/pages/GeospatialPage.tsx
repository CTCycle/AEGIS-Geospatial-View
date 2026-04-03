import { useState } from 'react';

import AgentChatPanel from '../components/chat/AgentChatPanel';
import MapPreview from '../components/MapPreview';
import { MapSession, SearchResponsePayload } from '../types';
import './GeospatialPage.css';

interface GeospatialPageProps {
    onOpenSettings: () => void;
}

function GeospatialPage({ onOpenSettings }: GeospatialPageProps) {
    const [payload, setPayload] = useState<SearchResponsePayload | undefined>();

    const handleMapSession = (mapSession: MapSession | undefined) => {
        if (!mapSession) {
            return;
        }
        setPayload({
            satellite_imagery: payload?.satellite_imagery,
            map_session: mapSession,
            compliance_warnings: mapSession.compliance_warnings,
        });
    };

    return (
        <div className="geospatial-page">
            <div className="geospatial-workspace">
                <aside className="toolbar-panel" aria-label="Chat toolbar">
                    <header className="toolbar-brand" aria-label="Application identity">
                        <div>
                            <span className="toolbar-brand__logo">AEGIS</span>
                            <p className="toolbar-brand__meta">Operations Console</p>
                        </div>
                        <button
                            type="button"
                            className="toolbar-gear"
                            aria-label="Open settings"
                            onClick={onOpenSettings}
                        >
                            Settings
                        </button>
                    </header>

                    <div className="toolbar-panel__content">
                        <AgentChatPanel onMapSession={handleMapSession} />
                    </div>
                </aside>

                <section className="canvas-panel" aria-label="Map canvas">
                    <MapPreview
                        payload={payload}
                        isLoading={false}
                        emptyMessage="Ask the assistant to run a geospatial search."
                    />
                </section>
            </div>
        </div>
    );
}

export default GeospatialPage;
