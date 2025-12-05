import React, { useState } from 'react';
import { LocationSearchRequest } from '../types';
import './LocationSearch.css';

interface LocationSearchProps {
    onSearch: (request: LocationSearchRequest) => void;
    isLoading: boolean;
}

type SearchMode = 'address' | 'coordinates';

const LocationSearch: React.FC<LocationSearchProps> = ({ onSearch, isLoading }) => {
    const [mode, setMode] = useState<SearchMode>('address');
    const [country, setCountry] = useState('');
    const [city, setCity] = useState('');
    const [address, setAddress] = useState('');
    const [latitude, setLatitude] = useState('');
    const [longitude, setLongitude] = useState('');
    const [errors, setErrors] = useState<{ address?: string; latitude?: string; longitude?: string }>({});

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
        if (!country.trim() && !city.trim() && !address.trim()) {
            return 'Enter at least one address detail.';
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
            };
            onSearch(request);
            return;
        }

        const request: LocationSearchRequest = {
            datetime: new Date().toISOString(),
            use_coordinates: false,
            country: country || undefined,
            city: city || undefined,
            address: address || undefined,
        };
        onSearch(request);
    };

    const renderAddressFields = () => (
        <div className="field-grid">
            <div className="form-group">
                <label htmlFor="country">Country or region</label>
                <input
                    id="country"
                    type="text"
                    placeholder="e.g., Italy"
                    value={country}
                    onChange={(e) => setCountry(e.target.value)}
                    aria-describedby="location-helper"
                />
            </div>
            <div className="form-group">
                <label htmlFor="city">City or locale</label>
                <input
                    id="city"
                    type="text"
                    placeholder="e.g., Florence"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                />
            </div>
            <div className="form-group">
                <label htmlFor="address">Street address</label>
                <input
                    id="address"
                    type="text"
                    placeholder="e.g., Piazza del Duomo"
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                />
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

            <div className="toolbar-summary" role="status">
                Map layers and models from the left toolbar are applied automatically.
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
