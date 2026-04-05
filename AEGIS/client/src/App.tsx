import './App.css';
import GeospatialPage from './pages/GeospatialPage';
import SettingsPage from './pages/SettingsPage';
import { useEffect, useMemo, useState } from 'react';
import {
    clearPersistedAppState,
    defaultAppState,
    loadPersistedAppState,
    persistAppState,
    PersistedAppState,
    startTabHeartbeat,
} from './state/appState';

type RouteView = 'chat' | 'settings';

const routeFromPath = (pathname: string): RouteView => {
    if (pathname === '/settings') {
        return 'settings';
    }
    return 'chat';
};

const pathFromRoute = (route: RouteView): string =>
    route === 'settings' ? '/settings' : '/';

function App() {
    const [persistedState, setPersistedState] = useState<PersistedAppState>(() => loadPersistedAppState());
    const [view, setView] = useState<RouteView>(() => routeFromPath(window.location.pathname));

    useEffect(() => {
        if (window.location.pathname !== '/' && window.location.pathname !== '/settings') {
            window.history.replaceState({}, '', '/');
            setView('chat');
        }
    }, []);

    useEffect(() => {
        persistAppState(persistedState);
    }, [persistedState]);

    useEffect(() => startTabHeartbeat(persistedState.tabId), [persistedState.tabId]);

    useEffect(() => {
        const onPopState = () => {
            setView(routeFromPath(window.location.pathname));
        };
        window.addEventListener('popstate', onPopState);
        return () => window.removeEventListener('popstate', onPopState);
    }, []);

    useEffect(() => {
        const onStorage = (event: StorageEvent) => {
            if (event.key === null) {
                clearPersistedAppState();
                setPersistedState(defaultAppState());
            }
        };
        window.addEventListener('storage', onStorage);
        return () => window.removeEventListener('storage', onStorage);
    }, []);

    const navigate = (route: RouteView) => {
        const nextPath = pathFromRoute(route);
        if (window.location.pathname !== nextPath) {
            window.history.pushState({}, '', nextPath);
        }
        setView(route);
    };

    const pageProps = useMemo(() => ({
        chat: persistedState.chatPage,
        settings: persistedState.settingsPage,
    }), [persistedState]);

    return (
        <div className="app-shell">
            <main className="app-content" role="main">
                <GeospatialPage
                    onOpenSettings={() => navigate('settings')}
                    state={pageProps.chat}
                    onStateChange={(chatPage) => setPersistedState((current) => ({ ...current, chatPage }))}
                    isActive={view === 'chat'}
                />
                <SettingsPage
                    onBack={() => navigate('chat')}
                    state={pageProps.settings}
                    onStateChange={(settingsPage) => setPersistedState((current) => ({ ...current, settingsPage }))}
                    isActive={view === 'settings'}
                />
            </main>
        </div>
    );
}

export default App;

