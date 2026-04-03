import { useEffect, useState } from 'react';

import AgentChatPanel from '../components/chat/AgentChatPanel';
import MapPreview from '../components/MapPreview';
import { MapSession, SearchResponsePayload } from '../types';
import './GeospatialPage.css';

interface GeospatialPageProps {
    onOpenSettings: () => void;
}

function GeospatialPage({ onOpenSettings }: GeospatialPageProps) {
    const [payload, setPayload] = useState<SearchResponsePayload | undefined>();
    const [toolbarWidth, setToolbarWidth] = useState(360);
    const [isToolbarCollapsed, setIsToolbarCollapsed] = useState(false);
    const [isResizing, setIsResizing] = useState(false);

    useEffect(() => {
        if (!isResizing) {
            return;
        }

        const minWidth = 280;
        const maxWidth = 560;

        const onMouseMove = (event: MouseEvent) => {
            const viewportWidth = window.innerWidth;
            const clamped = Math.max(minWidth, Math.min(maxWidth, Math.min(event.clientX, viewportWidth - 320)));
            setToolbarWidth(clamped);
        };

        const onMouseUp = () => {
            setIsResizing(false);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);

        return () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };
    }, [isResizing]);

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
            <div
                className={`geospatial-workspace${isToolbarCollapsed ? ' geospatial-workspace--toolbar-collapsed' : ''}`}
                style={{ ['--toolbar-width' as string]: `${toolbarWidth}px` }}
            >
                <aside className="toolbar-panel" aria-label="Chat toolbar">
                    <header className="toolbar-brand" aria-label="Application identity">
                        <div>
                            <span className="toolbar-brand__logo">AEGIS</span>
                            <p className="toolbar-brand__meta">Operations Console</p>
                        </div>
                        <div className="toolbar-actions">
                            <button
                                type="button"
                                className="toolbar-collapse"
                                aria-label={isToolbarCollapsed ? 'Expand toolbar' : 'Collapse toolbar'}
                                onClick={() => setIsToolbarCollapsed((current) => !current)}
                            >
                                {isToolbarCollapsed ? '>' : '<'}
                            </button>
                            <button
                                type="button"
                                className="toolbar-gear"
                                aria-label="Open settings"
                                onClick={onOpenSettings}
                            >
                                Settings
                            </button>
                        </div>
                    </header>

                    <div className="toolbar-panel__content">
                        <AgentChatPanel onMapSession={handleMapSession} />
                    </div>
                </aside>

                {!isToolbarCollapsed && (
                    <div
                        className={`toolbar-resize-handle${isResizing ? ' is-active' : ''}`}
                        aria-hidden="true"
                        onMouseDown={() => setIsResizing(true)}
                    />
                )}

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

