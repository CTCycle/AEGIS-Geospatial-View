import React, { useState } from 'react';
import { COMMON_GEOSPATIAL_LAYERS, COMMON_FOLIUM_MAPS } from '../constants';
import { LocationSearchRequest } from '../types';
import './LocationSearch.css';

interface LocationSearchProps {
    onSearch: (request: LocationSearchRequest) => void;
    isLoading: boolean;
}

const LocationSearch: React.FC<LocationSearchProps> = ({ onSearch, isLoading }) => {
    const [useCoordinates, setUseCoordinates] = useState(false);
    const [country, setCountry] = useState('');
    const [city, setCity] = useState('');
    const [address, setAddress] = useState('');
    const [latitude, setLatitude] = useState<number | ''>('');
    const [longitude, setLongitude] = useState<number | ''>('');
    const [selectedFilters, setSelectedFilters] = useState<string[]>([]);
    const [mapTile, setMapTile] = useState('OpenStreetMap');
    const [agenticEnabled, setAgenticEnabled] = useState(false);
    const [agentPrompt, setAgentPrompt] = useState('');

    const handleFilterSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
        const value = e.target.value;
        if (value && value !== 'None' && !selectedFilters.includes(value)) {
            setSelectedFilters([...selectedFilters, value]);
        }
        e.target.value = ''; // Reset select
    };

    const removeFilter = (filter: string) => {
        setSelectedFilters(selectedFilters.filter((f) => f !== filter));
    };

    const handleSearch = () => {
        const nowIso = new Date().toISOString();
        const request: LocationSearchRequest = {
            datetime: nowIso,
            use_coordinates: useCoordinates,
            country: !useCoordinates ? country : undefined,
            city: !useCoordinates ? city : undefined,
            address: !useCoordinates ? address : undefined,
            latitude: useCoordinates && latitude !== '' ? Number(latitude) : undefined,
            longitude: useCoordinates && longitude !== '' ? Number(longitude) : undefined,
            filters: selectedFilters,
            map_tiles: mapTile,
            agentic_enabled: agenticEnabled,
            agent_prompt: agenticEnabled ? agentPrompt : undefined,
        };
        onSearch(request);
    };

    return (
        <div className="card location-search-card">
            <div className="card-content">
                <h3 className="section-title">Location search</h3>

                <div className="search-inputs-row">
                    <div className="input-column">
                        <div className="form-group">
                            <label>Country or Region</label>
                            <input
                                type="text"
                                placeholder="Enter a country or region"
                                value={country}
                                onChange={(e) => setCountry(e.target.value)}
                                disabled={useCoordinates}
                            />
                        </div>
                        <div className="form-group">
                            <label>City Name</label>
                            <input
                                type="text"
                                placeholder="Enter a city or locale"
                                value={city}
                                onChange={(e) => setCity(e.target.value)}
                                disabled={useCoordinates}
                            />
                        </div>
                        <div className="form-group">
                            <label>Street Address</label>
                            <input
                                type="text"
                                placeholder="Enter the specific address"
                                value={address}
                                onChange={(e) => setAddress(e.target.value)}
                                disabled={useCoordinates}
                                required={!useCoordinates}
                            />
                        </div>

                        <div className="coordinates-section">
                            <div className="coordinates-header">
                                <div className="coordinates-labels">
                                    <p className="coordinates-title">Coordinate input</p>
                                    <p className="coordinates-description">Enable to search by latitude and longitude instead of address.</p>
                                </div>
                                <div className="coordinates-toggle">
                                    <span className={`toggle-status ${useCoordinates ? 'active' : ''}`}>
                                        {useCoordinates ? 'Enabled' : 'Disabled'}
                                    </span>
                                    <label className="switch" aria-label="Toggle coordinate input">
                                        <input
                                            type="checkbox"
                                            checked={useCoordinates}
                                            onChange={(e) => setUseCoordinates(e.target.checked)}
                                        />
                                        <span className="slider round"></span>
                                    </label>
                                </div>
                            </div>
                            <div className="coordinates-row">
                                <div className="form-group">
                                    <label>Latitude (?)</label>
                                    <input
                                        type="number"
                                        step="0.000001"
                                        value={latitude}
                                        onChange={(e) => setLatitude(e.target.value === '' ? '' : parseFloat(e.target.value))}
                                        disabled={!useCoordinates}
                                    />
                                </div>
                                <div className="form-group">
                                    <label>Longitude (?)</label>
                                    <input
                                        type="number"
                                        step="0.000001"
                                        value={longitude}
                                        onChange={(e) => setLongitude(e.target.value === '' ? '' : parseFloat(e.target.value))}
                                        disabled={!useCoordinates}
                                    />
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="separator hidden-xl"></div>

                    <div className="input-column">
                        <div className="form-group">
                            <label>Base Map</label>
                            <select value={mapTile} onChange={(e) => setMapTile(e.target.value)}>
                                {Object.entries(COMMON_FOLIUM_MAPS).map(([key, label]) => (
                                    <option key={key} value={key}>
                                        {label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="form-group">
                            <label>Geospatial Layer</label>
                            <select onChange={handleFilterSelect} defaultValue="">
                                <option value="" disabled>Select a layer...</option>
                                <option value="None">None</option>
                                {Object.entries(COMMON_GEOSPATIAL_LAYERS).map(([key, label]) => (
                                    <option key={key} value={key}>
                                        {label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="chip-container">
                            {selectedFilters.length === 0 && (
                                <span className="no-filters">No filters selected</span>
                            )}
                            {selectedFilters.map((filter) => (
                                <div key={filter} className="chip" onClick={() => removeFilter(filter)}>
                                    {COMMON_GEOSPATIAL_LAYERS[filter] || filter}
                                    <span className="material-icons chip-close">close</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <hr className="divider" />

                <div className="agentic-section">
                    <div className="agentic-header">
                        <label className="checkbox-label">
                            <input
                                type="checkbox"
                                checked={agenticEnabled}
                                onChange={(e) => setAgenticEnabled(e.target.checked)}
                            />
                            Activate agentic assistant
                        </label>
                    </div>
                    {agenticEnabled && (
                        <div className="agentic-content fade-in">
                            <div className="form-group">
                                <label>Agent Prompt</label>
                                <textarea
                                    placeholder="Describe the geographic insights you need"
                                    value={agentPrompt}
                                    onChange={(e) => setAgentPrompt(e.target.value)}
                                    rows={3}
                                />
                            </div>
                        </div>
                    )}
                </div>

                <div className="actions">
                    <button className="search-button" onClick={handleSearch} disabled={isLoading}>
                        {isLoading ? (
                            <>
                                <span className="animate-spin material-icons" style={{ fontSize: '1.2em' }}>refresh</span>
                                Searching...
                            </>
                        ) : (
                            <>
                                <span className="material-icons">search</span>
                                Search
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default LocationSearch;
