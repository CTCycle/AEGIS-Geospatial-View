import { useCallback, useState } from 'react';

import AgentChatPanel from '../components/chat/AgentChatPanel';
import MapPreview from '../components/MapPreview';
import { MapSession, SearchResponsePayload } from '../types';
import './GeospatialPage.css';
import { PersistedChatPageState } from '../state/appState';
import { useActivePagePersistence } from '../hooks/useActivePagePersistence';
import { useResizableToolbar } from '../hooks/useResizableToolbar';

interface GeospatialPageProps {
    onOpenSettings: () => void;
    state: PersistedChatPageState;
    onStateChange: (state: PersistedChatPageState) => void;
    isActive: boolean;
}

function GeospatialPage({ onOpenSettings, state, onStateChange, isActive }: GeospatialPageProps) {
    const [payload, setPayload] = useState<SearchResponsePayload | undefined>(state.payload);
    const [toolbarWidthState, setToolbarWidthState] = useState(state.toolbarWidth);
    const [isToolbarCollapsed, setIsToolbarCollapsed] = useState(state.isToolbarCollapsed);
    const [chatPanelState, setChatPanelState] = useState(state.chatPanel);
    const [mapState, setMapState] = useState(state.mapState);
    const [chatProgress, setChatProgress] = useState({ isLoading: false, progressPercent: 0 });

    const {
        toolbarWidth,
        isResizing,
        startResize,
    } = useResizableToolbar({
        initialWidth: toolbarWidthState,
        onWidthChange: setToolbarWidthState,
    });

    const handleMapSession = (mapSession: MapSession | undefined) => {
        if (!mapSession) {
            return;
        }
        setPayload((current) => ({
            satellite_imagery: current?.satellite_imagery,
            map_session: mapSession,
            compliance_warnings: mapSession.compliance_warnings,
        }));
    };

    const buildState = useCallback((scrollY: number): PersistedChatPageState => ({
        toolbarWidth: toolbarWidthState,
        isToolbarCollapsed,
        payload,
        chatPanel: chatPanelState,
        mapState,
        scrollY,
    }), [toolbarWidthState, isToolbarCollapsed, payload, chatPanelState, mapState]);

    const restoreState = useCallback(() => {
        window.scrollTo({ top: state.scrollY, behavior: 'auto' });
    }, [state.scrollY]);

    useActivePagePersistence({
        isActive,
        state,
        onStateChange,
        buildState,
        restoreState,
        syncDeps: [toolbarWidthState, isToolbarCollapsed, payload, chatPanelState, mapState],
    });

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
                        </div>
                    </header>

                    <div className="toolbar-panel__content">
                        <AgentChatPanel
                            onMapSession={handleMapSession}
                            initialState={chatPanelState}
                            onStateChange={setChatPanelState}
                            onProgressChange={setChatProgress}
                        />
                    </div>
                </aside>

                <div
                    className={[
                        'toolbar-resize-handle',
                        isResizing ? 'is-active' : '',
                        isToolbarCollapsed ? 'is-collapsed' : ''
                    ].filter(Boolean).join(' ')}
                    aria-hidden="true"
                    onMouseDown={() => {
                        startResize(() => {
                            if (isToolbarCollapsed) {
                                setIsToolbarCollapsed(false);
                            }
                        });
                    }}
                />

                <section className="canvas-panel" aria-label="Map canvas">
                    <header className="canvas-header" aria-label="Workspace header">
                        <div className="canvas-header__actions">
                            <button type="button" className="canvas-header__icon-button" aria-label="Alerts">
                                <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
                                    <path
                                        d="M12 3.5a4.8 4.8 0 0 0-4.8 4.8v1.7c0 .8-.2 1.6-.6 2.3L5.1 15h13.8l-1.5-2.7a4.8 4.8 0 0 1-.6-2.3V8.3A4.8 4.8 0 0 0 12 3.5zm0 17a2.4 2.4 0 0 1-2.2-1.5h4.4A2.4 2.4 0 0 1 12 20.5z"
                                        fill="currentColor"
                                    />
                                </svg>
                            </button>
                            <button
                                type="button"
                                className="canvas-header__icon-button"
                                aria-label="Workspace settings"
                                onClick={onOpenSettings}
                            >
                                <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
                                    <path
                                        d="M19.4 13.5c.1-.5.1-1 .1-1.5s0-1-.1-1.5l2-1.5-2-3.4-2.4 1a8 8 0 0 0-2.6-1.5l-.3-2.6h-4l-.3 2.6a8 8 0 0 0-2.6 1.5l-2.4-1-2 3.4 2 1.5c-.1.5-.1 1-.1 1.5s0 1 .1 1.5l-2 1.5 2 3.4 2.4-1a8 8 0 0 0 2.6 1.5l.3 2.6h4l.3-2.6a8 8 0 0 0 2.6-1.5l2.4 1 2-3.4-2-1.5zM12 15.1a3.1 3.1 0 1 1 0-6.2 3.1 3.1 0 0 1 0 6.2z"
                                        fill="currentColor"
                                    />
                                </svg>
                            </button>
                        </div>
                    </header>
                    <div className="canvas-panel__body">
                    <MapPreview
                        payload={payload}
                        isLoading={false}
                        emptyMessage="Ask the assistant to run a geospatial search."
                        initialOverlayVisibility={mapState.overlayVisibility}
                        initialOverlayOpacity={mapState.overlayOpacity}
                        onOverlayStateChange={setMapState}
                    />
                    </div>
                </section>
                <div className="chat-progress-indicator" aria-live="polite">
                    {chatProgress.isLoading && <span className="chat-progress-spinner" aria-hidden="true" />}
                    <span>{chatProgress.progressPercent}%</span>
                </div>
            </div>
        </div>
    );
}

export default GeospatialPage;

