import './App.css';
import GeospatialPage from './pages/GeospatialPage';
import SettingsPage from './pages/SettingsPage';
import { useState } from 'react';

function App() {
    const [view, setView] = useState<'chat' | 'settings'>('chat');

    return (
        <div className="app-shell">
            <main className="app-content" role="main">
                {view === 'chat' ? (
                    <GeospatialPage onOpenSettings={() => setView('settings')} />
                ) : (
                    <SettingsPage onBack={() => setView('chat')} />
                )}
            </main>
        </div>
    );
}

export default App;

