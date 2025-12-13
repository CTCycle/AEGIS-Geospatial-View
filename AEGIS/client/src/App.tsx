import { useState } from 'react';
import './App.css';
import Sidebar, { PageType } from './components/Sidebar';
import GeospatialPage from './pages/GeospatialPage';
import DatabaseBrowserPage from './pages/DatabaseBrowserPage';
import { DatabaseBrowserProvider } from './context/DatabaseBrowserContext';

function App() {
    const [activePage, setActivePage] = useState<PageType>('geospatial');

    const handleNavigate = (page: PageType) => {
        setActivePage(page);
    };

    return (
        <DatabaseBrowserProvider>
            <div className="app-layout">
                <Sidebar activePage={activePage} onNavigate={handleNavigate} />
                <main className="main-content" role="main">
                    {activePage === 'geospatial' && <GeospatialPage />}
                    {activePage === 'database' && <DatabaseBrowserPage />}
                </main>
            </div>
        </DatabaseBrowserProvider>
    );
}

export default App;

