import { useEffect, useState } from 'react';

import AgentChatPanel from '../components/chat/AgentChatPanel';
import MapPreview from '../components/MapPreview';
import { MapSession, SearchResponsePayload } from '../types';
import './GeospatialPage.css';
import { PersistedChatPageState } from '../state/appState';

interface GeospatialPageProps {
    onOpenSettings: () => void;
    state: PersistedChatPageState;
    onStateChange: (state: PersistedChatPageState) => void;
    isActive: boolean;
}

function GeospatialPage({ onOpenSettings, state, onStateChange, isActive }: GeospatialPageProps) {
    const [payload, setPayload] = useState<SearchResponsePayload | undefined>(state.payload);
    const [toolbarWidth, setToolbarWidth] = useState(state.toolbarWidth);
    const [isToolbarCollapsed, setIsToolbarCollapsed] = useState(state.isToolbarCollapsed);
    const [chatPanelState, setChatPanelState] = useState(state.chatPanel);
    const [mapState, setMapState] = useState(state.mapState);
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

    useEffect(() => {
        onStateChange({
            toolbarWidth,
            isToolbarCollapsed,
            payload,
            chatPanel: chatPanelState,
            mapState,
            scrollY: isActive ? window.scrollY : state.scrollY,
        });
    }, [toolbarWidth, isToolbarCollapsed, payload, chatPanelState, mapState, isActive, state.scrollY, onStateChange]);

    useEffect(() => {
        if (!isActive) {
            return;
        }
        window.scrollTo({ top: state.scrollY, behavior: 'auto' });
    }, [isActive, state.scrollY]);

    return (
        <div className="geospatial-page" hidden={!isActive} aria-hidden={!isActive}>
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
                        <AgentChatPanel
                            onMapSession={handleMapSession}
                            initialState={chatPanelState}
                            onStateChange={setChatPanelState}
                        />
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
                        initialOverlayVisibility={mapState.overlayVisibility}
                        initialOverlayOpacity={mapState.overlayOpacity}
                        onOverlayStateChange={setMapState}
                    />
                </section>
            </div>
        </div>
    );
}

export default GeospatialPage;

