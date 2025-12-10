import React, { useState } from 'react';
import { COMMON_FOLIUM_MAPS, COMMON_GEOSPATIAL_LAYERS, MAX_GEOSPATIAL_LAYERS } from '../constants';
import { LocationSearchRequest } from '../types';
import './LocationSearch.css';

interface LocationSearchProps {
    onSearch: (request: LocationSearchRequest) => void;
    isLoading: boolean;
}

type SearchMode = 'address' | 'coordinates';

const LocationSearch: React.FC<LocationSearchProps> = ({ onSearch, isLoading }) => {
    const [mode, setMode] = useState<SearchMode>('address');
    const [address, setAddress] = useState('');
    const [latitude, setLatitude] = useState('');
    const [longitude, setLongitude] = useState('');
    const [mapTile, setMapTile] = useState('OpenStreetMap');
    const [selectedFilters, setSelectedFilters] = useState<string[]>([]);
    const [errors, setErrors] = useState<{ address?: string; latitude?: string; longitude?: string }>({});
    const hasReachedFilterLimit = selectedFilters.length >= MAX_GEOSPATIAL_LAYERS;

    const resetErrors = () => setErrors({});

    const validateCoordinates = () => {
        const newErrors: { latitude?: string; longitude?: string } = {};
        const parsedLat = parseFloat(latitude);
        const parsedLon = parseFloat(longitude);

        if (!latitude.trim()) {
            newErrors.latitude = 'Latitude is required in coordinate mode.';
        } else if (Number.isNaN(parsedLat)) {
            newErrors.latitude = 'Latitude must be numeric.';
        } else if (parsedLat < -90 || parsedLat > 90) {
            newErrors.latitude = 'Latitude must be between -90 and 90.';
        }

        if (!longitude.trim()) {
            newErrors.longitude = 'Longitude is required in coordinate mode.';
        } else if (Number.isNaN(parsedLon)) {
            newErrors.longitude = 'Longitude must be numeric.';
        } else if (parsedLon < -180 || parsedLon > 180) {
            newErrors.longitude = 'Longitude must be between -180 and 180.';
        }

        return { newErrors, parsedLat, parsedLon };
    };

    const validateAddress = () => {
        if (!address.trim()) {
            return 'Enter an address (e.g., "Via Tesserete 29, Tesserete, Svizzera").';
        }
        return '';
    };

    const handleSubmit = (event: React.FormEvent) => {
        event.preventDefault();
        resetErrors();

        if (mode === 'address') {
            const addressError = validateAddress();
            if (addressError) {
                setErrors({ address: addressError });
                return;
            }
        }

        if (mode === 'coordinates') {
            const { newErrors, parsedLat, parsedLon } = validateCoordinates();
            if (newErrors.latitude || newErrors.longitude) {
                setErrors(newErrors);
                return;
            }

            const request: LocationSearchRequest = {
                datetime: new Date().toISOString(),
                use_coordinates: true,
                latitude: parsedLat,
                longitude: parsedLon,
                map_tiles: mapTile,
                filters: selectedFilters,
            };
            onSearch(request);
            return;
        }

        const request: LocationSearchRequest = {
            datetime: new Date().toISOString(),
            use_coordinates: false,
            address: address.trim(),
            map_tiles: mapTile,
            filters: selectedFilters,
        };
        onSearch(request);
    };

    const handleFilterSelect = (value: string) => {
        if (!value) {
            return;
        }
        if (hasReachedFilterLimit) {
            return;
        }
        const normalized = value === 'None' ? '' : value;
        if (normalized && !selectedFilters.includes(normalized)) {
            setSelectedFilters([...selectedFilters, normalized]);
        }
    };

    const removeFilter = (filter: string) => {
        setSelectedFilters(selectedFilters.filter((f) => f !== filter));
    };

    const renderAddressFields = () => (
        <div className="field-grid">
            <div className="form-group full-width">
                <label htmlFor="address">Full Address</label>
                <input
                    id="address"
                    type="text"
                    placeholder="e.g., Via Tesserete 29, Tesserete, Svizzera"
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    aria-describedby="location-helper"
                />
                <p className="helper-text">Enter a complete address including street, city, and country</p>
                {errors.address && <p className="error-text">{errors.address}</p>}
            </div>
        </div>
    );

    const renderCoordinateFields = () => (
        <div className="field-grid">
            <div className="form-group">
                <label htmlFor="latitude">Latitude</label>
                <input
                    id="latitude"
                    type="number"
                    step="0.000001"
                    placeholder="Decimal degrees from -90 to 90"
                    value={latitude}
                    onChange={(e) => setLatitude(e.target.value)}
                />
                <p className="helper-text">Numeric value, -90 to 90</p>
                {errors.latitude && <p className="error-text">{errors.latitude}</p>}
            </div>
            <div className="form-group">
                <label htmlFor="longitude">Longitude</label>
                <input
                    id="longitude"
                    type="number"
                    step="0.000001"
                    placeholder="Decimal degrees from -180 to 180"
                    value={longitude}
                    onChange={(e) => setLongitude(e.target.value)}
                />
                <p className="helper-text">Numeric value, -180 to 180</p>
                {errors.longitude && <p className="error-text">{errors.longitude}</p>}
            </div>
        </div>
    );

    return (
        <form className="location-container" onSubmit={handleSubmit}>
            <div className="header-row">
                <div>
                    <h3 className="panel-title">Location search</h3>
                    <p className="panel-description">Specify where to focus the map.</p>
                </div>
                <div className="mode-switch" role="tablist" aria-label="Search mode">
                    <button
                        type="button"
                        className={`mode-tab ${mode === 'address' ? 'active' : ''}`}
                        onClick={() => setMode('address')}
                        aria-selected={mode === 'address'}
                    >
                        Address
                    </button>
                    <button
                        type="button"
                        className={`mode-tab ${mode === 'coordinates' ? 'active' : ''}`}
                        onClick={() => setMode('coordinates')}
                        aria-selected={mode === 'coordinates'}
                    >
                        Coordinates
                    </button>
                </div>
            </div>

            <div className="group-label">Location</div>
            <p id="location-helper" className="helper-text">
                Choose address mode or coordinate mode. Validation applies only to the active mode.
            </p>

            {mode === 'address' ? renderAddressFields() : renderCoordinateFields()}

            <div className="group-label">Map context</div>
            <p className="helper-text">Select base map and optional geospatial filters to include in results.</p>
            <div className="field-grid">
                <div className="form-group">
                    <label htmlFor="base-map">Base map</label>
                    <select
                        id="base-map"
                        value={mapTile}
                        onChange={(e) => setMapTile(e.target.value)}
                    >
                        {Object.entries(COMMON_FOLIUM_MAPS).map(([key, label]) => (
                            <option key={key} value={key}>{label}</option>
                        ))}
                    </select>
                </div>
                <div className="form-group">
                    <label htmlFor="geospatial-layer">Geospatial layer</label>
                    <select
                        id="geospatial-layer"
                        defaultValue=""
                        onChange={(e) => {
                            handleFilterSelect(e.target.value);
                            e.target.value = '';
                        }}
                        disabled={hasReachedFilterLimit}
                    >
                        <option value="" disabled>Select a layer...</option>
                        <option value="None">None</option>
                        {Object.entries(COMMON_GEOSPATIAL_LAYERS).map(([key, label]) => (
                            <option key={key} value={key}>{label}</option>
                        ))}
                    </select>

                </div>
            </div>

            <div className="form-group">
                <p className="helper-text">
                    Choose multiple layers; click a chip to remove. Up to {MAX_GEOSPATIAL_LAYERS} overlays.
                </p>
                {hasReachedFilterLimit && (
                    <p className="error-text">
                        Maximum overlays selected. Remove one to add another.
                    </p>
                )}
                <div className="chip-container">
                    {selectedFilters.length === 0 && <span className="no-filters">No filters selected</span>}
                    {selectedFilters.map((filter) => (
                        <div
                            key={filter}
                            className="chip"
                            title={COMMON_GEOSPATIAL_LAYERS[filter] || filter}
                            onClick={() => removeFilter(filter)}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => e.key === 'Enter' && removeFilter(filter)}
                            aria-label={`Remove ${COMMON_GEOSPATIAL_LAYERS[filter] || filter}`}
                        >
                            {COMMON_GEOSPATIAL_LAYERS[filter] || filter}
                            <span className="chip-close">✕</span>
                        </div>
                    ))}
                </div>
            </div>

            <div className="actions">
                <button className="primary-button" type="submit" disabled={isLoading}>
                    {isLoading ? 'Searching...' : 'Search'}
                </button>
            </div>
        </form>
    );
};

export default LocationSearch;
