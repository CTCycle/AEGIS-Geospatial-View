import { useState } from 'react';
import './App.css';
import GeospatialPage from './pages/GeospatialPage';

function App() {
    const [activeTab, setActiveTab] = useState<'geospatial'>('geospatial');

    const handleSelectTab = (tab: 'geospatial') => {
        setActiveTab(tab);
    };

    return (
        <div className="app-shell">
            <header className="top-navbar">
                <div className="top-navbar__inner">
                    <span className="top-navbar__brand">AEGIS</span>
                    <nav aria-label="Primary tabs">
                        <div className="top-navbar__tabs" role="tablist">
                            <button
                                type="button"
                                role="tab"
                                id="tab-geospatial"
                                className={`top-navbar__tab ${activeTab === 'geospatial' ? 'top-navbar__tab--active' : ''}`}
                                aria-selected={activeTab === 'geospatial'}
                                aria-controls="panel-geospatial"
                                onClick={() => handleSelectTab('geospatial')}
                            >
                                Geospatial View
                            </button>
                        </div>
                    </nav>
                </div>
            </header>

            <main className="app-content" role="main">
                <section
                    id="panel-geospatial"
                    role="tabpanel"
                    aria-labelledby="tab-geospatial"
                >
                    <GeospatialPage />
                </section>
            </main>
        </div>
    );
}

export default App;

